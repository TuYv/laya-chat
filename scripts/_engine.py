"""真正调用 Laya 的地方。守护进程和评测脚本都用它，别的脚本不直接 import。"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from questions import BOOL_LABELS, JUDGE_QUESTIONS, RANK_KEYS, build_rank_question, build_state  # noqa: E402

MODEL_ID = os.environ.get("LAYA_CHAT_MODEL", "convaiinnovations/laya")
SUBFOLDER = os.environ.get("LAYA_CHAT_SUBFOLDER", "typed-decisions")   # 三份权重里评测最好的一份，见 README
DEVICE = os.environ.get("LAYA_CHAT_DEVICE") or None                  # None = 自动（cuda > mps > cpu）
# 7 道题里最长的一道有 10 个等级、每个等级一整句英文描述。Laya 默认给选项的 token 预算是
# 256，会把描述截得很短。README 建议对多选项题把 head_max_len 提到 512。
HEAD_MAX_LEN = int(os.environ.get("LAYA_CHAT_HEAD_MAX_LEN", "512"))
MAX_LEN = int(os.environ.get("LAYA_CHAT_MAX_LEN", "1024"))


class Engine:
    def __init__(self):
        self.agent = None
        self.lock = threading.Lock()
        self.load_error = None
        self.loaded_at = None

    @property
    def ready(self) -> bool:
        return self.agent is not None

    def load(self) -> None:
        import laya
        t = time.time()
        agent = laya.load(MODEL_ID, subfolder=SUBFOLDER or None, device=DEVICE)
        agent.cfg["head_max_len"] = HEAD_MAX_LEN
        agent.cfg["max_len"] = MAX_LEN
        self.agent = agent
        self.loaded_at = time.time()
        sys.stderr.write(
            f"[laya-chat] 模型已加载 {MODEL_ID}/{SUBFOLDER} device={agent.device} "
            f"head_max_len={HEAD_MAX_LEN} max_len={MAX_LEN} 用时 {time.time() - t:.1f}s\n"
        )

    def info(self) -> dict:
        return {
            "model": f"{MODEL_ID}/{SUBFOLDER}" if SUBFOLDER else MODEL_ID,
            "device": str(self.agent.device) if self.agent else None,
            "head_max_len": HEAD_MAX_LEN,
            "max_len": MAX_LEN,
        }

    def _predict(self, state, questions):
        with self.lock:
            return self.agent.predict(state, questions)

    def judge(self, messages, relationship, background="") -> dict:
        state = build_state(messages, relationship, background)
        t = time.time()
        raw = self._predict(state, JUDGE_QUESTIONS)["answers"]
        answers = {}
        for qid, a in raw.items():
            if a["type"] == "score":
                answers[qid] = {
                    "score": a["score"],
                    "level": int(round(a["score"])),
                    "max_level": len(JUDGE_QUESTIONS[qid]["criteria"]) - 1,
                    "confidence": a["confidence"],
                    "probabilities": a["probabilities"],
                }
            else:
                item = {
                    "choice": a["choice"],
                    "confidence": a["confidence"],
                    "probabilities": a["probabilities"],
                }
                if qid in BOOL_LABELS:
                    yes, _no = BOOL_LABELS[qid]
                    item["value"] = a["choice"] == yes
                    item["p_true"] = a["probabilities"].get(yes)
                answers[qid] = item
        return {
            "answers": answers,
            "latest_from": state["chat"]["latest_from"],
            "n_messages": len(state["chat"]["messages"]),
            "latency_ms": int((time.time() - t) * 1000),
            **self.info(),
        }

    def rank(self, messages, relationship, candidates, background="") -> dict:
        state = build_state(messages, relationship, background)
        q = build_rank_question(candidates)
        t = time.time()
        a = self._predict(state, q)["answers"]["best_reply"]
        ranked = [
            {"text": text, "key": key, "probability": a["probabilities"].get(key, 0.0)}
            for key, text in zip(RANK_KEYS, candidates)
        ]
        ranked.sort(key=lambda r: -r["probability"])
        for i, r in enumerate(ranked):
            r["rank"] = i + 1
        return {
            "ranked": ranked,
            "confidence": a["confidence"],
            "latency_ms": int((time.time() - t) * 1000),
            **self.info(),
        }


def summarize(judge_result: dict) -> str:
    """一行中文摘要，给人看的。"""
    a = judge_result["answers"]
    d = a["danger_level"]
    parts = [
        f"意图 {a['true_intent']['choice']}({a['true_intent']['confidence']:.2f})",
        f"危险 {d['score']:.1f}/{d['max_level']}",
        f"对方需要 {a['she_needs']['choice']}",
        f"最佳动作 {a['best_action']['choice']}",
        "有潜台词" if not a["literal_question"]["value"] else "字面意思",
        "现在给实质内容" if a["should_reply_now"]["value"] else "先别给实质内容",
        "紧张已解" if a["tension_resolved"]["value"] else "紧张未解",
    ]
    return " · ".join(parts)
