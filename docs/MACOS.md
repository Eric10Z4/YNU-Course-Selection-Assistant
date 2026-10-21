# macOS 运行、构建与验证

macOS 入口复用 `windows/` 中的当前桌面引擎；目录名称是历史布局，不表示需要 Windows。首次验证的范围及证据见 [进度记录](progress/2026-10-21-macos.md)。

## 源码运行

在仓库根目录使用独立 Python 3.12 环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r macos/requirements-build.txt -c "macos/constraints-$(uname -m).txt"
python macos/main.py
```

使用与目标架构匹配的 Python 和原生依赖。Apple Silicon 为 `arm64`，Intel 为 `x86_64`。目前不构建 universal2，最低可用系统版本也必须通过相应机器实测，不能从高版本 CI 成功推断。

## 离线与原生 GUI 验证

```bash
python -m unittest discover -s tests -v
python macos/main.py --self-test --report reports/source-runtime.json
python macos/main.py --gui-smoke-test --report reports/source-gui.json
```

`--self-test` 验证资源、合成图片 OCR、配置读写和回环 HTTP 的页面/令牌/停止接口。`--gui-smoke-test` 使用真实桌面入口加载原生 WebView，检查 JavaScript 调用本机停止接口，以及 SSE 日志进入界面，然后自动退出。

两种验证均没有账号信息，Python 网络连接限制为回环地址；不登录学校服务，不选课/退选。GUI 检查需要可用的 macOS 图形会话，关闭前必须实际完成检查才会成功。

## 打包

```bash
python macos/build.py --arch arm64
# Intel Mac 改用 --arch x86_64
python macos/check_bundle.py \
  --app dist/macos/arm64/QiangKeWeb.app \
  --arch arm64 --reports reports
```

生成 `dist/macos/<架构>/QiangKeWeb.app`。构建脚本使用 PyInstaller 的 onedir/windowed 模式，模型、字符表和背景随包收集。非 macOS 可用 `python macos/build.py --arch arm64 --dry-run` 检查命令，但不能实际构建 Mac 应用。

`check_bundle.py` 将应用复制到带空格的临时目录，以一个空目录为工作目录运行，验证可执行文件架构、ad-hoc 签名、离线运行与原生 GUI。子进程有时间上限，失败不会作为通过记录。

## CI 与测试包

版本源、可追溯预发布包及发布工作流见 [Mac 发布指南](MACOS_RELEASE.md)。

入口：[Mac 构建工作流](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/workflows/macos.yml)。首次固定依赖后的完整结果见 [运行 #39572967451](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/39572967451)。

`.github/workflows/macos.yml` 对相关路径的 PR、main 推送或手动触发运行，分别在 `macos-15` / `macos-15-intel` 上构建 arm64 / x86_64。成功后保存使用 ditto 打包的带版本应用 ZIP、原始验证报告压缩包和构建清单；另存 JSON 报告、运行输出和实际依赖版本。请下载对应运行的 artifact，不能把其它提交或单一架构的结果套用到当前版本。

构建使用隔离 runner；`constraints-arm64.txt` / `constraints-x86_64.txt` 保存首次原生验证通过的依赖组合，CI 同时约束版本并记录本次实际安装结果。它们是版本约束，不是带哈希的完整锁文件，不保证安装包逐字节复现。升级依赖需在对应架构重新验证。

首次基线中 arm64 使用 ONNX Runtime 1.31.0，Intel 使用 1.23.2，不能把一端的安装结果直接套用于另一端。

## 配置与电源行为

- 有原生文件对话框时由用户选择配置路径；取消保存不会自动覆盖默认文件。
- 对话框不可用时，Mac 默认保存在 `~/Library/Application Support/YNU-Course-Selection-Assistant/qiangke_config.json`；无窗口模式可加载该路径。
- 资源首先查找 PyInstaller 包内目录，源码运行也可以从非仓库工作目录找到数据。
- 运行任务时用系统 `caffeinate` 持有空闲睡眠断言，任务结束/退出时释放；它也监视应用进程，应用终止后释放。此机制不保证合盖后继续联网，也不代替断网或唤醒恢复验证。

配置仍可能包含明文密码或邮箱授权码。系统安全存储及无敏感信息的配置导出属于后续公共能力阶段；当前不要共享真实配置。

## 待人工验收及分发边界

自动检查通过仅代表记录的运行路径成立。仍需在真实 Mac 验收文件对话框、键盘输入、缩放、休眠唤醒、实际登录及业务行为。合成图片推理不代表真实验证码识别率。

当前产物是 PyInstaller ad-hoc 签名测试包，不是 Developer ID 签名、公证或 Mac App Store 版本。下载后的 Gatekeeper 体验、正式签名及公证在发布阶段处理，不默认引导用户关闭系统安全机制。

## 资料

- [PyInstaller Mac 应用](https://pyinstaller.org/en/stable/usage.html#building-macos-app-bundles)
- [GitHub macOS runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [PyWebView API](https://pywebview.flowrl.com/api/)
