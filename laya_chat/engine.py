"""进程内加载 Laya，回答两套题目。"""
import threading
import time

from .questions_send import (AFFINITY_QUESTIONS, AFFINITY_WORDS, LABELS, SEND_QUESTIONS,
                             build_affinity_state, build_send_state)


class Engine:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.agent = None
        self.error = None
        self.lock = threading.Lock()

    @property
    def ready(self):
        return self.agent is not None

    def load(self):
        try:
            import laya
            t = time.time()
            sub = self.cfg.get("subfolder") or None
            agent = laya.load(self.cfg["model"], subfolder=sub, device=self.cfg.get("device") or None)
            agent.cfg["head_max_len"] = int(self.cfg.get("head_max_len", 512))
            agent.cfg["max_len"] = int(self.cfg.get("max_len", 1024))
            self.agent = agent
            self.load_seconds = time.time() - t
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"

    def load_in_background(self):
        threading.Thread(target=self.load, daemon=True).start()

    def ask(self, state, questions):
        with self.lock:
            return self.agent.predict(state, questions)["answers"]

    # ---------- 好感度 ----------
    def judge_affinity(self, messages, relationship):
        state = build_affinity_state(messages, relationship,
                                     int(self.cfg.get("memory_messages", 30)), int(self.cfg.get("memory_chars", 700)))
        a = self.ask(state, AFFINITY_QUESTIONS)
        score = float(a["affinity"]["score"])
        return {
            "score": score,
            "score100": int(round(score / 9 * 100)),
            "level": int(round(score)),
            "label": AFFINITY_WORDS[max(0, min(9, int(round(score))))],
            "trend": a["trend"]["choice"],
            "trend_zh": LABELS["trend"][a["trend"]["choice"]],
            "open_issue": a["open_issue"]["choice"],
            "open_issue_zh": LABELS["open_issue"][a["open_issue"]["choice"]],
            "confidence": a["affinity"]["confidence"],
            "probabilities": {k: v["probabilities"] for k, v in a.items()},
            "n_messages": len(state["chat"]["messages"]),
        }

    # ---------- 发送后果 ----------
    def judge_send(self, messages, relationship, draft, affinity=None):
        t = time.time()
        a = self.ask(build_send_state(messages, relationship, draft, affinity,
                                      int(self.cfg.get("context_messages", 10)), int(self.cfg.get("memory_chars", 700))),
                     SEND_QUESTIONS)
        out = {"draft": draft, "latency_ms": int((time.time() - t) * 1000), "items": {}}
        for qid, ans in a.items():
            if ans["type"] == "score":
                lvl = float(ans["score"])
                item = {"score": lvl, "probabilities": ans["probabilities"], "confidence": ans["confidence"]}
                if qid == "affinity_change":
                    item["delta"] = lvl - 2.0
                    item["delta100"] = int(round((lvl - 2.0) / 9 * 100))   # 每档 1 分，换成 100 分制
                    item["zh"] = LABELS["affinity_change"][max(0, min(4, int(round(lvl))))]
                else:
                    item["zh"] = f"{lvl:.1f}/9"
            else:
                item = {"choice": ans["choice"], "probabilities": ans["probabilities"],
                        "confidence": ans["confidence"],
                        "zh": LABELS.get(qid, {}).get(ans["choice"], ans["choice"])}
            out["items"][qid] = item
        return out
