# YNU 抢课助手 · Linux 无界面版

服务器挂机专用。和图形版共用同一套抢课引擎（登录、验证码 OCR、齐射并发、高峰增强、定时、自动重登、抢到即停单门其余继续），只是把界面换成「配置文件 + 命令行」。

## 一、上传即用（三步）

1. 把本文件夹整个上传到服务器（比如 `/root/qiangke`）。
2. 装环境：

   ```bash
   cd /root/qiangke
   bash setup.sh
   ```

   脚本会建虚拟环境 `venv`、装依赖（含 `opencv-python-headless`，避开服务器缺 `libGL` 的坑）、并从模板生成 `config.json`。

3. 每次用前先激活环境：

   ```bash
   source venv/bin/activate
   ```

## 二、填配置

先查两样东西，填进 `config.json`：

```bash
python qiangke_cli.py batches           # 找到带 ★ 的开放批次，复制它的 code 填到 batch
python qiangke_cli.py query 0 数据结构   # 查课，复制 教学班ID 和 type 填到 courses
```

`query` 的分类序号：`0`=通识选修 `1`=推荐 `2`=主修 `3`=体育 `4`=创新创业。关键词可省略（=全部）。

`config.json` 关键字段：

- `username` / `password`：学号、密码（必填）。
- `batch`：开放批次 code（留空用内置默认，建议用 `batches` 查准）。
- `mode`：`turbo`（每轮每门 ×6、不间断，火力最猛）/ `fast`（×1、0.3s，均衡）/ `steady`（×1、2s，稳）/ `custom`（自定义）。
- `custom_salvo` / `custom_interval`：仅 `mode=custom` 时生效，每轮每门并发数与轮间隔秒。
- `start_at`：定时开抢，格式 `"2025-09-01 12:00:00"`，留空立即开抢。
- `peak`：高峰增强，`enabled` 打开后，每小时第 `startMin`~`endMin` 分把强度提到 `mult` 倍（优先缩短间隔；turbo/间隔为0则提并发）。
- `email_user` / `email_auth`：可选，抢到后用 QQ 邮箱 SMTP 授权码发提醒；不用留空。
- `courses`：要抢的课列表，每项 `{"name": "课程名", "id": "教学班ID", "type": "XGXK"}`。`name` 随便写方便看日志，`id`/`type` 从 `query` 复制。

其它命令：

```bash
python qiangke_cli.py selected          # 看已选
python qiangke_cli.py timetable         # 看课表
python qiangke_cli.py withdraw <教学班ID> # 退选
```

## 三、长期挂机（三选一）

**A. tmux / screen（最简单）**

```bash
tmux new -s qk
source venv/bin/activate
python qiangke_cli.py run
# 按 Ctrl-b 再按 d 脱离；重连用 tmux attach -t qk
```

**B. nohup 后台**

```bash
source venv/bin/activate
nohup python qiangke_cli.py run >/dev/null 2>&1 &
tail -f qiangke.log        # 看日志
```

**C. systemd（开机自启 + 崩溃自动重启，最稳）**

编辑 `qiangke.service` 里的 `WorkingDirectory` / `User` / 路径为你的实际值，然后：

```bash
sudo cp qiangke.service /etc/systemd/system/qiangke.service
sudo systemctl daemon-reload
sudo systemctl enable --now qiangke
sudo systemctl status qiangke      # 看状态
journalctl -u qiangke -f           # 看实时日志
sudo systemctl stop qiangke        # 停止
```

## 四、说明

- 日志同时打屏和写 `qiangke.log`（自动滚动，单文件 5MB×3）。想只打屏：`--log ""`。
- 优雅停止：`Ctrl-C` 或 `systemctl stop` / `kill` 都会让它停当前抢课后退出（`SIGINT`/`SIGTERM` 已处理）。
- 服务器不会像笔记本那样睡眠，所以图形版里"阻止睡眠"这类东西这里不需要。
- 抢课逻辑：每轮同时给所有未抢到的课发请求，某门抢到就只停那门、其余继续，直到全部抢到或你手动停。
- 依赖装不上/`libGL.so.1` 报错：`setup.sh` 已用 `opencv-python-headless` 规避；若仍报，执行 `sudo apt install -y libgl1 libglib2.0-0`。
