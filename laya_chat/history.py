"""按会话在本机记录看到过的消息，供好感度判断用。~/.laya-chat/history/<会话名>.jsonl"""
import json
import re
import time
from pathlib import Path
from typing import List

MAX_PER_CHAT = 500
DEDUP_WINDOW = 40


class HistoryStore:
    def __init__(self, root: Path, enabled: bool = True, max_per_chat: int = MAX_PER_CHAT):
        self.root = Path(root)
        self.enabled = enabled
        self.max_per_chat = max_per_chat
        self._mem = {}

    def _path(self, chat: str) -> Path:
        safe = re.sub(r"[^\w一-鿿（）()\-]+", "_", chat)[:80] or "chat"
        return self.root / f"{safe}.jsonl"

    def _load(self, chat: str) -> List[dict]:
        if chat in self._mem:
            return self._mem[chat]
        items = []
        p = self._path(chat)
        if self.enabled and p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        self._mem[chat] = items[-self.max_per_chat:]
        return self._mem[chat]

    def merge(self, chat: str, visible: List[dict]) -> int:
        """把屏幕上可见的消息并进去，只追加没见过的。返回新增条数。"""
        items = self._load(chat)
        recent = {(m["side"], m["text"]) for m in items[-DEDUP_WINDOW:]}
        added = 0
        for m in visible:
            key = (m["side"], m["text"])
            if key in recent:
                continue
            rec = {"ts": time.time(), "side": m["side"], "text": m["text"]}
            items.append(rec)
            recent.add(key)
            added += 1
        del items[:-self.max_per_chat]
        if added and self.enabled:
            self.root.mkdir(parents=True, exist_ok=True)
            with open(self._path(chat), "a", encoding="utf-8") as f:
                for rec in items[-added:]:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return added

    def recent(self, chat: str, n: int = 30) -> List[dict]:
        return [{"from": m["side"], "text": m["text"]} for m in self._load(chat)[-n:]]

    def clear_all(self) -> int:
        n = 0
        if self.root.exists():
            for p in self.root.glob("*.jsonl"):
                p.unlink(); n += 1
        self._mem.clear()
        return n
