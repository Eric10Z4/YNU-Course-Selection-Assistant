"""Build an ad-hoc signed, single-architecture macOS test application."""

import argparse
import json
from pathlib import Path
import platform
import plistlib
import subprocess
import sys
from app_version import BUNDLE_IDENTIFIER, bundle_metadata


ROOT = Path(__file__).resolve().parents[1]
NAME = "QiangKeWeb"


def build_command(architecture):
    source = ROOT / "windows"
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--windowed", "--name", NAME,
        "--osx-bundle-identifier", BUNDLE_IDENTIFIER,
        "--target-arch", architecture,
        "--distpath", str(ROOT / "dist" / "macos" / architecture),
        "--workpath", str(ROOT / "build" / "macos" / architecture),
        "--specpath", str(ROOT / "build" / "macos"),
        "--paths", str(source),
        "--icon", str(source / "logo.png"),
        "--collect-all", "webview", "--collect-all", "onnxruntime",
    ]
    for name in ("background.jpg", "ocr_model.onnx", "ocr_charset.json"):
        path = source / name
        if not path.is_file():
            raise FileNotFoundError(path)
        command.extend(("--add-data", f"{path}:."))
    for module in ("torch", "tensorflow", "matplotlib", "pandas", "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter"):
        command.extend(("--exclude-module", module))
    command.append(str(ROOT / "macos" / "main.py"))
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("arm64", "x86_64"), default=platform.machine())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and sys.platform != "darwin":
        parser.error("Build on macOS; use --dry-run elsewhere to inspect the command")
    if not args.dry_run and args.arch != platform.machine():
        parser.error("Use a Python environment matching the requested architecture")
    command = build_command(args.arch)
    if args.dry_run:
        print(json.dumps(command, indent=2))
        return 0
    (ROOT / "build" / "macos").mkdir(parents=True, exist_ok=True)
    subprocess.run(command, cwd=ROOT, check=True)
    app = ROOT / "dist" / "macos" / args.arch / f"{NAME}.app"
    if not (app / "Contents" / "MacOS" / NAME).is_file():
        raise RuntimeError(f"Build did not produce {app}")
    # The CLI emits a minimal 0.0.0 plist. Update it, then reseal the parent
    # bundle; collected Mach-O files retain PyInstaller's ad-hoc signatures.
    info_path = app / "Contents" / "Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    info.update(bundle_metadata())
    info_path.write_bytes(plistlib.dumps(info))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)], check=True)
    print(f"Built test application: {app}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
