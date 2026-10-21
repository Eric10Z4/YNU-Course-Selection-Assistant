"""Package only an application whose source and frozen checks have passed."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from app_version import VERSION, BUILD_VERSION, CHANNEL, RELEASE_TAG


REPORT_NAMES = (
    "source-runtime.json", "bundle.json", "bundle-runtime.json", "bundle-gui.json",
    "bundle-runtime.stdout.txt", "bundle-runtime.stderr.txt",
    "bundle-gui.stdout.txt", "bundle-gui.stderr.txt", "dependencies.txt",
)


def file_record(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"name": path.name, "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def validate_reports(reports, arch):
    results = {}
    for name in ("source-runtime", "bundle-runtime", "bundle-gui"):
        report = json.loads((reports / f"{name}.json").read_text(encoding="utf-8"))
        if report.get("status") != "passed" or report.get("system") != "Darwin" or report.get("architecture") != arch:
            raise ValueError(f"Invalid or failed {name} report for {arch}")
        if report.get("version") != VERSION or report.get("build_version") != BUILD_VERSION or report.get("channel") != CHANNEL:
            raise ValueError(f"Wrong version in {name} report")
        if name.startswith("bundle-") and report.get("frozen") is not True:
            raise ValueError(f"{name} did not run the frozen application")
        required = ({"resources", "synthetic_ocr_inference", "fallback_config_round_trip", "loopback_http_and_token_check"}
                    if name != "bundle-gui" else
                    {"native_webview_render", "javascript_to_local_api", "sse_to_native_webview"})
        if any(report.get("checks", {}).get(check) != "passed" for check in required):
            raise ValueError(f"Missing verification in {name}")
        results[name] = report
    bundle = json.loads((reports / "bundle.json").read_text(encoding="utf-8"))
    if bundle.get("architecture") != arch or bundle.get("ad_hoc_signature_verified") is not True:
        raise ValueError("Bundle signature/architecture was not verified")
    return results


def package(app, arch, reports, output, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("An exact source commit is required")
    results = validate_reports(reports, arch)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"QiangKeWeb-{VERSION}-macos-{arch}.zip"
    if archive.exists():
        raise FileExistsError(archive)
    subprocess.run(["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app.resolve()), str(archive.resolve())], check=True)
    audit = output / f"verification-{arch}.zip"
    with zipfile.ZipFile(audit, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in REPORT_NAMES:
            path = reports / name
            if not path.is_file():
                raise FileNotFoundError(path)
            bundle.write(path, name)
    manifest = {
        "schema_version": 1,
        "version": VERSION,
        "build_version": BUILD_VERSION,
        "channel": CHANNEL,
        "release_tag": RELEASE_TAG,
        "source_commit": commit,
        "architecture": arch,
        "signing": "ad-hoc",
        "notarized": False,
        "human_acceptance": "pending",
        "school_operations_tested": False,
        "verified_system": results["bundle-runtime"]["system_version"],
        "files": [file_record(archive), file_record(audit)],
    }
    (output / f"manifest-{arch}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Packaged {archive.name}: {commit}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "x86_64"), required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Preserve macOS bundle metadata by packaging on macOS")
    package(args.app, args.arch, args.reports, args.output, args.commit)


if __name__ == "__main__":
    main()
