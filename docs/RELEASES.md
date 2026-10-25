# 下载与文件校验

## 安卓 0.1.0 Preview 1（2026-10-25）

[android-v0.1.0-preview.1 下载页](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/android-v0.1.0-preview.1) 提供以下四个文件：

| 文件 | 用途 |
| --- | --- |
| `YNU-Course-Assistant-0.1.0-preview.1.apk` | Android 8.0/API 26+ 公开预览，含 arm64-v8a 与 x86_64，无需安装 Python |
| `android-verification.zip` | 原生/设备验证材料，内含 `original-build-manifest.json` |
| `release-manifest.json` | 发布来源与校验信息 |
| `SHA256SUMS.txt` | 下载文件 SHA-256 摘要 |

公开包来自 main 提交 `8af69ea0571e1f9d49143c930c6a350c8eff80b8`、[成功的 main 原生运行](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40166135205)；[PR 原生运行](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40165733327) 仅作合入前验证。API 26、35、36 的 x86_64 模拟器各通过 11 项原生检查，并分别全新安装、启动非调试公开包。测试使用合成会话，ARM64 实体设备、覆盖更新、真实学校业务及厂商后台策略待验收，详情见 [安卓指南](ANDROID.md) 和 [发布记录](progress/2026-10-25-android-release.md)。

公开应用 ID 为 `io.github.eric10z4.ynu.android`，`versionCode=1`，使用固定的专用预览签名；证书 SHA-256 为 `60136241dddbf677d63bb7d59b1e1c4d2868ea1a69fc598606d58da18eabc561`。后续覆盖更新保持应用 ID/证书并递增 versionCode。debug 包使用 `.debug` 后缀，与公开包数据隔离。

下载后可在 Windows 使用 `Get-FileHash -Algorithm SHA256 <文件路径>`，在 Linux 使用 `sha256sum <文件路径>`，或在 macOS 使用 `shasum -a 256 <文件路径>`，与 `SHA256SUMS.txt` 对照。证书指纹与 APK 文件摘要是不同的校验值；签名私钥和密码不包含在任何公开资产中。

## macOS 预发布

[2.4.1 Preview 1 下载页](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/macos-v2.4.1-preview.1) 提供以下两份独立构建，无需安装 Python：

| 芯片 | 应用压缩包 |
| --- | --- |
| Apple Silicon（M 系列） | `QiangKeWeb-2.4.1-macos-arm64.zip` |
| Intel | `QiangKeWeb-2.4.1-macos-x86_64.zip` |

下载页同时提供 `SHA256SUMS.txt`、`release-manifest.json` 和两份 `verification` 压缩包，记录源码提交、架构、依赖及实际自动检查结果。Mac 可运行 `shasum -a 256 <文件路径>` 核对对应校验值。

这是 ad-hoc 签名、未公证的预发布版，尚未完成真人业务验收，仅在 macOS 15 的构建环境验证。下载后可能被 macOS 阻止打开；正式分发的条件和待验收内容见 [Mac 发布指南](MACOS_RELEASE.md)。付费签名公证按用户选择暂缓；iOS 尚无 IPA。

## 历史成品

以下历史成品原样归档，GitHub 下载文件名使用英文；原名称与 SHA-256 保存在 [文件清单](file-manifest.json)。

| 下载页 | 原文件名 | 大小 | 网盘修改时间 |
| --- | --- | --- | --- |
| [linux-archive-20260727](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/linux-archive-20260727) | `qiangke_linux.zip` | 0.01 MiB | `2026-07-27T01:18:15+08:00` |
| [archive-px10](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/archive-px10) | `QiangKeWeb PX10版本.exe` | 339.71 MiB | `2026-07-27T01:24:05+08:00` |
| [v2.0](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v2.0) | `QiangKeWeb V2.0.exe` | 170.97 MiB | `2026-07-27T01:20:20+08:00` |
| [v2.1](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v2.1) | `QiangKeWeb V2.1.exe` | 170.97 MiB | `2026-07-27T01:22:28+08:00` |
| [v2.2.1](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v2.2.1) | `QiangKeWeb V2.2.1.exe` | 167.95 MiB | `2026-08-02T21:37:27+08:00` |
| [v2.2](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v2.2) | `QiangKeWeb V2.2.exe` | 170.97 MiB | `2026-07-27T01:21:41+08:00` |
| [v2.3](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v2.3) | `QiangKeWeb V2.3.exe` | 50.29 MiB | `2026-08-03T02:23:57+08:00` |
| [v2.4](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v2.4) | `QiangKeWeb V2.4.exe` | 50.30 MiB | `2026-09-01T14:37:37+08:00` |
| [v1.0](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/v1.0) | `QiangKeWebPX0 V1.0.exe` | 170.96 MiB | `2026-07-27T01:21:26+08:00` |

每个下载页附带对应的 `SHA256SUMS` 文本。Windows 可用 `Get-FileHash -Algorithm SHA256 <文件路径>` 查看文件校验值；Linux 可使用 `sha256sum <文件路径>`。

V2.4 的 EXE 内部入口仍保留 `qiangke_web V2.3` 的构建名称，但其嵌入代码包含动态类别相关符号；此处按提供的文件名称归档，并记录这一差异，不改写原成品。

PX10 没有对应源码或可验证更新列表。Linux 压缩包未声明版本号。旧成品未签署本次迁移的新签名，也未重新编译。
