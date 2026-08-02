# -*- coding: utf-8 -*-
"""
YNU 抢课助手 · PyWebView 版  一键打包脚本（Python 版，避开 bat 中文编码坑）
用法：把本文件和 qiangke_web.py（以及可选 logo.ico/logo.png、background.png）放同一文件夹，
      命令行运行：  python build.py
成品在 dist/QiangKeWeb.exe
"""
import os
import sys
import subprocess

DEPS = ["pyinstaller", "pywebview", "requests", "ddddocr", "yagmail", "pillow"]
NAME = "QiangKeWeb"          # 用纯英文名，避免中文在打包各环节出问题
ENTRY = "qiangke_web.py"
BG_CANDIDATES = ("background.png", "background.jpg", "background.jpeg", "bg.png", "bg.jpg")
# 本程序用不到的大库，明确排除（否则 conda 环境里的 torch 等会被一起打包，体积暴涨且易失败）
# 注意：不要排除 cv2 / numpy / PIL / onnxruntime —— ddddocr 依赖它们！
EXCLUDES = ["torch", "torchvision", "torchaudio", "matplotlib", "scipy", "pandas",
            "tkinter", "IPython", "notebook", "jupyter", "sympy", "tensorflow",
            "sklearn", "scikit-learn", "numba", "PyQt5", "PyQt6", "PySide2", "PySide6",
            "wx", "pygame"]


def run(cmd):
    print(">>", " ".join(cmd))
    return subprocess.run(cmd).returncode


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    if not os.path.exists(ENTRY):
        print(f"× 找不到 {ENTRY}，请把本脚本和 {ENTRY} 放在同一文件夹。")
        input("按回车退出…")
        return

    print("[1/2] 安装依赖（首次较慢）…")
    if run([sys.executable, "-m", "pip", "install", *DEPS]) != 0:
        print("× 依赖安装失败，请检查 Python/pip/网络。")
        input("按回车退出…")
        return

    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--name", NAME]

    # 图标：优先 logo.ico，其次 logo.png（PyInstaller 配合 Pillow 自动转）
    if os.path.exists("logo.ico"):
        args += ["--icon", "logo.ico"]
        print("图标：logo.ico")
    elif os.path.exists("logo.png"):
        args += ["--icon", "logo.png"]
        print("图标：logo.png（自动转 ico）")
    else:
        print("图标：无（用默认）")

    # 背景图：打进 exe
    sep = ";" if os.name == "nt" else ":"
    bg = next((b for b in BG_CANDIDATES if os.path.exists(b)), None)
    if bg:
        args += ["--add-data", f"{bg}{sep}."]
        print(f"背景图：{bg}")
    else:
        print("背景图：无（用内置暗色渐变）")

    for m in EXCLUDES:
        args += ["--exclude-module", m]
    args += ["--collect-all", "webview", "--collect-all", "ddddocr", "--collect-all", "onnxruntime", ENTRY]

    print("[2/2] 开始打包（几分钟，别关窗口）…已排除 torch/scipy 等无关大库")
    code = run(args)
    if code == 0:
        print(f"\n✔ 完成！成品：dist{os.sep}{NAME}.exe")
        print("  直接双击运行；发给同学也只需这一个 exe。")
        print("  界面依赖系统 WebView2 运行时（Win10/11 一般自带）。")
    else:
        print("\n× 打包失败。请把窗口里【最后 20 行】的报错发给开发者。")
        print("  常见原因：磁盘空间不足；或某个库的 hook 报错。")
        print("  建议：在干净的虚拟环境里打包更稳（conda 全家桶容易带进无关大库）：")
        print("        python -m venv qk & qk\\Scripts\\activate & python build.py")
    input("按回车退出…")


if __name__ == "__main__":
    main()
