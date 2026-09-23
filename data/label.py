#!/usr/bin/env python3
"""老师打标：输出每道题每个选项的概率。题目原文直接取自 laya_chat/questions_send.py，保证和运行时一致。

用法：
  python data/label.py --what affinity [--model sonnet] [--per-call 16] [--shard 0/2]
  python data/label.py --what send     [--model sonnet] [--per-call 16] [--shard 1/2] [--tool codex]
输出：data/labeled/affinity.jsonl、data/labeled/send.jsonl，每行 {id, ..., gold:{qid:{probabilities:{opt:p}}}}
可重复运行，已标过的 id 跳过。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from teacher import add_common_args, apply_shard, model_arg, read_jsonl, run_batches  # noqa: E402
from laya_chat.questions_send import AFFINITY_QUESTIONS, SEND_QUESTIONS  # noqa: E402

RAW, LAB = os.path.join(HERE, "raw"), os.path.join(HERE, "labeled")

HEADER = """你是一个经验丰富的人际沟通专家，在为一个小模型造训练标签。对下面每个条目，回答给定的几道题；每道题给出「每个选项的概率」（0 到 1，同一题合计为 1）。
概率要真实反映你的把握：明显的情况给 0.8 以上，模棱两可的分散开。不要所有题都给极端值。
题目用英文写，聊天是中文，按你对中文语境的理解作答。

## 题目
{questions}

## 条目
{items}

只输出一个 JSON 数组，每个元素形如：
{{"id": "...", "answers": {{"题号": {{"选项": 概率, ...}}, ...}}}}
score 类型的题，选项用 "0"、"1"、… 这样的等级序号做键。不要输出任何别的文字。"""


def fmt_questions(qs):
    out = []
    for qid, q in qs.items():
        out.append(f"### {qid}（{q['type']}）\n{q['instructions']}")
        if q["type"] == "score":
            for i, c in enumerate(q["criteria"]):
                out.append(f"  - \"{i}\": {c}")
        else:
            for k, c in q["criteria"].items():
                out.append(f"  - \"{k}\": {c}")
    return "\n".join(out)


def fmt_messages(msgs):
    return "\n".join(f"  {'我' if m['from'] == 'me' else '对方'}：{m['text']}" for m in msgs)


def normalize(qs, answers):
    """校验并归一化。缺选项补 0，多的忽略；全 0 就均匀。返回 None 表示这条不可用。"""
    gold = {}
    for qid, q in qs.items():
        a = answers.get(qid)
        if not isinstance(a, dict):
            return None
        keys = [str(i) for i in range(len(q["criteria"]))] if q["type"] == "score" else list(q["criteria"].keys())
        vals = []
        for k in keys:
            try:
                vals.append(max(0.0, float(a.get(k, 0.0))))
            except (TypeError, ValueError):
                vals.append(0.0)
        s = sum(vals)
        vals = [v / s for v in vals] if s > 0 else [1.0 / len(keys)] * len(keys)
        gold[qid] = {"probabilities": dict(zip(keys, [round(v, 4) for v in vals]))}
    return gold


def run(what, args):
    convs = {c["id"]: c for c in read_jsonl(os.path.join(RAW, "conversations.jsonl"))}
    if what == "affinity":
        qs, out = AFFINITY_QUESTIONS, os.path.join(LAB, "affinity.jsonl")
        items = [{"id": cid, "conv_id": cid} for cid in convs]
    else:
        qs, out = SEND_QUESTIONS, os.path.join(LAB, "send.jsonl")
        items = [{"id": d["id"], "conv_id": d["conv_id"], "tag": d["tag"], "draft": d["text"]}
                 for d in read_jsonl(os.path.join(RAW, "drafts.jsonl")) if d["conv_id"] in convs]
    done = {r["id"] for r in read_jsonl(out)}
    todo = apply_shard([it for it in items if it["id"] not in done], args.shard, args.limit)
    print(f"{what}：共 {len(items)} 条，已标 {len(done)}，本次待标 {len(todo)}（shard {args.shard}）")
    batches = [todo[i:i + args.per_call] for i in range(0, len(todo), args.per_call)]
    prompts = []
    for b in batches:
        parts = []
        for it in b:
            c = convs[it["conv_id"]]
            block = f"### id {it['id']}\n关系：{c['relationship']}\n聊天：\n{fmt_messages(c['messages'])}"
            if what == "send":
                block += f"\n我准备发出的草稿：{it['draft']}"
            parts.append(block)
        prompts.append(HEADER.format(questions=fmt_questions(qs), items="\n\n".join(parts)))

    def handle(b, res):
        if not isinstance(res, list):
            return [], len(b)
        by_id = {r.get("id"): r for r in res if isinstance(r, dict)}
        rows, bad = [], 0
        for it in b:
            gold = normalize(qs, ((by_id.get(it["id"]) or {}).get("answers")) or {})
            if gold is None:
                bad += 1; continue
            rows.append({**it, "gold": gold, "teacher": f"{args.tool}:{args.model}"})
        return rows, bad

    w, bad = run_batches(batches, prompts, handle, args.tool, model_arg(args), args.workers, out)
    print(f"写入 {w} 条，作废 {bad} 条 → {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--what", choices=["affinity", "send"], required=True)
    add_common_args(ap, per_call=16)
    a = ap.parse_args()
    run(a.what, a)


if __name__ == "__main__":
    main()
