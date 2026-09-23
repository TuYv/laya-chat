#!/usr/bin/env python3
"""把标好的数据合并成 Laya 微调笔记本要的格式：每行 {case_id, state, questions, gold}（后三个是 JSON 字符串）。
按对话切分 train / dev / test（同一段对话的草稿不会跨集合）。

用法：python data/build_dataset.py [--dev 0.15 --test 0.15 --seed 0]
输出：data/dataset/{train,dev,test}.jsonl
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from teacher import read_jsonl  # noqa: E402
from laya_chat.questions_send import (AFFINITY_QUESTIONS, AFFINITY_WORDS, LABELS, SEND_QUESTIONS,  # noqa: E402
                                      build_affinity_state, build_send_state)


def expected_level(probs):
    return sum(int(k) * v for k, v in probs.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", type=float, default=0.15)
    ap.add_argument("--test", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    convs = {c["id"]: c for c in read_jsonl(os.path.join(HERE, "raw", "conversations.jsonl"))}
    aff = {r["conv_id"]: r for r in read_jsonl(os.path.join(HERE, "labeled", "affinity.jsonl"))}
    send = read_jsonl(os.path.join(HERE, "labeled", "send.jsonl"))

    rows = []
    for cid, r in aff.items():
        c = convs.get(cid)
        if not c:
            continue
        rows.append({"case_id": f"aff_{cid}", "conv_id": cid, "kind": "affinity",
                     "state": json.dumps(build_affinity_state(c["messages"], c["relationship"]), ensure_ascii=False),
                     "questions": json.dumps(AFFINITY_QUESTIONS, ensure_ascii=False),
                     "gold": json.dumps(r["gold"], ensure_ascii=False)})
    for r in send:
        c = convs.get(r["conv_id"])
        if not c:
            continue
        # 运行时 state 里带的是 Laya 自己算的好感度；训练时用老师标的，让模型学会参考这个字段
        affinity = None
        ar = aff.get(r["conv_id"])
        if ar:
            g = ar["gold"]
            score = expected_level(g["affinity"]["probabilities"])
            trend = max(g["trend"]["probabilities"], key=g["trend"]["probabilities"].get)
            issue = max(g["open_issue"]["probabilities"], key=g["open_issue"]["probabilities"].get)
            affinity = {"score": score, "label": AFFINITY_WORDS[max(0, min(9, int(round(score))))],
                        "trend": trend, "open_issue": issue}
        rows.append({"case_id": f"send_{r['id']}", "conv_id": r["conv_id"], "kind": "send", "tag": r.get("tag"),
                     "state": json.dumps(build_send_state(c["messages"], c["relationship"], r["draft"], affinity),
                                         ensure_ascii=False),
                     "questions": json.dumps(SEND_QUESTIONS, ensure_ascii=False),
                     "gold": json.dumps(r["gold"], ensure_ascii=False)})

    ids = sorted(convs)
    random.Random(a.seed).shuffle(ids)
    n = len(ids)
    n_test, n_dev = int(n * a.test), int(n * a.dev)
    split = {}
    for i, cid in enumerate(ids):
        split[cid] = "test" if i < n_test else "dev" if i < n_test + n_dev else "train"
    out_dir = os.path.join(HERE, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    counts = {"train": 0, "dev": 0, "test": 0}
    files = {k: open(os.path.join(out_dir, f"{k}.jsonl"), "w", encoding="utf-8") for k in counts}
    for r in rows:
        k = split[r["conv_id"]]
        files[k].write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[k] += 1
    for f in files.values():
        f.close()
    print(f"对话 {n} 段 → 条目 {len(rows)}（好感度 {len(aff)}，发送后果 {len(send)}）；切分 {counts}")


if __name__ == "__main__":
    main()
