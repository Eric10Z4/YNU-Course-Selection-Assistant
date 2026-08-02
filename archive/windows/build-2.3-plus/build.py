# -*- coding: utf-8 -*-
"""
YNU 抢课助手 · 一键打包脚本
用法：把本文件和 qiangke_web*.py 等文件放同一文件夹，
      命令行运行：  python build.py
成品在 dist/QiangKeWeb.exe
"""
import os
import sys
import glob
import subprocess
import shutil

DEPS = ["pyinstaller", "pywebview", "requests", "onnxruntime", "yagmail", "pillow", "numpy"]
NAME = "QiangKeWeb"
BG_CANDIDATES = ("background.png", "background.jpg", "background.jpeg", "bg.png", "bg.jpg")
EXCLUDES = ["torch", "torchvision", "torchaudio", "matplotlib", "scipy", "pandas",
            "tkinter", "IPython", "notebook", "jupyter", "sympy", "tensorflow",
            "sklearn", "scikit-learn", "numba", "PyQt5", "PyQt6", "PySide2", "PySide6",
            "wx", "pygame", "cv2", "ddddocr",
            "PIL._avif", "PIL.AvifImagePlugin",
            "numpy.f2py", "numpy.testing", "numpy.tests", "numpy.distutils",
            "lxml.objectify",
            "onnxruntime.transformers", "onnxruntime.quantization",
            "onnxruntime.training", "onnxruntime.tools"]


def run(cmd, **kw):
    print(">>", " ".join(cmd))
    return subprocess.run(cmd, **kw).returncode


def find_entry(src_dir):
    matches = glob.glob(os.path.join(src_dir, "qiangke_web*.py"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        matches.sort(key=os.path.getmtime, reverse=True)
        print(f"  找到多个入口文件，使用最新的：{os.path.basename(matches[0])}")
        return matches[0]
    return None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)

    entry = find_entry(here)
    if not entry:
        print("[X] 找不到 qiangke_web*.py，请把本脚本和源码放在同一文件夹。")
        input("按回车退出…")
        return
    ENTRY = os.path.basename(entry)
    print(f"  入口文件：{ENTRY}")

    # ---- 步骤 1：创建干净 venv（避免 conda 把无关库打进去）----
    print("[1/3] 准备虚拟环境…")
    venv_path = os.path.join(here, ".build_venv")
    venv_python = os.path.join(venv_path, "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        print("  创建干净虚拟环境（首次较慢）…")
        if run([sys.executable, "-m", "venv", venv_path]) != 0:
            print("[X] 创建虚拟环境失败。")
            input("按回车退出…")
            return
    else:
        print("  使用已有虚拟环境")

    # ---- 步骤 2：安装依赖 ----
    print("[2/3] 安装依赖…")
    run([venv_python, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    if run([venv_python, "-m", "pip", "install", *DEPS, "-q"]) != 0:
        print("[X] 依赖安装失败，请检查网络。")
        input("按回车退出…")
        return

    # ---- 步骤 3：打包 ----
    print("[3/3] 开始打包（几分钟，别关窗口）…")
    args = [venv_python, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--onefile", "--windowed", "--name", NAME]

    if os.path.exists("logo.ico"):
        args += ["--icon", "logo.ico"]
    elif os.path.exists("logo.png"):
        args += ["--icon", "logo.png"]

    bg = next((b for b in BG_CANDIDATES if os.path.exists(b)), None)
    if bg:
        args += ["--add-data", f"{bg};."]

    for data_file in ("ocr_model.onnx", "ocr_charset.json"):
        if os.path.exists(data_file):
            args += ["--add-data", f"{data_file};."]
            print(f"  OCR 数据：{data_file} ({os.path.getsize(data_file)/1024/1024:.1f} MB)")
        else:
            print(f"  [!] 缺少：{data_file}")

    for m in EXCLUDES:
        args += ["--exclude-module", m]
    args += ["--collect-all", "webview", "--collect-all", "onnxruntime"]
    args.append(ENTRY)

    code = run(args)
    if code == 0:
        exe = os.path.join(here, "dist", f"{NAME}.exe")
        if os.path.exists(exe):
            size_mb = os.path.getsize(exe) / 1024 / 1024
            print(f"\n[OK] 打包完成！")
            print(f"  成品：dist/{NAME}.exe ({size_mb:.1f} MB)")
        else:
            print("\n[X] 打包似乎成功但找不到 exe 文件。")
    else:
        print("\n[X] 打包失败。请把窗口里【最后 20 行】的报错发给开发者。")
    input("按回车退出…")


if __name__ == "__main__":
    main()
