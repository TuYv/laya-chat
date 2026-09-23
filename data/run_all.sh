#!/bin/zsh
# 全量流水线：每一步 claude(sonnet) 和 codex 各跑一半，互不等待；某一半失败不影响另一半。
# 中断后重跑同一条命令即可，已完成的会跳过。日志：data/run.log
set -u
cd "$(dirname "$0")/.."
P=.venv/bin/python
LOG=data/run.log
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
USE_CODEX=${USE_CODEX:-0}   # codex 走的自定义服务商实测很慢，默认关；USE_CODEX=1 时两个老师各跑一半
both() {   # both <script> <args...>
  if [[ "$USE_CODEX" == "1" ]]; then
    $P "$@" --tool claude --model sonnet --shard 0/2 --workers 3 >>"$LOG" 2>&1 &
    $P "$@" --tool codex  --model none   --shard 1/2 --workers 3 >>"$LOG" 2>&1 &
    wait
  else
    $P "$@" --tool claude --model sonnet --workers 3 >>"$LOG" 2>&1
  fi
}
log "== 1/5 合成 100 段有张力的对话（只用 claude）"
$P data/gen_conversations.py --n 100 --seed 1 --focus --tool claude --model sonnet --per-call 4 --workers 3 >>"$LOG" 2>&1
log "== 2/5 生成草稿"
both data/gen_drafts.py --per-call 6
log "== 3/5 好感度标签"
both data/label.py --what affinity --per-call 16
log "== 4/5 发送后果标签"
both data/label.py --what send --per-call 16
log "== 5/5 合并切分"
$P data/build_dataset.py >>"$LOG" 2>&1
log "完成。对话 $(wc -l < data/raw/conversations.jsonl) 段，草稿 $(wc -l < data/raw/drafts.jsonl) 条，好感度标签 $(wc -l < data/labeled/affinity.jsonl)，发送后果标签 $(wc -l < data/labeled/send.jsonl)"
