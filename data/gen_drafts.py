#!/usr/bin/env python3
"""每段对话 → 4 条「我接下来要发的草稿」。

来自 LCCC 的对话有真实下一句（real_next），直接当一条草稿，再合成 1 条还行的 + 2 条坏写法；
合成对话没有真实下一句，合成 2 条还行的 + 2 条坏写法。坏写法从 5 种里按对话 id 随机挑。

用法：python data/gen_drafts.py [--model sonnet] [--per-call 6] [--shard 0/2]
输入：data/raw/conversations.jsonl   输出：data/raw/drafts.jsonl，每行 {id, conv_id, tag, text}
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teacher import add_common_args, apply_shard, append_jsonl, model_arg, read_jsonl, run_batches  # noqa: E402

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
IN, OUT = os.path.join(RAW, "conversations.jsonl"), os.path.join(RAW, "drafts.jsonl")

TAGS = {
    "fitting": "写得合适：回应到对方真正想要的，语气和关系相称",
    "fitting_short": "也合适，但很短：一两句话就把该给的给了",
    "neutral_plain": "平淡但不出错：中规中矩，没接住情绪，也没得罪人",
    "too_cold": "太冷淡或太敷衍：一两个字、或明显不走心",
    "over_apologetic": "讨好过头：反复道歉、低姿态、承诺做不到的事",
    "over_explaining": "解释过多：一大段理由，像在为自己辩护",
    "misses_point": "答非所问或回避：说了别的事、转移话题、或没接住对方的情绪",
    "pushes_back": "顶回去：带情绪地反驳、讲道理压人、或阴阳怪气",
}
BAD = ["too_cold", "over_apologetic", "over_explaining", "misses_point", "pushes_back"]


def pick_tags(conv):
    """要让老师写的类型（不含 real_next）。"""
    rnd = random.Random(conv["id"])
    ok = [rnd.choice(["fitting_short", "neutral_plain"])] if conv.get("real_next") else ["fitting", rnd.choice(["fitting_short", "neutral_plain"])]
    return ok + rnd.sample(BAD, 2)


PROMPT = """下面有 {k} 段微信聊天，每段最后一条是对方发的，我还没回。请为每段写几条「我接下来可能发出去的回复草稿」，每段要写哪几种类型在该段下面列出。类型说明：
{tags}

要求：草稿要像我本人在微信上打字，口语、简短；同一段的几条要明显不同；不要在草稿里标注类型。

{convs}

只输出一个 JSON 数组，每个元素形如：
{{"conv_id": "...", "drafts": {{"类型名": "草稿", ...}}}}
键必须正好是该段要求的类型名。不要输出任何别的文字。"""


def fmt_conv(c):
    lines = "\n".join(f"  {'我' if m['from'] == 'me' else '对方'}：{m['text']}" for m in c["messages"])
    return f"### conv_id {c['id']}（{c['relationship']}）\n{lines}\n要写的类型：{', '.join(pick_tags(c))}"


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap, per_call=6)
    args = ap.parse_args()
    convs = read_jsonl(IN)
    done = {r["conv_id"] for r in read_jsonl(OUT)}
    todo = apply_shard([c for c in convs if c["id"] not in done], args.shard, args.limit)
    print(f"对话 {len(convs)} 段，已有草稿 {len(done)} 段，待生成 {len(todo)} 段")
    batches = [todo[i:i + args.per_call] for i in range(0, len(todo), args.per_call)]
    tags = "\n".join(f"- {k}：{v}" for k, v in TAGS.items())
    prompts = [PROMPT.format(k=len(b), tags=tags, convs="\n\n".join(fmt_conv(c) for c in b)) for b in batches]

    def handle(b, res):
        if not isinstance(res, list):
            return [], len(b)
        by_id = {r.get("conv_id"): r for r in res if isinstance(r, dict)}
        rows, bad = [], 0
        for c in b:
            d = ((by_id.get(c["id"]) or {}).get("drafts")) or {}
            want = pick_tags(c)
            if not all(isinstance(d.get(t), str) and d[t].strip() for t in want):
                bad += 1; continue
            if c.get("real_next"):
                rows.append({"id": f"{c['id']}_real_next", "conv_id": c["id"], "tag": "real_next", "text": c["real_next"]})
            for t in want:
                rows.append({"id": f"{c['id']}_{t}", "conv_id": c["id"], "tag": t, "text": d[t].strip()})
        return rows, bad

    w, bad = run_batches(batches, prompts, handle, args.tool, model_arg(args), args.workers, OUT)
    print(f"写入 {w} 条草稿，作废 {bad} 段 → {OUT}")


if __name__ == "__main__":
    main()
