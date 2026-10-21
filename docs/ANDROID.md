# 安卓预览版开发与使用

## 范围与路线

当前实现面向 Android 8.0/API 26 及以上的 64 位 ARM 手机/平板，另外包含 x86_64 用于模拟器验证。32 位设备不在首版范围。界面为本地响应式网页，原生 Java Activity/WebView 承载，Chaquopy 复用现有 Python 认证和查询引擎，ONNX Runtime Android 运行原有 OCR 模型。

选择这条路线是为了先验证现有模型、Cookie 会话和请求语义，不提前重写全部业务。构建时复制 `windows/qiangke_web.py`、`desktop_support.py`，不修改桌面入口；手机任务循环和页面分别位于 `android/app/src/main/python/` 与 `assets/mobile/`。没有依赖桌面 PyWebView、Pillow、NumPy 或 Python onnxruntime wheel。

## 使用

1. 安装 APK，进入“账号与设置”，填写本人学号和密码，登录并获取批次。应用首次打开不会发送学校请求。
2. 课程页查询或手动添加教学班；可查看已选和课表、明确确认后退选。查询首版最多获取前五页，可用关键词缩小范围。
3. 任务页设置间隔、运行时长与可选计划时间，点击开始并允许通知。通知栏提供停止入口。
4. 网络恢复后先核对登录和已选；提交响应丢失时进入待核对状态，不直接重发。不能确认时请在学校系统人工核对，再使用对应确认入口。

首版采用串行提交，间隔至少一秒，默认运行三十分钟，单次最长三小时；不直接照搬桌面的并发齐射和高峰增强。定时、断网等待均计入运行时长，计划时间不能超出本次运行窗口。邮箱提醒暂未移植。

## 网络、后台与恢复

- 监听默认网络及认证状态，区分断网、需认证、网络未验证。连上 Wi-Fi 不能证明学校可达；实际查询错误单独处理。
- 请求不做传输层自动重放或自动重定向。登录/查询有请求次数和时间预算；连续失败会退避并暂停。
- 每次选课/退选在发送前原子保存待核对记录；退选虽使用 GET，仍按修改操作处理。网络切换、重启恢复和结果不明都先查询已选，按批次核对；结果仍不明确时不自动重试。
- 前台服务只由用户从可见页面启动，持续展示通知，持有有限期唤醒锁；离线等待释放唤醒锁。服务超时/停止时释放资源，系统结束或更新后不自动恢复。
- Android 15+ 的 dataSync 前台服务存在后台累计时限；Doze 和厂商策略仍会限制执行。前台服务不能保证无限挂机、准点执行或强制停止后继续运行。
- 不申请精确闹钟、开机自启或绕过省电限制。任务需要长期稳定执行时，应另行设计电脑托管模式。

## 隐私与 UI

界面仅加载应用内白名单资源，原生桥只暴露指定操作，不启动局域网服务器、不加载远程页面。学校请求沿用 Python Session 的 Cookie/token 和 HTTPS 校验，认证信息不进入 WebView Cookie 或任务日志。

密码默认只保留在本次进程，选择“记住密码”后才通过 Android Keystore/AES-GCM 加密保存；配置和任务记录位于私有目录并禁用系统备份。任务记录不包含密码、token、Cookie 或邮箱授权码，日志隐藏账号密码与接口 URL。不要向仓库或 CI 填入真实凭据。

布局在小屏使用单栏，平板/横屏按宽度扩展；输入框与触摸按钮有最小高度，适配系统字体、状态栏/刘海/导航区和软键盘。自动检查不代表全部厂商或所有字体组合均已验收。

## 构建与验证

使用 JDK 17、Python 3.13、Android SDK 36 和仓库内 Gradle 8.13 wrapper：

```sh
python -m unittest discover -s tests -v
android/gradlew -p android assembleDebug assembleDebugAndroidTest lintDebug
android/gradlew -p android connectedDebugAndroidTest
```

设备检查覆盖原生模型合成推理、Python 恢复场景、本机加密配置、实际 WebView→Python 桥、小屏横向溢出、通知停止及超时回调清理。所有学校交互场景使用合成会话，不访问真实学校服务。Android 8/15/16 模拟器的实际结果及构建链接记入 [阶段记录](progress/2026-10-21-android.md)。

当前 APK 使用 Android 的测试签名，真实业务和各厂商后台策略待验收。公开预览前固定专用预览签名，避免后续更新因签名变化必须卸载；密钥不提交仓库。

## 官方资料

- [Chaquopy 构建与 Python 版本](https://chaquo.com/chaquopy/doc/current/android.html)
- [ONNX Runtime Android](https://onnxruntime.ai/docs/get-started/with-java.html)
- [网络状态](https://developer.android.com/develop/connectivity/network-ops/reading-network-state)
- [前台服务时限](https://developer.android.com/develop/background-work/services/fgs/timeout)
- [Doze 与待机](https://developer.android.com/training/monitoring-device-state/doze-standby)
