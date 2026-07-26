#!/usr/bin/env bash
# YNU 抢课助手 · Linux 版一键环境准备
# 用法： bash setup.sh
set -e
cd "$(dirname "$0")"

PY=python3
command -v $PY >/dev/null 2>&1 || { echo "未找到 python3，请先安装 Python3"; exit 1; }

echo "[1/3] 创建虚拟环境 venv ..."
$PY -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

echo "[2/3] 安装依赖 ..."
pip install --upgrade pip
pip install requests ddddocr yagmail
# ddddocr 会带上 opencv-python，但服务器一般没有图形库(libGL)，换成 headless 版更省心
pip uninstall -y opencv-python opencv-contrib-python >/dev/null 2>&1 || true
pip install opencv-python-headless

echo "[3/3] 准备配置文件 ..."
if [ ! -f config.json ]; then
  cp config.example.json config.json
  echo "已生成 config.json，请编辑填入学号/密码/批次/课程。"
else
  echo "config.json 已存在，跳过。"
fi

echo
echo "完成！接下来："
echo "  source venv/bin/activate"
echo "  python qiangke_cli.py batches            # 拿 batch 码"
echo "  python qiangke_cli.py query 0 关键词      # 拿 教学班ID/type"
echo "  # 编辑 config.json 填好 batch 和 courses"
echo "  python qiangke_cli.py run                # 开始抢课"
