# 运行与构建

## 当前 Windows V2.4

`windows/` 已放齐一个入口 `qiangke_web.py`、`lite_ocr.py`、`ocr_model.onnx`、`ocr_charset.json`、图标、背景与 `build.py`。主源码与网盘 V2.4 文件逐字节相同；独立 OCR 模块从开发记录指向的旧打包目录找回。

在 Python 3.10+ 环境中安装 `windows/requirements.txt` 后运行入口。打包时先切换到 `windows/`，运行 `python build.py`。脚本创建独立的 `.build_venv`，安装 PyInstaller 等依赖，输出 `dist/QiangKeWeb.exe`；首次需要联网下载依赖。

只保留一个 `qiangke_web*.py` 入口。原始脚本在发现多个入口时按文件修改时间选择，Git 检出后的文件时间不能可靠表示版本顺序。

模型与字符表必须随程序分发；仅复制主程序会导致 OCR 缺失。模型数据由原始打包脚本加入成品，`lite_ocr.py` 会由 Python 模块依赖分析收集。

## 历史版本

- `archive/windows/source/` 保留七个原始源码快照；V1.0 至 V2.2.1 使用 ddddocr。
- `archive/windows/build-pre-2.3/` 是原来的早期构建目录，随附主源码内容与 V2.0 相同。
- `archive/windows/build-2.3-plus/` 是原来的 V2.3 构建目录，包含内嵌 OCR 的 V2.3 主源码。
- 历史标签是按文件日期重建的增量快照，不保证每个标签当时已经包含后来归档的全部构建资源。完整可浏览的归档位于最新 main。

## 复现边界

原始资料没有锁定依赖版本或完整的历史构建环境，本次未杜撰锁文件，也不保证重新生成的 EXE 与存档逐字节相同。此处保留原始构建逻辑，并给出独立环境运行步骤。没有运行历史脚本去修改系统环境或进行真实选课操作。
