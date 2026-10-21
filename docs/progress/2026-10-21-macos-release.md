# Mac 2.4.1 Preview 1 发布记录

- 日期：2026-10-21（Asia/Shanghai）
- 基准：`cd312edfb1c191af438c2a773ba8fe3e70b902a7`
- 成品源码提交：`b545278dd41323677afda7d426cd25273ceb5757`
- 状态：两端原生构建及预发布工作流通过，六份资产已公开下载。
- 维护者当前没有可用的 Mac；仓库没有签名相关 Secrets。

## 范围

补充此前测试包缺失的版本/构建号、可追溯发布资产和预发布工作流，重新验证后发布第一个 Mac 预发布版。应用数字版本/构建号均为 `2.4.1`，渠道为 `preview.1`，标签为 `macos-v2.4.1-preview.1`。Developer ID 签名、公证和真实账号/休眠唤醒仍待证书及人工条件，不标为完成。

## 验证

- Windows 本地：语法检查、20 项单元测试和版本输出通过；版本输出为 `2.4.1-preview.1`。
- 发布校验覆盖来源运行/提交、下载校验值、应用版本和原生 GUI 报告；不接受 PR 构建、旧版本包、失败的检查或已存在的发布标签。
- [PR #2](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/pull/2) 的 [两端原生检查](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/39576312623) 通过后合入 main。
- [成品对应的 main 原生构建](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/39576802105)：Apple Silicon 与 Intel 均成功；源代码提交与上述成品提交一致。
- [main 跨平台检查](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/39576802041)：Windows/Ubuntu × Python 3.10/3.12 的语法、单元测试和资源检查均通过。
- 原生报告环境为 macOS `15.7.9`、Python `3.12.10`。两端版本元数据、复制到含空格路径、ad-hoc 签名、合成 OCR、配置往返、本机 HTTP/token、原生 WebView、JavaScript API 和 SSE 均通过。
- [预发布工作流](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/39577450857) 成功：核对两种架构的资产后，先上传完整草稿，再公开为 Pre-release。发布后再次核对六份资产的大小/摘要、标签提交及 `draft=false`、`prerelease=true`；稳定版仍为 `v2.4`。

## 交付与限制

- [下载页](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/macos-v2.4.1-preview.1) 包含两份应用压缩包、两份验证报告压缩包、`release-manifest.json` 和 `SHA256SUMS.txt`。
- 仓库说明及项目 skill 补充本次已验证的发布流程；skill 结构校验通过。
- 仅为 ad-hoc 签名、未公证的预发布版，不替换 Windows `v2.4` 稳定版。没有验证更早的 macOS 系统，不把 CI 启动检查等同于下载后的 Gatekeeper 验收。
- 真人登录、查询、选课、退选、文件对话框、休眠/唤醒和下载后打开仍待验收；安卓/iOS 本次没有安装包。
- 正式分发所需的 Developer ID 证书及私钥、公证凭据和 Mac 测试人员见 [发布指南](../MACOS_RELEASE.md)。凭据不提交代码或聊天，通过钥匙串/GitHub Secrets 配置。
