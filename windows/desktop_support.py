"""Platform services shared by the active desktop entry points."""

import atexit
from pathlib import Path
import subprocess
import sys
import threading


_awake_process = None
_awake_lock = threading.Lock()


def find_resource(name, module_file):
    """Resolve frozen data, adjacent overrides, then source data and cwd."""
    candidates = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(Path(bundle_dir) / name)
    if sys.argv and sys.argv[0]:
        candidates.append(Path(sys.argv[0]).resolve().parent / name)
    candidates.extend((Path(module_file).resolve().parent / name, Path.cwd() / name))
    return next((str(path) for path in candidates if path.is_file()), None)


def default_config_path():
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support"
                / "YNU-Course-Selection-Assistant" / "qiangke_config.json")
    return Path.cwd() / "qiangke_config.json"


def set_macos_awake(enabled):
    """Hold an idle-sleep assertion only while a task is active."""
    global _awake_process
    if sys.platform != "darwin":
        return
    with _awake_lock:
        if enabled:
            if _awake_process is None or _awake_process.poll() is not None:
                # -w also releases the assertion if this Python process is killed.
                import os
                _awake_process = subprocess.Popen(
                    ["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
        elif _awake_process is not None:
            process, _awake_process = _awake_process, None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


atexit.register(set_macos_awake, False)
