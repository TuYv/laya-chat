#!/bin/zsh
# 补齐发送后果标签（已标的跳过），然后合并切分。用量受限时自动等待。
cd "$(dirname "$0")/.."
P=.venv/bin/python
echo "[$(date '+%H:%M:%S')] == 补标发送后果" >> data/run.log
$P data/label.py --what send --model sonnet --per-call 16 --workers 3 >> data/run.log 2>&1
echo "[$(date '+%H:%M:%S')] == 合并切分" >> data/run.log
$P data/build_dataset.py >> data/run.log 2>&1
echo "[$(date '+%H:%M:%S')] 补标结束。发送后果标签 $(wc -l < data/labeled/send.jsonl) 条" >> data/run.log
