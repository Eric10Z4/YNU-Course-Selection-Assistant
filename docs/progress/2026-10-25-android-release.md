# 安卓 0.1.0 Preview 1 发布记录

- 日期：2026-10-25（Asia/Shanghai）
- 成品来源：main 提交 `8af69ea0571e1f9d49143c930c6a350c8eff80b8`。
- 状态：原生构建与模拟器检查通过，固定签名预览的四份资产已公开下载；真实业务及实体设备验收待完成。
- 范围：安卓通用适配；Mac 保持现有未公证预览，iOS 尚未实现。

## 实现与发布前修复

采用原生 Java WebView + Chaquopy 17.1/Python 3.13 + Android ONNX Runtime 1.23.2。复用桌面认证、Cookie 会话与查询，原生运行现有 OCR 模型；安卓任务循环和页面独立，不改变原桌面执行入口。

实现串行限时任务、提交前原子保存、断网等待、切网恢复先核对、结果不明不自动重发、进程中断手动恢复、通知停止、服务时限清理和小屏/大字/键盘适配。密码默认不保存，显式保存后由系统密钥加密。支持 Android 8/API 26+，包含 arm64-v8a 与 x86_64，不含 32 位。

发布前修复同 ID 跨批次确认、首次提交前计划窗口重查、排队启动与前台服务生命周期、停止取消排队启动/退选，以及登录期间停止后不再退选。公开包关闭调试并递归检查排除合成测试模块，debug 使用独立 `.debug` 应用 ID。

## 验证证据

- Windows/Python 3.12：51 项本地单元测试通过，其中安卓合成场景 31 项；Python 编译、移动 JavaScript 语法和 `git diff --check` 通过。
- [PR #4](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/pull/4) 的提交 `9c86855e32eee7d5f0b08bab0e94325ab7bc386a`：[Android 原生检查](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40165733327)、[Mac 双架构回归](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40165733461)、[Windows/Ubuntu 检查](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40165733312) 全部通过后合入 main。
- 首次 main 运行的 API 35 作业因 Google Maven 返回 502 在下载依赖时失败；只重跑该作业，未修改代码。API 26/36 沿用同一来源运行中已通过的结果，最终运行尝试为第 2 次。
- 成品对应的 [main 原生构建与设备检查](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/actions/runs/40166135205) 通过；来源提交、版本、固定签名、两个 ABI 和 16 KB ELF/ZIP 对齐均核对。
- API 26、35、36 的 x86_64 模拟器各完成 11 项设备检查，无失败或跳过；每组内嵌 Python 另运行全部 31 项合成场景，无跳过。
- 检查包括：原生合成 OCR/透明图、密码默认不保存和加密、实际 WebView→Python 桥、360 CSS 像素布局、160% 文字与实际触摸输入、系统断网/恢复回调、通知停止、排队启动跨越真实 32 秒心跳后停止、停止先于 UI 调度、排队退选取消，以及明确手动重启成功。
- 服务超时清理通过手动调用 Android 15/16 的系统回调检查；Android 8 不支持该回调，该测试方法直接返回。这不是连续运行六小时的验证。
- 非调试公开 APK 在三组系统全新安装、启动并确认真实引擎的空闲状态。debug 合成场景和公开包分别验收；公开包不会运行合成选课场景。
- 所有学校认证、Cookie、查询、选课和退选检查均使用合成会话；没有发送真实学校请求。OCR 合成推理不证明真实验证码识别率。

## 签名与公开资产

用户已明确授权创建并配置免费的专用安卓预览签名。私钥在仓库外保留备份，并通过 GitHub Secrets 供可信 main 构建使用；私钥和密码不进入 Git、报告或下载包。PR 构建不读取预览密钥。

应用 ID `io.github.eric10z4.ynu.android`，版本 `0.1.0-preview.1`、`versionCode=1`。证书 SHA-256：`60136241dddbf677d63bb7d59b1e1c4d2868ea1a69fc598606d58da18eabc561`。后续覆盖更新保持应用 ID/证书并递增 versionCode；本次只验证全新安装，数据迁移仍待验收。

[公开预发布下载](https://github.com/Eric10Z4/YNU-Course-Selection-Assistant/releases/tag/android-v0.1.0-preview.1) 的标签指向上述成品提交。先上传草稿并核对四份资产的名称、大小和 SHA-256，再公开为 Pre-release；发布后再次核对标签、资产和状态，Windows 最新稳定版仍为 `v2.4`，Mac 预览保持不变。

| 文件 | 内容 |
| --- | --- |
| `YNU-Course-Assistant-0.1.0-preview.1.apk` | 固定签名、关闭调试的安装包；87142653 字节，SHA-256 `3c775bc3c67a411a9671a47e6e60d40124d7fc04110e39efb7c3f5c11038e63c` |
| `android-verification.zip` | 原始构建清单、三组设备 XML/合成 JSON 报告及公开包启动截图，不含完整设备日志 |
| `release-manifest.json` | 来源提交、构建运行、签名指纹、检查范围和下载摘要 |
| `SHA256SUMS.txt` | 上述三份文件的 SHA-256 |

已将实际有效的安卓构建、恢复、debug/preview 隔离和分发边界补充到项目 `ynu-development` skill；命令维护在 [安卓指南](../ANDROID.md)，避免重复清单。

## 尚待验收

ARM64 实体手机及 16 KB 实体设备、真实验证码与本人账号业务、厂商省电、长时间锁屏/Doze、平板横屏/厂商键盘、保留数据覆盖更新均未验收。默认运行三十分钟、单次最长三小时；系统或厂商可提前限制，不能保证无限挂机或准点执行。后续按 [验收矩阵](../TEST_MATRIX.md) 逐项记录，不把自动检查等同于真实学校业务。
