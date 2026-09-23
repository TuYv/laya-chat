#!/usr/bin/env python3
"""从 LCCC（清华，微博对话）挑对话做训练数据。

流式读 lccc_base_train.jsonl.gz（370 MB，首次下载并缓存在 data/raw/），筛选：
- 7 到 14 轮，每轮 2 到 60 字，不含 @、网址、「转发」
- 前 T-2 轮当对话（最后一轮是对方说的），第 T-1 轮是我实际发的下一句（real_next），第 T 轮是对方实际回复（real_reply）
- 命中张力关键词的优先抽 --n-tension 段，再随机抽 --n-random 段
用法：python data/import_lccc.py --n-tension 200 --n-random 100 --seed 0
输出追加到 data/raw/conversations.jsonl，id 形如 l_00012。
"""
import argparse
import gzip
import json
import os
import random
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teacher import append_jsonl, read_jsonl  # noqa: E402

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
URL = "https://huggingface.co/datasets/silver/lccc/resolve/main/lccc_base_train.jsonl.gz"
CACHE = os.path.join(RAW, "lccc_base_train.jsonl.gz")
OUT = os.path.join(RAW, "conversations.jsonl")
RELATIONSHIP = "关系未知，请从聊天内容判断"

TENSION = ["算了", "随便", "呵呵", "你怎么又", "不想说", "不想理", "别理我", "无所谓", "你忘了", "记得吗",
           "为什么不", "又忘", "生气", "对不起", "抱歉", "不理你", "分手", "烦", "无语", "你从来", "每次都",
           "说好的", "等你", "不回", "不高兴", "失望", "凭什么", "不用了", "再见", "拉黑", "哼", "骗", "冷"]
BAD = re.compile(r"@|http|转发|微博|抽奖|关注|私信")


def clean(t):
    return re.sub(r"\s+", "", t)


def usable(turns):
    if not 7 <= len(turns) <= 14:
        return False
    for t in turns:
        if not 2 <= len(t) <= 60 or BAD.search(t):
            return False
    return True


def to_row(turns, idx):
    p = len(turns) - 2
    prefix = turns[:p]
    # 轮次交替：前缀最后一轮是对方，下一轮是我
    other_parity = (p - 1) % 2
    msgs = [{"from": "other" if i % 2 == other_parity else "me", "text": t} for i, t in enumerate(prefix)]
    return {"id": f"l_{idx:05d}", "source": "lccc", "relationship": RELATIONSHIP, "relationship_short": "未知",
            "situation": "", "messages": msgs, "real_next": turns[p], "real_reply": turns[p + 1],
            "tension": any(k in "".join(turns) for k in TENSION)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-tension", type=int, default=200)
    ap.add_argument("--n-random", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    if not os.path.exists(CACHE):
        print("下载 LCCC base 训练集（370 MB）…", flush=True)
        urllib.request.urlretrieve(URL, CACHE + ".part")
        os.rename(CACHE + ".part", CACHE)
    rnd = random.Random(a.seed)
    tension, plain = [], []
    n_seen = n_ok = 0
    with gzip.open(CACHE, "rt", encoding="utf-8") as f:
        for line in f:
            n_seen += 1
            try:
                turns = [clean(t) for t in json.loads(line)]
            except Exception:  # noqa: BLE001
                continue
            if not usable(turns):
                continue
            n_ok += 1
            joined = "".join(turns)
            if any(k in joined for k in TENSION):
                tension.append(turns)
            else:
                # 蓄水池抽样，只留 20000 条平淡的
                if len(plain) < 20000:
                    plain.append(turns)
                else:
                    j = rnd.randrange(n_ok)
                    if j < 20000:
                        plain[j] = turns
            if n_seen % 1000000 == 0:
                print(f"  已读 {n_seen} 行，可用 {n_ok}，有张力 {len(tension)}", flush=True)
    print(f"读完 {n_seen} 行：可用 {n_ok}，有张力 {len(tension)}")
    existing = read_jsonl(OUT)
    start = 1 + max([int(r["id"][2:]) for r in existing if r["id"].startswith("l_")] or [0])
    picked = rnd.sample(tension, min(a.n_tension, len(tension))) + rnd.sample(plain, min(a.n_random, len(plain)))
    rows = [to_row(t, start + i) for i, t in enumerate(picked)]
    append_jsonl(OUT, rows)
    print(f"写入 {len(rows)} 段（张力 {min(a.n_tension, len(tension))}，随机 {min(a.n_random, len(plain))}）→ {OUT}")


if __name__ == "__main__":
    main()
