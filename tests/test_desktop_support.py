import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "windows"))
sys.path.insert(0, str(ROOT / "macos"))
import desktop_support
import qiangke_web as app


class ResourceTests(unittest.TestCase):
    def test_source_resource_is_found_outside_source_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Path, "cwd", return_value=Path(directory)), patch.object(sys, "argv", [str(Path(directory) / "launcher.py")]):
                self.assertEqual(Path(app.resource_path("background.jpg")), ROOT / "windows" / "background.jpg")

    def test_frozen_resources_take_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / "background.jpg"
            expected.write_bytes(b"frozen resource")
            with patch.object(sys, "_MEIPASS", directory, create=True):
                self.assertEqual(Path(app.resource_path("background.jpg")), expected)

    def test_absent_resource_is_reported_missing(self):
        self.assertIsNone(app.resource_path("resource-that-does-not-exist.bin"))


class ConfigurationTests(unittest.TestCase):
    def test_macos_default_is_user_writable_data_directory(self):
        with patch.object(sys, "platform", "darwin"), patch.object(Path, "home", return_value=Path("/Users/test")):
            path = desktop_support.default_config_path()
        self.assertEqual(path, Path("/Users/test/Library/Application Support/YNU-Course-Selection-Assistant/qiangke_config.json"))

    def test_cancelling_save_does_not_write_a_fallback_file(self):
        api = app.Api()
        api.window = Mock()
        api.window.create_file_dialog.return_value = None
        with patch.object(app, "webview", SimpleNamespace(SAVE_DIALOG="save")), patch.object(app, "default_config_path") as fallback:
            self.assertEqual(api.save_config({"courses": []}), {"ok": False, "cancelled": True})
            fallback.assert_not_called()

    def test_browser_mode_can_save_and_load_without_native_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "qiangke_config.json"
            api = app.Api()
            with patch.object(app, "default_config_path", return_value=path):
                self.assertTrue(api.save_config({"courses": []})["ok"])
                self.assertEqual(api.load_config()["cfg"], {"courses": []})


class AwakeAndLifecycleTests(unittest.TestCase):
    def tearDown(self):
        desktop_support._awake_process = None

    def test_macos_assertion_is_reused_and_released(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(sys, "platform", "darwin"), patch.object(desktop_support.subprocess, "Popen", return_value=process) as spawn:
            desktop_support.set_macos_awake(True)
            desktop_support.set_macos_awake(True)
            self.assertEqual(spawn.call_count, 1)
            self.assertIn("-w", spawn.call_args.args[0])
            desktop_support.set_macos_awake(False)
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=3)
            self.assertIsNone(desktop_support._awake_process)

    def test_macos_assertion_force_cleanup_is_bounded(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("caffeinate", 3), 0]
        desktop_support._awake_process = process
        with patch.object(sys, "platform", "darwin"):
            desktop_support.set_macos_awake(False)
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)

    def test_failed_window_creation_stops_server_and_releases_assertion(self):
        server = Mock()
        webview = Mock()
        webview.create_window.side_effect = RuntimeError("No GUI session")
        with patch.object(app, "start_server", return_value=(server, 12345)), patch.object(app, "webview", webview), patch.object(app, "keep_awake") as awake:
            with self.assertRaisesRegex(RuntimeError, "No GUI session"):
                app.main()
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        awake.assert_called_once_with(False)
        self.assertTrue(app._API.engine.stop_flag.is_set())


class OfflineGuardTests(unittest.TestCase):
    def test_probes_reject_external_connections(self):
        import socket
        spec = importlib.util.spec_from_file_location("verify_runtime", ROOT / "macos" / "verify_runtime.py")
        probes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probes)
        with probes.loopback_only(), socket.socket() as sock:
            with self.assertRaisesRegex(RuntimeError, "non-loopback"):
                sock.connect(("203.0.113.1", 443))
            with self.assertRaisesRegex(RuntimeError, "non-loopback"):
                sock.connect_ex(("203.0.113.1", 443))


if __name__ == "__main__":
    unittest.main()
