#!/usr/bin/env python3
"""给 2 到 5 条候选回复排序。

用法：
  python scripts/rank.py --file rank.json
  python scripts/rank.py < rank.json

输入 JSON：
  {
    "relationship": "对方是我的伴侣",
    "messages": [...同 judge.py...],
    "candidates": ["候选一", "候选二", "候选三"],
    "background": "可选"
  }
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bootstrap import print_json, read_json_input  # noqa: E402
from _client import call  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    args = ap.parse_args()
    payload = read_json_input(args.file)
    for k in ("messages", "candidates"):
        if k not in payload:
            sys.stderr.write(f"[laya-chat] 输入缺少 {k}\n")
            sys.exit(2)
    payload.setdefault("relationship", "对方是我的朋友")
    print_json(call("/rank", payload))


if __name__ == "__main__":
    main()
