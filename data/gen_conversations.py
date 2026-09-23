#!/usr/bin/env python3
"""种子 → 中文微信对话。每段 6 到 14 条，最后一条是对方说的。

用法：python data/gen_conversations.py --n 100 --seed 1 [--focus] [--model sonnet] [--per-call 4]
--focus 只用有张力的情境（最后通牒、试探、道歉后、催促……），补公开数据集缺的那部分。
输出：data/raw/conversations.jsonl；已有的 id 会跳过。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scenarios  # noqa: E402
from teacher import add_common_args, apply_shard, model_arg, read_jsonl, run_batches  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw", "conversations.jsonl")

FOCUS = [s for s in scenarios.SITUATIONS if any(k in s for k in
         ("试探", "道歉", "催", "冷战", "阴阳", "追问", "最后通牒", "拒绝", "误会", "生气", "借钱"))]

PROMPT = """你在为一个「微信聊天回复助手」造训练数据。请写 {k} 段真实感很强的中文微信聊天记录，每段按下面给定的设定来写。

要求：
- 每段是「我」和「对方」的一对一聊天，from 只能是 me 或 other。
- 每段 6 到 14 条消息，最后一条必须是 other 说的，我还没回。
- 像真人在微信上打字：短句、口语、有时不加标点、偶尔错别字或表情文字。不要像小说对白。
- 对方的态度要符合设定的「对方当前态度」和「走势」，但不要把设定原话写进聊天。
- 每段之间人物、话题、用词都要不一样。

设定：
{settings}

只输出一个 JSON 数组，每个元素形如：
{{"seed_id": 0, "messages": [{{"from": "other", "text": "..."}}, {{"from": "me", "text": "..."}}]}}
不要输出任何别的文字。"""


def fmt_setting(s):
    return (f"- seed_id {s['seed_id']}：关系「{s['relationship_short']}」；情境：{s['situation']}；"
            f"对方当前态度：{s['mood']}；走势：{s['trend']}；风格：{s['style']}；约 {s['n_messages']} 条")


def valid(msgs):
    if not isinstance(msgs, list) or len(msgs) < 5:
        return False
    sides = {m.get("from") for m in msgs}
    if not sides <= {"me", "other"} or "me" not in sides or "other" not in sides:
        return False
    if msgs[-1].get("from") != "other":
        return False
    return all(isinstance(m.get("text"), str) and m["text"].strip() for m in msgs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--focus", action="store_true")
    add_common_args(ap, per_call=4)
    args = ap.parse_args()
    if args.focus:
        scenarios.SITUATIONS = FOCUS
    existing = {r["id"] for r in read_jsonl(OUT)}
    todo = [s for s in scenarios.seeds(args.n, args.seed) if f"c{args.seed}_{s['seed_id']:04d}" not in existing]
    todo = apply_shard(todo, args.shard, args.limit)
    print(f"已有 {len(existing)} 段，待生成 {len(todo)} 段（focus={args.focus}）")
    batches = [todo[i:i + args.per_call] for i in range(0, len(todo), args.per_call)]
    prompts = [PROMPT.format(k=len(b), settings="\n".join(fmt_setting(s) for s in b)) for b in batches]

    def handle(b, res):
        if not isinstance(res, list):
            return [], len(b)
        by_seed = {r.get("seed_id"): r for r in res if isinstance(r, dict)}
        rows, bad = [], 0
        for s in b:
            r = by_seed.get(s["seed_id"])
            if not r or not valid(r.get("messages")):
                bad += 1; continue
            rows.append({"id": f"c{args.seed}_{s['seed_id']:04d}", "source": "synthetic",
                         "relationship": s["relationship"], "relationship_short": s["relationship_short"],
                         "situation": s["situation"], "mood_level": s["mood_level"], "trend_hint": s["trend"],
                         "messages": [{"from": m["from"], "text": m["text"].strip()} for m in r["messages"]]})
        return rows, bad

    w, bad = run_batches(batches, prompts, handle, args.tool, model_arg(args), args.workers, OUT)
    print(f"写入 {w} 段，作废 {bad} 段 → {OUT}")


if __name__ == "__main__":
    main()
