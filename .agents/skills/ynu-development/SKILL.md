---
name: ynu-development
description: "维护 YNU-Course-Selection-Assistant 的桌面代码、平台适配和构建验证；在本仓库实现功能、修复问题、检查 Mac 构建或推进安卓/iOS 阶段时使用。"
---

# YNU 项目开发

## 先定位任务与证据

将本 skill 所在目录的上三级作为仓库根目录。先读取 [项目规则](../../../AGENTS.md) 和 [开发流程](../../../docs/DEVELOPMENT.md)，再按当前任务读取：

- 平台范围/下一阶段：[改造计划](../../../docs/ROADMAP.md)。
- 测试和真实设备验收：[验收矩阵](../../../docs/TEST_MATRIX.md)。
- Mac 构建/排错：[Mac 指南](../../../docs/MACOS.md) 和 [首次验证记录](../../../docs/progress/2026-10-21-macos.md)。
- Mac 预发布/正式分发：[发布指南](../../../docs/MACOS_RELEASE.md) 和 [预发布记录](../../../docs/progress/2026-10-21-macos-release.md)。

检查当前分支、改动和用户授权。继续已有工作，不把计划当作实现结果，不重新要求用户确认已经授权的例行操作。

## 选择最小相关验证

- 纯文档改动：检查链接、范围及 `git diff --check`。
- 桌面运行代码：运行 `python -m unittest discover -s tests -v` 和相关语法检查。
- 资源/OCR/本机接口：运行 `python macos/main.py --self-test --report reports/source-runtime.json`。此命令也能在非 Mac 上检查共享运行逻辑，但不能证明 Cocoa GUI 或 Mac 构建通过。
- Mac 原生 GUI：在 Mac 图形会话中运行 `python macos/main.py --gui-smoke-test --report reports/source-gui.json`，或使用当前提交的 Mac CI。
- 打包改动：按目标架构读取 `macos/constraints-<架构>.txt`，构建并运行 `macos/check_bundle.py`。具体命令只维护在 Mac 指南，不在 skill 复制一份。

当前有 arm64 和 x86_64 两条独立构建路径。首次验证时两者解析到不同版本的 ONNX Runtime；不要从一端成功推断另一端可用。依赖升级应检查对应原生 CI，不随意把两份约束合并为 universal2。

## 脆弱边界

- 活动桌面引擎目前仍在 `windows/`，Mac 入口复用它。`archive/` 是原始快照，不能用改写历史存档来修当前版本。
- Mac 验证必须覆盖复制到其它目录、不同工作目录、包内 OCR 资源、原生页面加载、JavaScript 到本机 API 和 SSE 回传。
- `macos/verify_runtime.py` 只使用合成图片和回环连接。不要为构建测试填入真实账号，也不要把实际选课/退选加入 CI。
- 进程终止、系统挂起和网络中断不同；修改恢复逻辑时按测试矩阵检查状态核对与防止重复提交。
- 手机端先验证 OCR、会话及执行层再确定技术栈。共用网页界面不能替代 Python 移植，也不能保证系统允许后台长期执行。

## 上传与交付

使用现有 GitHub 权限在用户授权范围内提交上传，保留并发改动。构建产物放在 artifacts/Releases，不提交到 Git；签名和正式发布按本次任务范围执行。

Mac 预发布通过发布工作流核对成功的 main 原生构建、提交、两种架构的报告和下载校验值，不能直接把 PR 构建改称主分支成品。已经存在的版本标签或发布不覆盖；ad-hoc 预发布与 Developer ID 签名、公证和人工验收分别记录。

读取与本次提交匹配的 CI 作业和 JSON 报告，报告实际架构、检查结果及构建链接。把以下状态分开：代码实现、自动检查、原生构建、原生启动、人工交互、真实学校业务和正式分发。上一提交的通过结果只有在相关代码未变时才能作为继承证据，并注明原提交。

最后更新当前阶段记录和必要的使用说明。记录尚未运行的检查及原因，不为通过一个阶段而自动扩展到其它平台或真实账号操作。
