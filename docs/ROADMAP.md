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

## macOS 首阶段范围

- 增加独立 `macos/` 入口和构建脚本，先不移动或重写完整业务引擎。
- 资源随应用分发，从任意工作目录启动也能找到模型、字符表及背景。
- 配置默认落到用户可写位置；本机 HTTP 服务仍只绑定回环地址。
- 补 Mac 防休眠与退出清理；休眠/唤醒后的业务恢复属于后续验证项。
- Apple Silicon 和 Intel 各自构建。先生成 ad-hoc 测试包，Developer ID 签名、公证及下载后体验另行验收。
- 所有自动检查使用合成图片和回环服务，不进行真实学校操作。

## 手机端路线与 UI

候选路线为共用响应式网页界面 + Capacitor 原生容器 + 平台执行/OCR 接口。安卓 PyWebView/Buildozer 可作为复用 Python 的对照验证。最终路线必须由 OCR、Cookie/认证、请求语义和后台执行的实验结果决定；Capacitor 不自带 Python 引擎，不能把桌面 Python 原样封装为完整手机应用。

- 手机单栏、课程卡片、独立任务/日志页面；平板及桌面按宽度使用多栏。
- 适配 360–430 CSS 像素宽度、横竖屏、安全区、软键盘、大字体和触摸操作。
- 显示网络、登录、任务状态及最后同步时间，恢复界面时从实际执行层重新取状态。
- 更新时迁移数据和配置，核对任务后才恢复；不承诺安装更新期间任务连续运行。
- 密码与授权码使用系统安全存储，默认不进入导出配置、日志或截图。

## 断网与任务恢复

| 场景 | 预期处理 |
| --- | --- |
| 无网络/飞行模式 | 保存进度，暂停发送请求，显示等待网络 |
| Wi-Fi/流量切换 | 监听变化，检查目标服务，必要时重建会话 |
| 校园网需要认证 | 与普通断网区分，提示用户完成网络认证 |
| 提交后响应丢失 | 标记结果待核对，查询已选课程后再决定重试；选课/退选 GET 请求也不是天然可重复的读操作 |
| 登录过期 | 合并重新登录操作，限制连续失败次数 |
| 服务故障/限流 | 有上限的退避重试，按服务响应调整 |
| 错过计划时间 | 按任务允许延迟窗口处理，过期不盲目执行 |
| 系统回收进程/重启 | 恢复记录，核对结果、计划和停止状态，再恢复任务 |

## 后台执行边界

安卓按适用服务类型、目标 SDK、Doze、服务超时及厂商省电策略验证；前台服务不等于无限运行。iOS 的后台时间和持续处理任务受系统控制，不能承诺任意锁屏长期执行。首版以本机前台执行和中断恢复为可验收目标。

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
