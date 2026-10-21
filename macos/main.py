"""macOS entry point; verification modes never perform school operations."""

import argparse
from pathlib import Path
import sys


source_dir = Path(__file__).resolve().parents[1] / "windows"
if source_dir.is_dir():
    sys.path.insert(0, str(source_dir))

import qiangke_web  # noqa: E402
import verify_runtime  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="YNU course assistant for macOS")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true", help="offline resource/OCR/HTTP check")
    mode.add_argument("--gui-smoke-test", action="store_true", help="native WebView and local API check")
    parser.add_argument("--report", type=Path, help="verification JSON report path")
    args = parser.parse_args()
    if args.self_test or args.gui_smoke_test:
        return verify_runtime.run(qiangke_web, gui=args.gui_smoke_test, report_path=args.report)
    qiangke_web.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
