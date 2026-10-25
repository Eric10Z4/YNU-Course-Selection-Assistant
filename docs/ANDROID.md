# 安卓预览版开发与使用

## 下载与适配范围

[0.1.0 Preview 1 下载页](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/android-v0.1.0-preview.1) 提供 `YNU-Course-Assistant-0.1.0-preview.1.apk`。支持范围为 Android 8.0/API 26 及以上的 64 位 ARM 手机/平板，另含 x86_64 供模拟器使用；32 位设备不在首版范围。

2026-10-25 的发布基于 main 提交 `8af69ea0571e1f9d49143c930c6a350c8eff80b8`。PR 检查见 [PR 原生运行](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40165733327)，公开包的固定签名和设备证据见 [main 原生运行](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40166135205) 与 [发布记录](progress/2026-10-25-android-release.md)。API 26、35、36 的 x86_64 模拟器各通过 11 项原生设备检查，并全新安装、启动公开预览包；51 项单元测试中包含 31 项安卓合成场景。所有学校交互使用合成会话，未访问真实学校服务。ARM64 实体设备、真实验证码和学校业务仍待验收。

界面为本地响应式网页，由原生 Java Activity/WebView 承载；Chaquopy 复用 Python 认证和查询，ONNX Runtime Android 运行现有 OCR 模型。构建复制 `windows/qiangke_web.py` 和 `desktop_support.py`；手机任务适配位于 `android/app/src/main/python/`，页面位于 `android/app/src/main/assets/mobile/`。这是一层已验证的安卓适配，公共引擎的完整拆分重构仍未完成；没有依赖桌面 PyWebView、Pillow、NumPy 或 Python onnxruntime wheel。

## 使用

1. 安装 APK，进入“账号与设置”，填写本人学号和密码，登录并获取批次。应用首次打开不会发送学校请求。
2. 课程页查询或手动添加教学班；可查看已选和课表，明确确认后退选。查询首版最多获取前五页，可用关键词缩小范围。
3. 任务页设置间隔、运行时长与可选计划时间，点击开始并允许通知。通知栏提供停止入口。
4. 网络恢复后先核对登录和已选；提交响应丢失时进入待核对状态，不直接重发。不能确认时请在学校系统人工核对，再使用对应确认入口。

首版串行提交，间隔至少一秒，默认运行三十分钟，单次最长三小时；定时、断网等待均计入运行时长，计划时间不能超出本次运行窗口。首次提交前再次检查计划窗口，错过计划时间超过两分钟不再启动提交。邮箱提醒暂未移植。

## 网络、后台与恢复

- 监听默认网络及认证状态，区分断网、需认证、网络未验证。连上 Wi-Fi 不能证明学校可达；实际查询错误单独处理。
- 请求不做传输层自动重放或自动重定向。登录/查询有请求次数和时间预算；连续失败会退避并暂停。
- 每次选课/退选在发送前原子保存待核对记录；退选虽使用 GET，仍按修改操作处理。按账号、教学班和有效批次核对恢复记录；同一教学班 ID 在不同批次中的确认结果分开处理。
- 网络切换、重启恢复和结果不明都先查询已选；结果仍不明确时不自动重试。停止不等于已经在途的请求未生效，未确认结果仍需核对。
- 停止会取消排队中的启动和退选；退选登录期间收到停止后不再发送修改请求。系统结束或更新后不自动恢复任务。
- 前台服务只由用户从可见页面启动，持续展示通知，持有有限期唤醒锁；离线等待释放唤醒锁，排队准备期间保留服务。服务超时/停止时释放资源。
- Android 15+ 的 dataSync 前台服务存在后台累计时限；Doze 和厂商策略仍会限制执行。前台服务不能保证无限挂机、准点执行或强制停止后继续运行。
- 不申请精确闹钟、开机自启或绕过省电限制。长期电脑托管属于后续设计范围。

## 隐私与界面

界面仅加载应用内白名单资源，原生桥只暴露指定操作，不启动局域网服务器、不加载远程页面。学校请求沿用 Python Session 的 Cookie/token 和 HTTPS 校验，认证信息不进入 WebView Cookie 或任务日志。

密码默认只保留在本次进程，选择“记住密码”后才通过 Android Keystore/AES-GCM 加密保存；配置和任务记录位于私有目录并禁用系统备份。任务记录不包含密码、token、Cookie 或邮箱授权码，日志隐藏账号密码与接口 URL。不要向仓库或 CI 填入真实凭据。

小屏使用单栏，平板/横屏按宽度扩展；输入框与触摸按钮有最小高度，并处理系统字体、安全区和软键盘。模拟器检查覆盖 360 CSS 像素布局、160% 文字缩放和输入框可编辑性；不同平板、横屏、厂商键盘与全部系统字体组合仍需人工验收。

## 签名与覆盖更新

公开包的应用 ID 为 `io.github.eric10z4.ynu.android`，当前 `versionName` 为 `0.1.0-preview.1`、`versionCode` 为 `1`。专用预览证书 SHA-256 为：

```text
60136241dddbf677d63bb7d59b1e1c4d2868ea1a69fc598606d58da18eabc561
```

这是签名证书指纹；APK 文件本身的 SHA-256 以下载页 `SHA256SUMS.txt` 为准。后续覆盖更新需要保持应用 ID 和证书一致，并递增 `versionCode`。当前验证为全新安装，保留配置与任务记录的覆盖更新尚待专门验收；更新前请停止任务并核对待确认结果，更新后手动恢复。

debug 包使用 `io.github.eric10z4.ynu.android.debug`，与公开包的配置、任务和密钥存储隔离，不会自动迁移调试数据。合成场景只加入 debug Python 源集；公开 preview 包关闭调试，并通过递归归档检查排除 `test_android` 测试模块。

固定预览签名已按用户授权配置在可信 main 构建中，私钥与密码不提交仓库或下载包。PR 和未配置专用签名的本地构建可以使用临时测试签名，只能作为验证产物；公开发布必须核对上述固定指纹。

## 构建与验证

使用 JDK 17、Python 3.13、Android SDK Platform 36、Build Tools 35.0.0 和仓库内 Gradle 8.13 wrapper。从仓库根目录运行；Windows 构建可使用 `android/gradlew.bat`，设备脚本按 CI 的 Linux/Bash 环境运行。

```sh
python -m unittest discover -s tests -v
android/gradlew -p android assembleDebug assemblePreview assembleDebugAndroidTest lintDebug
python android/verify_apk.py --apk android/app/build/outputs/apk/preview/app-preview.apk --commit "$(git rev-parse HEAD)" --output android/app/build/outputs/apk/preview/build-manifest.json
```

`assemblePreview` 生成 `android/app/build/outputs/apk/preview/app-preview.apk`。`verify_apk.py` 检查来源提交、应用元数据、非调试状态、测试模块排除、arm64-v8a/x86_64、ELF 与 ZIP 的 16 KB 对齐及签名，并写入构建清单。可信 main CI 通过 `prepare_signing.py` 载入已授权的 GitHub Secrets；没有专用签名时清单会标为临时测试签名，不能据此认定可公开更新。

启动对应 API 的专用 x86_64 测试模拟器后运行，例如：

```sh
bash android/run_device_checks.sh 35
```

分别用 API 26、35、36 运行。脚本调用 `connectedDebugAndroidTest`，保存 debug 设备结果，再通过 `preview_smoke.py` 全新安装非调试公开包并确认 WebView 到 Python 的空闲状态；报告位于 `reports/android-<API>/`。全新安装会先卸载模拟器上的公开应用并清除其数据，只在专用测试设备运行。

每个 API 的 11 项原生检查覆盖：Android 内的 Python 恢复测试、合成 OCR 与透明图、系统断网/恢复、本机加密配置、实际 WebView 桥、小屏和大字输入、通知停止、排队启动的心跳与取消、界面调度前停止、排队退选取消及服务超时清理。服务超时回调仅在 API 35、36 实际触发，API 26 的该测试项直接返回；没有连续运行六小时验证系统累计时限。公开包另做全新安装检查；debug 场景通过不能替代公开包检查。

CI 上传 `android-verification-api-26/35/36` 报告；API 35 成功作业另上传 `YNU-android-preview` 包与构建清单。发布前核对成功 main 运行、确切提交、固定证书、报告和下载摘要，不能把临时签名的 PR 包直接作为公开预览。公开资产清单见 [下载与校验](RELEASES.md)。

## 待人工验收

ARM64 实体设备、本人账号的真实登录/查询/选课/退选、真实验证码识别率、各厂商省电策略、长时间锁屏/Doze、平板横屏和覆盖更新仍未验收。模拟器和合成会话不能证明这些场景通过。

## 官方资料

- [Chaquopy 构建与 Python 版本](https://chaquo.com/chaquopy/doc/current/android.html)
- [ONNX Runtime Android](https://onnxruntime.ai/docs/get-started/with-java.html)
- [网络状态](https://developer.android.com/develop/connectivity/network-ops/reading-network-state)
- [前台服务时限](https://developer.android.com/develop/background-work/services/fgs/timeout)
- [Doze 与待机](https://developer.android.com/training/monitoring-device-state/doze-standby)
