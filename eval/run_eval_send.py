#!/usr/bin/env python3
"""用 data/dataset/dev.jsonl（或 test）评测一份 Laya 权重在新题目上的表现。微调前后各跑一次对比。

用法：.venv/bin/python eval/run_eval_send.py [--split dev] [--model 路径或repo] [--subfolder typed-decisions]
指标：每题 argmax 和老师 argmax 的一致率、score 题的等级平均误差、以及「永远猜最常见答案」的基线。
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from laya_chat import config  # noqa: E402
from laya_chat.engine import Engine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--model")
    ap.add_argument("--subfolder")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cfg = config.load()
    if a.model is not None:
        cfg["model"] = a.model
    if a.subfolder is not None:
        cfg["subfolder"] = a.subfolder
    path = os.path.join(ROOT, "data", "dataset", f"{a.split}.jsonl")
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    if a.limit:
        rows = rows[:a.limit]
    eng = Engine(cfg); eng.load()
    if eng.error:
        sys.exit(f"模型加载失败：{eng.error}")
    print("model:", cfg["model"], cfg.get("subfolder"), "rows:", len(rows))

    hit, tot, mae = Counter(), Counter(), defaultdict(float)
    majority = defaultdict(Counter)
    for r in rows:
        state, qs, gold = json.loads(r["state"]), json.loads(r["questions"]), json.loads(r["gold"])
        ans = eng.ask(state, qs)
        for qid, q in qs.items():
            gp = gold[qid]["probabilities"]
            want = max(gp, key=gp.get)
            majority[qid][want] += 1
            if q["type"] == "score":
                got = str(int(round(ans[qid]["score"])))
                exp_gold = sum(int(k) * v for k, v in gp.items())
                mae[qid] += abs(ans[qid]["score"] - exp_gold)
            else:
                got = ans[qid]["choice"]
            hit[qid] += got == want
            tot[qid] += 1
    print(f"\n{'question':18} {'acc':>6} {'majority':>9}  note")
    for qid in tot:
        maj = majority[qid].most_common(1)[0][1] / tot[qid]
        note = f"level MAE={mae[qid] / tot[qid]:.2f}" if qid in mae else ""
        print(f"{qid:18} {hit[qid] / tot[qid]:6.2f} {maj:9.2f}  {note}")
    print(f"\noverall: {sum(hit.values()) / max(1, sum(tot.values())):.3f}")


if __name__ == "__main__":
    main()
