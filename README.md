# YNU选课助手

云南大学选课辅助工具，提供 **Windows 图形界面**与 **Linux 命令行版本**。

[下载 Windows V2.4](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v2.4) · [所有版本](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases) · [更新日志](CHANGELOG.md) · [历史与时间来源](docs/HISTORY.md)

跨平台开发：[开发流程](docs/DEVELOPMENT.md) · [macOS / 安卓 / iOS 改造计划](docs/ROADMAP.md) · [验收矩阵](docs/TEST_MATRIX.md) · [当前验证进度](docs/progress/2026-10-21-macos.md)。Mac 验证先行，移动端仍处于计划阶段。

## 能做什么

| 功能 | Windows V2.4 | Linux 存档 |
| --- | --- | --- |
| 查询课程、选课批次、已选课程、个人课表 | 支持 | 支持 |
| 定时、多课程任务、运行日志、可选邮件通知 | 支持 | 支持 |
| 手动退选 | 界面确认 | 命令行命令 |
| 按当前页面识别课程类别，包括方案外/跨专业 | 支持 | 保留原始静态类别 |
| 使用方式 | 桌面窗口；缺少 PyWebView 时可用本地浏览器界面 | 配置文件与命令行 |

## Windows 使用

从 [V2.4 下载页](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v2.4) 下载 `QiangKeWeb-v2.4-windows.exe`。这是原有成品的归档，未在本次迁移中重新编译。页面同时提供 SHA-256 校验文件。

打开后填写本人学号和密码，获取当前批次与课程类型，查询并加入目标课程，再根据界面配置启动时间。旧代码包含默认批次，但它不保证适用于当前学期，应先获取实际开放批次。

源码运行（Python 3.10+）：

```powershell
git clone https://github.com/Eric10Z4/YNU-Course-Selection-Assistant.git
cd YNU-Course-Selection-Assistant/windows
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe qiangke_web.py
```

桌面窗口需要系统可用的 WebView2 环境。需要自行打包时，在 `windows` 目录执行 `python build.py`；脚本会建立 `.build_venv` 并生成 `dist/QiangKeWeb.exe`。详见 [构建说明](docs/BUILD.md)。

## Linux 使用

```bash
cd linux
bash setup.sh
source venv/bin/activate
# 在本机编辑 config.json，填入本人账号和所需配置
python qiangke_cli.py batches
```

配置字段、课程查询与运行命令见 [原始 Linux 说明](linux/README_LINUX.md)。该压缩包没有明确版本号，不将它标为 Windows V2.4 的等价版本。

## 目录

```text
windows/           当前 V2.4 源码、找回的 OCR 模块、模型和构建资源
linux/             原始 Linux 压缩包解出的文件
archive/windows/   各版原始源码与两套打包工具，保持字节内容不变
archive/linux/     原始 Linux 压缩包
docs/              构建、下载、时间证据与文件清单
CHANGELOG.md       依据逐版源码差异重建的更新日志
```

## 版本与完整性

七个 Windows 源码版本从 PX0 V1.0 到 V2.4 均已保存，并建立版本标签；另有无对应源码的 PX10 成品存档。Windows 可执行文件放在 Releases 中，不放入 Git 源码历史。完整清单见 [下载与校验](docs/RELEASES.md)。

历史 Git 提交是本次按现存文件重建的：作者时间与提交者时间均使用对应的网盘修改时间，恢复的 `lite_ocr.py` 使用其旧目录修改时间。多个早期版本共享同一网盘时间，保留原值。新增仓库说明使用本次整理时间。详情见 [历史说明](docs/HISTORY.md)。

## 使用与配置

本项目不是学校官方客户端。仅使用本人有权操作的账号，并遵守学校选课规则。保存的配置可能含明文密码或邮箱授权码，勿将实际配置、日志、Cookie 或抓包文件上传到仓库；`.gitignore` 已忽略常见文件。停止任务可用界面停止按钮或命令行中断。

本次验证范围见 [验证记录](docs/VALIDATION.md)。未进行真实登录、选课、退选或当前学期接口兼容性测试。原始代码及素材的授权说明见 [NOTICE](NOTICE.md)。
