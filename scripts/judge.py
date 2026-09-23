#!/usr/bin/env python3
"""对一段聊天回答 7 道判断题。

用法：
  python scripts/judge.py --file chat.json
  python scripts/judge.py < chat.json
  python scripts/judge.py --file chat.json --pretty     # 附一行中文摘要到 stderr
  python scripts/judge.py --stop                        # 关掉后台判断进程

输入 JSON：
  {
    "relationship": "对方是我的伴侣",
    "messages": [{"from": "other", "text": "你又忘了？"}, {"from": "me", "text": "忘了什么"}],
    "background": "可选。联系人备注、相关笔记等"
  }
from 只能是 me 或 other。只用最近 10 条。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bootstrap import print_json, read_json_input  # noqa: E402
from _client import call, stop_daemon  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args()
    if args.stop:
        print_json({"stopped": stop_daemon()})
        return
    payload = read_json_input(args.file)
    if "messages" not in payload:
        sys.stderr.write("[laya-chat] 输入缺少 messages\n")
        sys.exit(2)
    payload.setdefault("relationship", "对方是我的朋友")
    out = call("/judge", payload)
    if args.pretty:
        from _engine import summarize
        sys.stderr.write(summarize(out) + "\n")
    print_json(out)


if __name__ == "__main__":
    main()
