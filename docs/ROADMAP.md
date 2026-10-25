# macOS、安卓与 iOS 改造计划

基准：`ef489230a93b32549967e31f135fbfcf67d2b63d`，2026-10-21 制定。原程序为 Python + PyWebView + 内嵌网页界面，本机 HTTP/SSE 连接后端，ONNX Runtime 运行 OCR。当前 Windows 构建脚本不能直接生成 Mac 应用或手机安装包。

## 阶段与验收

| 阶段 | 目标及工作 | 退出条件 |
| --- | --- | --- |
| P0 开发基础 | 仓库规则、开发流程、测试矩阵、证据记录 | 文档可发现，原存档保持不变 |
| P1 macOS 最小验证 | 复用桌面引擎；补启动入口、资源/配置路径、防休眠与退出清理；增加两种架构的 CI 构建和离线/GUI 检查 | 原生 .app 构建、OCR、本机服务、GUI 自动检查通过；人工验收与签名状态单列 |
| P2 公共能力整理 | 从已验证的桌面路径提取引擎和界面；统一任务/配置格式；增加任务持久化、恢复及异常分类 | Windows 回归通过，恢复场景可重复验证 |
| P3 安卓技术验证 | 验证认证会话、模型预处理/推理、界面与原生通信、生命周期和执行服务 | 最小 APK 在目标设备上通过上述链路；据此确定最终技术栈 |
| P4 安卓功能版 | 手机 UI、网络恢复、通知、任务状态存储、后台限时和省电处理 | 测试矩阵中的目标设备/场景通过，真实挂机边界可说明 |
| P5 iOS 技术验证与功能版 | 共用手机 UI；实现 iOS 请求/OCR/安全存储接口；前台执行及中断恢复；验证可用的后台处理能力 | Xcode 构建、真机安装和指定场景通过，后台限制如实说明 |
| P6 分发与持续维护 | 签名、公证/TestFlight、安装包校验、配置迁移和版本说明 | 发布包可追溯至提交与验证记录 |

## 当前进度与 macOS 首阶段范围

截至 2026-10-25 的进度：

| 阶段 | 实际状态与待验收范围 |
| --- | --- |
| P0 | 已完成项目规则、流程和证据记录。 |
| P1 | Apple Silicon / Intel 原生构建、离线 OCR 与 GUI 自动检查通过；人工业务待验收。Mac 保持现有 ad-hoc、未公证预览，付费签名公证按用户选择暂缓。 |
| P2 | 已以最小安卓适配复用桌面认证/查询，并实现独立持久化与恢复策略；公共引擎/界面完整拆分、统一全部平台格式尚未完成。 |
| P3 | 已确定原生 WebView + Chaquopy + ONNX Runtime Android 路线；API 26、35、36 的 x86_64 模拟器链路验证通过，ARM64 实体设备待验收。 |
| P4 | 预览功能已实现，包含手机/平板 UI、串行限时任务、网络恢复、通知停止与中断核对；模拟器自动场景通过，真实学校业务与厂商后台策略待验收。 |
| P5 | iOS 尚未实现，未建立 Xcode/IPA 或真机验证链路。 |
| P6 | Mac 已有未公证预览；安卓 `android-v0.1.0-preview.1` 已建立固定签名、来源记录与下载校验。ARM64 安装、覆盖更新和真人业务分别待验收。 |

Mac 证据见 [首次阶段记录](progress/2026-10-21-macos.md) 和 [预发布记录](progress/2026-10-21-macos-release.md)；安卓对应 main 提交 `8af69ea0571e1f9d49143c930c6a350c8eff80b8`、[main 原生运行](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40166135205)，详情见 [安卓发布记录](progress/2026-10-25-android-release.md)。

- 增加独立 `macos/` 入口和构建脚本，先不移动或重写完整业务引擎。
- 资源随应用分发，从任意工作目录启动也能找到模型、字符表及背景。
- 配置默认落到用户可写位置；本机 HTTP 服务仍只绑定回环地址。
- 补 Mac 防休眠与退出清理；休眠/唤醒后的业务恢复属于后续验证项。
- Apple Silicon 和 Intel 各自构建。先生成 ad-hoc 测试包，Developer ID 签名、公证及下载后体验另行验收。
- 所有自动检查使用合成图片和回环服务，不进行真实学校操作。

## 手机端路线与 UI

安卓已采用本地响应式网页 + 原生 Java Activity/WebView + Chaquopy Python 会话/任务适配 + ONNX Runtime Android。已验证的链路与实际构建命令维护在 [安卓指南](ANDROID.md)。原候选 Capacitor/PyWebView/Buildozer 未作为当前实现；iOS 路线仍需通过自身 OCR、请求与生命周期技术验证，不能从安卓通过推断 iOS 可用。

- 手机单栏、课程卡片、独立任务/日志页面；平板及桌面按宽度使用多栏。
- 适配 360–430 CSS 像素宽度、横竖屏、安全区、软键盘、大字体和触摸操作。
- 显示网络、登录、任务状态及最后同步时间，恢复界面时从实际执行层重新取状态。
- 安卓公开包使用固定应用 ID/预览证书，更新递增 versionCode；debug 数据单独隔离。覆盖更新和迁移仍待实际验收，更新后核对任务并手动恢复，不承诺更新期间任务连续运行。
- 密码与授权码使用系统安全存储，默认不进入导出配置、日志或截图。

## 断网与任务恢复

| 场景 | 预期处理 |
| --- | --- |
| 无网络/飞行模式 | 保存进度，暂停发送请求，显示等待网络 |
| Wi-Fi/流量切换 | 监听变化，检查目标服务，必要时重建会话 |
| 校园网需要认证 | 与普通断网区分，提示用户完成网络认证 |
| 提交后响应丢失 | 标记结果待核对，查询已选课程后再决定重试；即使退选使用 GET，也不能当作可安全重复的读操作 |
| 登录过期 | 合并重新登录操作，限制连续失败次数 |
| 服务故障/限流 | 有上限的退避重试，按服务响应调整 |
| 错过计划时间 | 按任务允许延迟窗口处理，过期不盲目执行 |
| 系统回收进程/重启 | 恢复记录，核对结果、计划和停止状态，再恢复任务 |

## 后台执行边界

安卓已实现限时前台 dataSync 服务、通知停止、离线释放唤醒锁和超时清理，并在上述三种 x86_64 模拟器验证相关路径；长时间锁屏/Doze 和各厂商省电策略仍待验收。前台服务不等于无限运行。iOS 尚未实现，不能承诺其任意锁屏长期执行。首版以本机限时执行和手动中断恢复为范围。

如需手机断网或锁屏后仍长期执行，可另加电脑托管模式：任务在联网电脑运行，手机通过配对和认证查看/控制；不能直接公开当前仅供本机使用的 HTTP 接口。该模式不包含在 P1。

## 参考资料

- [PyWebView 平台与打包](https://pywebview.flowrl.com/guide/freezing.html)
- [PyInstaller Mac 构建](https://pyinstaller.org/en/stable/usage.html#building-macos-app-bundles)
- [ONNX Runtime Mobile](https://onnxruntime.ai/docs/get-started/with-mobile.html)
- [Capacitor](https://capacitorjs.com/docs)
- [安卓网络状态](https://developer.android.com/develop/connectivity/network-ops/reading-network-state)
- [安卓后台服务时限](https://developer.android.com/develop/background-work/services/fgs/timeout)
- [安卓 Doze](https://developer.android.com/training/monitoring-device-state/doze-standby)
- [iOS 持续后台处理](https://developer.apple.com/documentation/BackgroundTasks/performing-long-running-tasks-on-ios-and-ipados)
