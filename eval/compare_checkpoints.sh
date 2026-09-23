#!/bin/zsh
# 依次用不同权重 / token 预算跑一遍 30 条评测，只打印汇总表
cd "$(dirname "$0")/.."
run() {
  echo "=================== $1 ==================="
  env "${@:2}" .venv/bin/python eval/run_eval.py 2>&1 | grep -vE 'Warning: |warnings.warn|^\s*$' | tail -12
}
run "multilingual head=1024 max=2048"  LAYA_CHAT_SUBFOLDER=multilingual LAYA_CHAT_HEAD_MAX_LEN=1024 LAYA_CHAT_MAX_LEN=2048
run "english root head=512 max=1024"   LAYA_CHAT_SUBFOLDER= LAYA_CHAT_HEAD_MAX_LEN=512 LAYA_CHAT_MAX_LEN=1024
run "typed-decisions head=512 max=1024" LAYA_CHAT_SUBFOLDER=typed-decisions LAYA_CHAT_HEAD_MAX_LEN=512 LAYA_CHAT_MAX_LEN=1024
