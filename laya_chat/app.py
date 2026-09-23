"""主循环。一个工作线程每秒读一次微信；界面更新通过 AppHelper.callAfter 交给主线程。"""
import json
import re
import subprocess
import sys
import threading
import time
import traceback

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
from PyObjCTools import AppHelper

from . import ai_help, config
from .ax_reader import ChatReader
from .engine import Engine
from .history import HistoryStore
from .overlay import Overlay
from .questions_send import LABELS


def pbcopy(text):
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False)


def risk_word(score):
    return "低" if score < 2.5 else "中" if score < 5.5 else "高" if score < 7.5 else "很高"


def todo_items(messages, affinity):
    """待办：你最后一条消息之后对方发的每一条都算一件要回的事。"""
    last_me = max([i for i, m in enumerate(messages) if m["side"] == "me"] or [-1])
    pending = [m["text"] for m in messages[last_me + 1:]
               if m["side"] == "other" and not re.fullmatch(r"\[.*\]", m["text"].strip())]
    items = [f"回复「{t[:18] + ('…' if len(t) > 18 else '')}」" for t in pending][-3:]
    if not items and affinity and affinity.get("open_issue") == "unresolved_issue":
        items = ["对方还有事没了结，先接住再说别的"]
    return items


class App:
    def __init__(self):
        self.cfg = config.load()
        self.tool = ai_help.resolve(self.cfg.get("ai_tool", "auto"))   # claude / codex / None
        self.reader = ChatReader(self.cfg["app_name"])
        self.engine = Engine(self.cfg)
        self.history = HistoryStore(config.HOME / "history", enabled=bool(self.cfg["keep_history"]),
                                    max_per_chat=int(self.cfg.get("history_max", 500)))
        self.overlay = None
        self.chat = None
        self.rel = ""
        self.messages = []
        self.affinity = None
        self.snapshot = None
        self.last_draft = ""
        self.draft_changed_at = 0.0
        self.judged_draft = None
        self.judgment = None
        self.ai = None
        self.ai_for_draft = None
        self.candidates = []
        self.last_msgs_key = None
        self.pending_sent = None            # 我刚发出去、还没等到对方回复的那条：{text, judgment, affinity_before}
        self.last_actual = None             # 对方回复后实际的好感度变化：{delta, reply}
        self.busy = threading.Lock()

    def record_feedback(self, rec):
        """预计 vs 实际，记在本机，供以后用真实聊天再训练。"""
        if not self.cfg["keep_history"]:
            return
        try:
            config.HOME.mkdir(parents=True, exist_ok=True)
            with open(config.HOME / "feedback.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ---------- 界面（主线程） ----------
    def ui(self, fn, *args):
        AppHelper.callAfter(fn, *args)

    def set_status(self, text):
        self.ui(self.overlay.setStatus_, text)

    def render(self):
        """根据当前状态拼出悬浮窗的所有行。"""
        T = lambda text, **kw: {"type": "text", "text": text, **kw}  # noqa: E731
        rows = []
        if not self.chat:
            rows.append(T("没有打开的会话", color="dim"))
        else:
            rows.append(T(f"{self.chat} · {self.rel}", size=13, bold=True, color="title"))
        if not self.engine.ready:
            rows.append(T("模型加载失败：" + self.engine.error if self.engine.error else "模型加载中…", color="dim"))
        elif self.affinity:
            a = self.affinity
            rows.append({"type": "gap", "h": 2})
            line = f"好感度  {a['score100']} / 100   {a['label']} · {a['trend_zh']}"
            rows.append(T(line, size=12, bold=True, color="green"))
            if self.last_actual:
                d = self.last_actual["delta"]
                if abs(d) <= 3:
                    rows.append(T("对方回复后  — 基本没变", size=11, color="dim"))
                else:
                    rows.append(T(f"对方回复后  {'▲' if d > 0 else '▼'} {abs(d)}", size=11,
                                  color="green" if d > 0 else "red"))
            rows.append({"type": "bar", "value": a["score100"] / 100.0, "color": "auto"})
            todos = todo_items(self.messages, a)
            if todos:
                rows.append(T("待办", size=11, color="dim"))
                for t in todos:
                    rows.append(T(f"☐ {t}", color="amber"))
            else:
                rows.append(T("待办  无", size=11, color="dim"))
            rows.append(T(f"会话记忆：近 {a['n_messages']} 条", size=11, color="dim"))
        if self.judgment:
            it = self.judgment["items"]
            rows.append({"type": "gap", "h": 8})
            rows.append(T("这条发出去", size=12, bold=True, color="title"))
            top = sorted(it["reaction"]["probabilities"].items(), key=lambda kv: -kv[1])[:2]
            rows.append(T("对方反应  " + " · ".join(f"{LABELS['reaction'].get(k, k)} {v:.0%}" for k, v in top)))
            risk = it["risk_after_send"]["score"]
            rows.append(T(f"风险  {risk:.1f} / 9   {risk_word(risk)}", color="amber" if risk >= 5.5 else "white"))
            rows.append({"type": "bar", "value": risk / 9.0, "color": "risk"})
            d = it["affinity_change"]["delta100"]
            if abs(d) <= 3:
                rows.append(T("好感度  预计 — 基本不变", color="dim"))
            else:
                word = ("略升" if d <= 12 else "明显上升") if d > 0 else ("略降" if d >= -12 else "明显下降")
                rows.append(T(f"好感度  预计 {'▲' if d > 0 else '▼'} {abs(d)}   {word}", color="green" if d > 0 else "red"))
            tags = []
            tags.append(("回应到点上", "dim") if it["addresses_need"]["choice"] == "addresses" else ("没回应到点上", "amber"))
            tags.append(("语气合适", "dim") if it["tone"]["choice"] == "fitting" else (f"语气{it['tone']['zh']}", "amber"))
            tags.append(("能收住", "dim") if it["invites_followup"]["choice"] == "closes_cleanly" else ("会引来追问", "amber"))
            warn = [t for t, c in tags if c == "amber"]
            fine = [t for t, c in tags if c == "dim"]
            if warn:
                rows.append(T("⚠ " + " · ".join(warn), color="amber"))
            if fine:
                rows.append(T("✓ " + " · ".join(fine), color="dim"))
        if self.ai:
            rows.append({"type": "gap", "h": 8})
            rows.append(T(f"{ai_help.DISPLAY[self.tool]} 的看法", size=12, bold=True, color="blue"))
            rows.append(T(self.ai["verdict"] or self.ai["raw"][:200], color="white"))
        self.ui(self.overlay.setRows_, rows)

    def clear_ai(self):
        """清掉求助得到的看法和候选。返回是否真的清了东西（调用方据此重画）。"""
        if self.ai is None and not self.candidates:
            return False
        self.ai = None
        self.candidates = []
        self.ai_for_draft = None
        self.ui(self.overlay.setCandidates_, [])
        return True

    # ---------- 工作线程 ----------
    def worker(self):
        while True:
            try:
                self.tick()
            except Exception:
                traceback.print_exc()
            time.sleep(float(self.cfg["poll_interval"]))

    def tick(self):
        snap = self.reader.read()
        if snap is None or not snap.get("chat"):
            self.ui(self.overlay.hide)
            return
        self.snapshot = snap
        self.ui(self.overlay.moveNextTo_anchor_, snap["window"], snap.get("input_box"))
        if not self.engine.ready:
            if snap["chat"] != self.chat:
                self.chat = snap["chat"]; self.rel = config.relationship_for(self.cfg, snap["chat"])
            self.render()
            return

        rel = config.relationship_for(self.cfg, snap["chat"])
        changed = False
        # 1. 切换会话
        if snap["chat"] != self.chat:
            self.chat, self.rel = snap["chat"], rel
            self.affinity = None
            self.judged_draft = None
            self.judgment = None
            self.clear_ai()
            self.last_msgs_key = None
            self.pending_sent = None
            self.last_actual = None
            changed = True
        # 2. 消息有变化：记历史、重算好感度、作废旧建议
        msgs_key = tuple((m["side"], m["text"]) for m in snap["messages"])
        if msgs_key != self.last_msgs_key and snap["messages"]:
            old_key = self.last_msgs_key or ()
            self.last_msgs_key = msgs_key
            self.messages = snap["messages"]
            new_msgs = [m for m in snap["messages"] if (m["side"], m["text"]) not in set(old_key)]
            # 我刚才判断过的草稿出现在了新消息里 → 发出去了，记下发送前的好感度
            if self.judged_draft and any(m["side"] == "me" and m["text"] == self.judged_draft for m in new_msgs):
                self.pending_sent = {"text": self.judged_draft, "judgment": self.judgment,
                                     "affinity_before": self.affinity, "ts": time.time()}
                self.last_actual = None
            self.history.merge(snap["chat"], snap["messages"])
            hist = self.history.recent(snap["chat"], int(self.cfg.get("memory_messages", 30))) if self.cfg["keep_history"] else \
                [{"from": m["side"], "text": m["text"]} for m in snap["messages"]]
            self.set_status("正在判断好感度…")
            self.affinity = self.engine.judge_affinity(hist, rel)
            self.set_status("")
            # 对方回复了我发出去的那条 → 实际变化 = 回复后的好感度 - 发送前的好感度
            replies = [m for m in new_msgs if m["side"] == "other"]
            if self.pending_sent and replies and self.pending_sent.get("affinity_before"):
                before = self.pending_sent["affinity_before"]["score100"]
                delta = self.affinity["score100"] - before
                self.last_actual = {"delta": delta, "reply": replies[-1]["text"]}
                pj = self.pending_sent.get("judgment") or {}
                self.record_feedback({
                    "ts": time.time(), "chat": snap["chat"], "relationship": rel,
                    "sent": self.pending_sent["text"], "reply": replies[-1]["text"],
                    "affinity_before": before, "affinity_after": self.affinity["score100"], "actual_delta": delta,
                    "predicted": {k: {"choice": v.get("choice"), "score": v.get("score"), "delta100": v.get("delta100")}
                                  for k, v in (pj.get("items") or {}).items()},
                })
                self.pending_sent = None
            self.judged_draft = None
            self.clear_ai()
            changed = True
        # 3. 草稿
        draft = snap["draft"].strip()
        now = time.time()
        if draft != self.last_draft:
            self.last_draft = draft
            self.draft_changed_at = now
            # 草稿变成了和求助时不一样的内容才清建议；草稿为空但求助时也为空，保留
            if self.ai is not None and draft != self.ai_for_draft and draft not in self.candidates:
                changed = self.clear_ai() or changed
        if not draft:
            if self.judgment is not None:
                self.judgment = None; changed = True
        elif draft != self.judged_draft and now - self.draft_changed_at >= float(self.cfg["draft_debounce"]):
            self.set_status("正在判断这条发出去会怎样…")
            msgs = [{"from": m["side"], "text": m["text"]} for m in snap["messages"]]
            self.judgment = self.engine.judge_send(msgs, rel, draft, self.affinity)
            self.judged_draft = draft
            self.set_status("")
            changed = True
        if changed:
            self.render()

    # ---------- 按钮 ----------
    def on_help(self):
        tool = self.tool
        if not tool:
            self.set_status("本机没找到 claude 或 codex 命令，装一个之后重启程序")
            return
        if not self.snapshot or not self.snapshot.get("chat"):
            return
        if not self.busy.acquire(blocking=False):
            return
        snap = self.snapshot

        def run():
            try:
                self.set_status(f"正在问 {ai_help.DISPLAY[tool]}…（只有这一步会用 AI 工具）")
                rel = config.relationship_for(self.cfg, snap["chat"])
                msgs = [{"from": m["side"], "text": m["text"]} for m in snap["messages"]]
                res = ai_help.ask(tool, snap["chat"], rel, msgs, self.affinity, snap["draft"], self.judgment)
                self.ai = res
                self.ai_for_draft = snap["draft"].strip()
                self.candidates = res["candidates"]
                self.render()
                self.ui(self.overlay.setCandidates_, self.candidates)
                self.set_status("")
            except Exception as e:
                self.set_status(f"{ai_help.DISPLAY[tool]} 出错：{e}")
            finally:
                self.busy.release()
        threading.Thread(target=run, daemon=True).start()

    def on_fill(self, i):
        if i >= len(self.candidates):
            return
        text = self.candidates[i]
        if self.reader.set_draft(text):
            self.set_status("已填进输入框，没有发送。")
        else:
            pbcopy(text)
            self.set_status("输入框不接受直接写入，已复制到剪贴板，请 Cmd+V。")

    def on_copy(self, i):
        if i < len(self.candidates):
            pbcopy(self.candidates[i])
            self.set_status("已复制。")

    # ---------- 启动 ----------
    def run(self):
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.overlay = Overlay.alloc().initWithWidth_callbacks_(
            int(self.cfg["overlay_width"]),
            {"help": self.on_help, "fill": self.on_fill, "copy": self.on_copy})
        if self.tool:
            self.overlay.setHelpTitle_enabled_(f"求助 {ai_help.DISPLAY[self.tool]}", True)
        else:
            self.overlay.setHelpTitle_enabled_("没有可用的求助工具", False)
        self.engine.load_in_background()
        threading.Thread(target=self.worker, daemon=True).start()
        print("[laya-chat] 运行中，Ctrl+C 退出", file=sys.stderr)
        AppHelper.runEventLoop()


def main():
    App().run()
