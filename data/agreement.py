#!/usr/bin/env python3
"""老师自一致性：抽一些已标条目重标一遍，看两次的一致程度。这是微调后模型能达到的上限参考。

用法：python data/agreement.py --what send --n 12 [--tool claude]
"""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from teacher import call_json, read_jsonl  # noqa: E402
from label import HEADER, fmt_messages, fmt_questions, normalize  # noqa: E402
from laya_chat.questions_send import AFFINITY_QUESTIONS, SEND_QUESTIONS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--what", choices=["affinity", "send"], default="send")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--tool", default="claude")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    convs = {c["id"]: c for c in read_jsonl(os.path.join(HERE, "raw", "conversations.jsonl"))}
    qs = AFFINITY_QUESTIONS if a.what == "affinity" else SEND_QUESTIONS
    rows = read_jsonl(os.path.join(HERE, "labeled", f"{a.what}.jsonl"))
    rows = random.Random(a.seed).sample(rows, min(a.n, len(rows)))
    parts = []
    for it in rows:
        c = convs[it["conv_id"]]
        block = f"### id {it['id']}\n关系：{c['relationship']}\n聊天：\n{fmt_messages(c['messages'])}"
        if a.what == "send":
            block += f"\n我准备发出的草稿：{it['draft']}"
        parts.append(block)
    prompts = [HEADER.format(questions=fmt_questions(qs), items="\n\n".join(parts[i:i + 6])) for i in range(0, len(parts), 6)]
    res = []
    for pr in prompts:
        b = call_json(pr, a.tool, model=None if a.model == 'none' else a.model)
        res += b if isinstance(b, list) else []
    by_id = {r.get("id"): r for r in res if isinstance(r, dict)}
    agree, l1, n = {q: 0 for q in qs}, {q: 0.0 for q in qs}, 0
    for it in rows:
        g2 = normalize(qs, (by_id.get(it["id"]) or {}).get("answers") or {})
        if g2 is None:
            continue
        n += 1
        for q in qs:
            p1, p2 = it["gold"][q]["probabilities"], g2[q]["probabilities"]
            agree[q] += max(p1, key=p1.get) == max(p2, key=p2.get)
            l1[q] += sum(abs(p1[k] - p2[k]) for k in p1) / 2
    print(f"重标 {n} 条")
    print(f"{'question':18} argmax一致  分布平均差(0-1)")
    for q in qs:
        print(f"{q:18} {agree[q] / n:8.2f}   {l1[q] / n:.2f}")


if __name__ == "__main__":
    main()
