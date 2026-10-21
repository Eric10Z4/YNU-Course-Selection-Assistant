"""Check a copied .app outside the source directory, with bounded processes."""

import argparse
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
from app_version import BUNDLE_IDENTIFIER, bundle_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "x86_64"), required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Native bundle checks require macOS")
    reports = args.reports.resolve()
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="YNU app verification ") as directory:
        directory = Path(directory)
        bundle = directory / "Application With Spaces.app"
        subprocess.run(["/usr/bin/ditto", str(args.app.resolve()), str(bundle)], check=True)
        info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
        if info.get("CFBundleIdentifier") != BUNDLE_IDENTIFIER:
            raise RuntimeError("Unexpected bundle identifier")
        for key, value in bundle_metadata().items():
            if info.get(key) != value:
                raise RuntimeError(f"Unexpected bundle metadata: {key}")
        executable = bundle / "Contents" / "MacOS" / info["CFBundleExecutable"]
        architecture = subprocess.check_output(["/usr/bin/lipo", "-archs", str(executable)], text=True).strip()
        if architecture != args.arch:
            raise RuntimeError(f"Wrong architecture: {architecture}")
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
        (reports / "bundle.json").write_text(json.dumps({
            "architecture": architecture,
            "metadata": bundle_metadata(),
            "ad_hoc_signature_verified": True,
            "copied_bundle_with_spaces": True,
            "developer_id_notarized": False,
        }, indent=2) + "\n", encoding="utf-8")
        empty_cwd = directory / "empty working directory"
        empty_cwd.mkdir()
        for flag, name, timeout in (("--self-test", "bundle-runtime", 90), ("--gui-smoke-test", "bundle-gui", 90)):
            try:
                result = subprocess.run(
                    [str(executable), flag, "--report", str(reports / f"{name}.json")],
                    cwd=empty_cwd, capture_output=True, text=True, timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                (reports / f"{name}.timeout.txt").write_text(f"Process exceeded {timeout} seconds\n", encoding="utf-8")
                raise RuntimeError(f"{name} timed out") from exc
            (reports / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
            (reports / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
            if result.returncode:
                print(result.stdout)
                print(result.stderr, file=sys.stderr)
                raise RuntimeError(f"{name} exited with {result.returncode}")
            report = json.loads((reports / f"{name}.json").read_text(encoding="utf-8"))
            if report["status"] != "passed" or not report["frozen"]:
                raise RuntimeError(f"{name} did not pass as a frozen application")
            print(f"{name}: passed ({architecture})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
