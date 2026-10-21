"""Offline probes used by both the source launcher and frozen app."""

from contextlib import contextmanager
from datetime import datetime, timezone
import http.client
import io
import ipaddress
import json
from pathlib import Path
import platform
import secrets
import socket
import sys
import tempfile
import time
from unittest.mock import patch
from app_version import VERSION, BUILD_VERSION, CHANNEL


@contextmanager
def loopback_only():
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def check(address):
        if isinstance(address, tuple):
            host = address[0]
            if not ipaddress.ip_address(host).is_loopback:
                raise RuntimeError("Verification forbids non-loopback connections")

    def connect(sock, address):
        check(address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check(address)
        return original_connect_ex(sock, address)

    with patch.object(socket.socket, "connect", connect), patch.object(socket.socket, "connect_ex", connect_ex):
        yield


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        conn.close()


def offline_checks(app, checks):
    from PIL import Image
    import lite_ocr

    for name in ("ocr_model.onnx", "ocr_charset.json", "background.jpg"):
        path = app.resource_path(name)
        if not path or not Path(path).is_file():
            raise RuntimeError(f"Missing packaged resource: {name}")
    checks["resources"] = "passed"
    image = Image.new("RGB", (120, 40), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    output = lite_ocr.classification(buffer.getvalue())
    if not isinstance(output, str):
        raise RuntimeError("OCR did not return text")
    checks["synthetic_ocr_inference"] = "passed"

    with tempfile.TemporaryDirectory(prefix="ynu config ") as directory:
        path = Path(directory) / "nested" / "qiangke_config.json"
        api = app.Api()
        with patch.object(app, "default_config_path", return_value=path):
            saved = api.save_config({"courses": [], "verification": True})
            loaded = api.load_config()
        if not saved.get("ok") or loaded.get("cfg") != {"courses": [], "verification": True}:
            raise RuntimeError("Configuration round-trip failed")
    checks["fallback_config_round_trip"] = "passed"

    app.TOKEN = secrets.token_urlsafe(16)
    app._API = app.Api()
    server, port = app.start_server()
    try:
        status, html = request(port, "GET", "/")
        if status != 200 or "__TOKEN__" in html or 'id="btnStart"' not in html:
            raise RuntimeError("Local page did not render")
        status, _ = request(port, "POST", "/api/stop?t=wrong-token", "[]")
        if status != 403:
            raise RuntimeError("Local API accepted an invalid token")
        status, result = request(port, "POST", f"/api/stop?t={app.TOKEN}", "[]")
        if status != 200 or not json.loads(result).get("ok") or not app._API.engine.stop_flag.is_set():
            raise RuntimeError("Local stop API failed")
    finally:
        server.shutdown()
        server.server_close()
    checks["loopback_http_and_token_check"] = "passed"


def gui_checks(app, checks):
    if sys.platform != "darwin" or app.webview is None:
        raise RuntimeError("Native GUI verification requires macOS and PyWebView")
    completed = []
    errors = []

    def loaded(window, api):
        if completed:
            return
        completed.append(True)
        try:
            ready = window.evaluate_js("document.readyState === 'complete' && !!document.querySelector('#btnStart')")
            if not ready:
                raise RuntimeError("Native WebView did not render the app")
            window.evaluate_js("window.__ynuSmoke = 'pending'; callApi('stop').then(r => { window.__ynuSmoke = r.ok ? 'ok' : 'failed'; }).catch(() => { window.__ynuSmoke = 'failed'; });")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                api_ok = window.evaluate_js("window.__ynuSmoke === 'ok'")
                event_ok = window.evaluate_js("document.querySelector('#logbox').textContent.includes('正在停止')")
                if api_ok and event_ok and api.engine.stop_flag.is_set():
                    checks["native_webview_render"] = "passed"
                    checks["javascript_to_local_api"] = "passed"
                    checks["sse_to_native_webview"] = "passed"
                    return
                time.sleep(0.1)
            raise RuntimeError("Native page API or SSE timed out")
        except Exception as exc:
            errors.append(str(exc))
        finally:
            window.destroy()

    app.main(on_loaded=loaded)
    if errors:
        raise RuntimeError("; ".join(errors))
    if not completed or "sse_to_native_webview" not in checks:
        raise RuntimeError("Native WebView closed before verification completed")


def run(app, *, gui=False, report_path=None):
    report = {
        "mode": "native-gui" if gui else "offline-runtime",
        "version": VERSION,
        "build_version": BUILD_VERSION,
        "channel": CHANNEL,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "system": platform.system(),
        "system_version": platform.mac_ver()[0] if sys.platform == "darwin" else platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "scope": "synthetic image and loopback only; no school operations",
        "checks": {},
        "status": "failed",
    }
    try:
        with loopback_only():
            if gui:
                gui_checks(app, report["checks"])
            else:
                offline_checks(app, report["checks"])
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    if report_path:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1
