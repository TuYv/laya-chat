#!/usr/bin/env python3
"""用 jev-chat 的 30 条标注对话测 Laya 在 7 道题上的准确率。直接在进程内加载模型，不经过守护进程。

用法：
  .venv/bin/python eval/run_eval.py
  .venv/bin/python eval/run_eval.py --verbose          # 逐条打印判错的题
  LAYA_CHAT_HEAD_MAX_LEN=768 LAYA_CHAT_MAX_LEN=1536 .venv/bin/python eval/run_eval.py
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from _engine import Engine  # noqa: E402
from questions import BOOL_LABELS, JUDGE_QUESTIONS  # noqa: E402

REL_ZH = {
    "friends": "对方是我的朋友",
    "partner": "对方是我的伴侣",
    "couple": "对方是我的伴侣",
    "colleague": "对方是我的同事",
    "coworker": "对方是我的同事",
    "boss": "对方是我的上司",
    "family": "对方是我的家人",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(ROOT, "eval", "labeled_set.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    cases = json.load(open(args.file, encoding="utf-8"))

    eng = Engine()
    eng.load()
    print("model:", eng.info())

    hit, tot = Counter(), Counter()
    danger_abs_err, danger_within1 = [], 0
    majority = defaultdict(Counter)
    lat = []
    for c in cases:
        rel = REL_ZH.get(c["relationship"], c["relationship"])
        res = eng.judge(c["messages"], rel)
        lat.append(res["latency_ms"])
        a = res["answers"]
        for q, want in c["expect"].items():
            majority[q][want] += 1
            if q == "danger_level":
                got = a[q]["level"]
                err = abs(got - want)
                danger_abs_err.append(err)
                ok = err == 0
                danger_within1 += err <= 1
            elif q in BOOL_LABELS:
                got = a[q]["value"]
                ok = got == want
            else:
                got = a[q]["choice"]
                ok = got == want
            hit[q] += ok
            tot[q] += 1
            if args.verbose and not ok:
                print(f"  [{c['id']}] {q}: want={want} got={got}  conf={a[q]['confidence']:.2f}")

    print()
    print(f"{'question':18} {'acc':>6} {'majority':>9} {'random':>7}  note")
    for q in JUDGE_QUESTIONS:
        k = len(JUDGE_QUESTIONS[q]["criteria"])
        maj = majority[q].most_common(1)[0][1] / tot[q]
        note = ""
        if q == "danger_level":
            note = f"MAE={sum(danger_abs_err)/len(danger_abs_err):.2f}  within±1={danger_within1/tot[q]:.2f}"
        print(f"{q:18} {hit[q]/tot[q]:6.2f} {maj:9.2f} {1/k:7.2f}  {note}")
    print(f"\noverall (7 questions x {len(cases)} cases): {sum(hit.values())/sum(tot.values()):.3f}")
    print(f"latency per case (7 questions, one forward pass): median {sorted(lat)[len(lat)//2]} ms")


if __name__ == "__main__":
    main()
