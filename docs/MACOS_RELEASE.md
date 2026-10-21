# Mac 预发布与正式分发准备

当前版本：`2.4.1-preview.1`，预发布标签 `macos-v2.4.1-preview.1`。应用内的数字版本为 2.4.1，发布渠道单独记录。版本源为 `macos/app_version.py`。

[预发布下载页](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/macos-v2.4.1-preview.1)；对应源码、构建环境和检查证据见 [发布记录](progress/2026-10-21-macos-release.md)。

## 当前可完成的发布

无需本地 Mac 或 Apple 证书，也可以使用 GitHub 原生 Mac runner 构建、验证和生成 ad-hoc 签名测试包，再发布到 GitHub Releases 的 **Pre-release**。预发布不标记为 Latest，不替换原 Windows 稳定版，不声称已通过 Apple 公证或真人业务验收。

构建时写入应用版本和构建号，再重新封装外层应用签名。原生检查必须再次验证签名、版本、OCR、配置、窗口、本机 API 和 SSE。发布包附校验值、源码提交、平台版本与原始验证报告，避免把旧包重新标成新提交。

## 发布流程

1. 将版本和相关改动合入 main，等待 **macOS build and offline verification** 两种架构均成功。
2. 在 GitHub Actions 的 **Publish verified macOS preview** 工作流填入该成功运行的 ID，以及 `macos/app_version.py` 中的精确标签。
3. 工作流确认来源为本仓库 main 上成功的 Mac 验证运行，下载其 artifacts。
4. 检查两个架构的源码提交、应用版本、SHA-256、原生验证报告及发布范围，再生成统一清单和校验文件。
5. 先建立带全部资产的草稿，确认服务器接收的文件名、大小及可用的 SHA-256 摘要，再发布为 Pre-release。

遇到已存在的标签或发布条目时停止，不覆盖资产；上传中断时保留草稿供检查，不能把不完整草稿当成已发布。

发布工作流只有手动入口，不在 PR 上使用写权限，也不读取 Apple 签名密钥。它只能发布当前预发布标签，不支持把未公证包标为正式版。

## 下载内容

- `QiangKeWeb-2.4.1-macos-arm64.zip`：M 系列 Mac 应用。
- `QiangKeWeb-2.4.1-macos-x86_64.zip`：Intel Mac 应用。
- `verification-arm64.zip` / `verification-x86_64.zip`：对应原生报告及依赖版本。
- `release-manifest.json`：两个架构的来源、版本、校验值与验证范围。
- `SHA256SUMS.txt`：以上文件的校验值。

解压后得到 `.app`，无需安装 Python。当前自动化只在 macOS 15 环境验证；最低兼容版本尚未通过人工验收。下载后的系统提示应如实反馈，不要求关闭 Gatekeeper。

## 完成 Developer ID 签名与公证还需要什么

2026-10-21 检查时，本仓库没有配置签名相关 GitHub Secrets。维护者目前没有可用的测试 Mac，因此人工验收仍待安排。GitHub Mac runner 可以承载后续签名/公证任务，但不能代替证书权限和真人验收。

准备正式的非 App Store 分发时，需要：

| 项目 | 用途 | 配置方式 |
| --- | --- | --- |
| Apple Developer Program 团队权限 | 申请与管理 Developer ID 证书 | 在 Apple 开发者账户中完成 |
| Developer ID Application 证书及对应私钥 | 为应用和所有原生依赖签名 | 准备带私钥的加密 `.p12`，通过 GitHub Secrets 或受控钥匙串使用 |
| 证书密码及签名身份 | 在临时钥匙串导入证书并选择正确团队 | 仅存放在 Secrets，不写入仓库 |
| Apple 公证认证 | 通过 `notarytool` 提交 | 使用有公证权限的 App Store Connect API key，或 Apple 官方支持的其他认证方式 |
| 一位有 Mac 的验收者 | 下载打开、文件对话框、键盘、休眠唤醒和本人账号功能 | 提交去除个人信息的系统/场景结果 |

证书、私钥、API key 和密码不要发到聊天或作为普通文件提交。正式签名路径需在上述条件可用后实现并验证：签名并启用 Hardened Runtime → 原生启动测试 → notarytool 提交并确认 Accepted → stapler 附票并校验 → Gatekeeper 验收 → 重新生成分发包及校验值。

仅有一个 `.cer` 文件而没有对应私钥，或只有 ad-hoc 签名，都不能完成 Developer ID 签名。公证成功也不表示学校接口或业务行为已经通过验收。

## 人工验收待办

- 下载对应芯片版本，记录 macOS 版本、芯片和系统打开提示。
- 文件对话框保存/取消/加载、中文输入、窗口缩放与正常退出。
- 插电及电池条件下的锁屏、休眠/唤醒；核对状态，不假定断网期间仍有请求成功。
- 使用本人账号依次确认登录、批次、查询和课表；选课/退选按本人明确操作单独验收。
- 不上传包含密码、Cookie、邮箱授权码或个人课表的完整日志/截图。

## 依据

- [Apple：Developer ID 签名](https://developer.apple.com/developer-id/)
- [Apple：Mac 软件公证](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [PyInstaller：Mac 代码签名](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing)
