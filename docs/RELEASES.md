# 下载与文件校验

成品原样归档，GitHub 下载文件名使用英文；原名称与 SHA-256 保存在 [文件清单](file-manifest.json)。

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
