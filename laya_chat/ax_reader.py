"""读微信窗口：会话名、最近的消息、输入框里的草稿。全部来自系统辅助功能树，不用文字识别。

我方 / 对方的区分：辅助功能树给不出左右，只给每条消息在屏幕上的纵坐标；
所以截一张窗口图，在那一行从右往左扫像素，绿色气泡是我方，浅灰气泡是对方。
只有可见消息列表变化时才截图，其余时候不截。

2026-09-23 在微信 mac 4.1 上验证：
- list 消息 的每个子元素：AXIdentifier 是 chat_bubble_item_view 的是气泡，title 是正文；
  identifier 为空的是时间戳；virtual_cell 是滚出屏幕的占位，没有内容。
  英文界面里这个 list 的 description 是 Messages，不是「消息」。
- 输入框是 AXTextArea，title 就是当前会话名；搜索框的 description 是「搜索」或 Search。
"""
import os
import subprocess
import tempfile
import time
from typing import Dict, List, Optional

import Quartz
from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
    AXValueGetValue,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

APP_ALIASES = {
    "wechat": ["WeChat", "微信"],
    "微信": ["WeChat", "微信"],
}

# 微信 mac 跟系统语言：中文界面叫「消息」，英文界面叫 Messages。
MESSAGE_LIST_NAMES = {"消息", "Messages", "messages"}
SEARCH_LABELS = {"搜索", "Search", "search"}


def _attr(el, name):
    err, v = AXUIElementCopyAttributeValue(el, name, None)
    return v if err == 0 else None


def _point(v):
    if v is None:
        return None
    ok, p = AXValueGetValue(v, kAXValueCGPointType, None)
    return (float(p.x), float(p.y)) if ok else None


def _size(v):
    if v is None:
        return None
    ok, s = AXValueGetValue(v, kAXValueCGSizeType, None)
    return (float(s.width), float(s.height)) if ok else None


class ChatReader:
    def __init__(self, app_name: str = "WeChat"):
        self.names = [n.lower() for n in APP_ALIASES.get(app_name.lower(), [app_name])]
        self._side_cache: Dict[str, str] = {}     # 消息标识 -> me / other
        self._last_titles = None
        self._ax_app = None
        self._pid = None

    # ---------- 窗口 ----------
    def find_window(self) -> Optional[dict]:
        wins = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        best = None
        for w in wins:
            owner = (w.get("kCGWindowOwnerName") or "").lower()
            if owner not in self.names and not any(n in owner for n in self.names):
                continue
            if w.get("kCGWindowLayer", 0) != 0:
                continue
            b = w.get("kCGWindowBounds") or {}
            if b.get("Width", 0) < 300 or b.get("Height", 0) < 300:
                continue
            area = b["Width"] * b["Height"]
            if best is None or area > best[0]:
                best = (area, w)
        if best is None:
            return None
        w = best[1]
        b = w["kCGWindowBounds"]
        return {
            "app": w["kCGWindowOwnerName"],
            "pid": int(w["kCGWindowOwnerPID"]),
            "window_id": int(w["kCGWindowNumber"]),
            "x": int(b["X"]), "y": int(b["Y"]), "w": int(b["Width"]), "h": int(b["Height"]),
        }

    # ---------- 辅助功能树 ----------
    def _app_element(self, pid: int):
        if self._ax_app is None or self._pid != pid:
            self._ax_app = AXUIElementCreateApplication(pid)
            self._pid = pid
        return self._ax_app

    def _walk(self, el, found, depth=0):
        if depth > 14:
            return
        role = _attr(el, "AXRole")
        if role == "AXList":
            name = _attr(el, "AXDescription") or _attr(el, "AXTitle") or ""
            if name in MESSAGE_LIST_NAMES:
                found["list"] = el
                return                       # 消息列表下面不用再走
        elif role == "AXTextArea":
            desc = _attr(el, "AXDescription") or ""
            title = _attr(el, "AXTitle") or ""
            if desc not in SEARCH_LABELS and title not in SEARCH_LABELS:
                found["textarea"] = el
        for c in _attr(el, "AXChildren") or []:
            self._walk(c, found, depth + 1)

    def read(self) -> Optional[dict]:
        """一次读取。返回 None 表示聊天软件没开或没有打开的会话。"""
        win = self.find_window()
        if win is None:
            return None
        app = self._app_element(win["pid"])
        windows = _attr(app, "AXWindows") or []
        if not windows:
            return None
        found = {"list": None, "textarea": None}
        self._walk(windows[0], found)
        if found["textarea"] is None or found["list"] is None:
            return {"window": win, "chat": None, "draft": "", "messages": []}
        chat = _attr(found["textarea"], "AXTitle") or ""
        draft = _attr(found["textarea"], "AXValue") or ""
        ib_p = _point(_attr(found["textarea"], "AXPosition"))
        ib_s = _size(_attr(found["textarea"], "AXSize"))
        input_box = {"x": ib_p[0], "y": ib_p[1], "w": ib_s[0], "h": ib_s[1]} if ib_p and ib_s else None
        messages = []
        for i, el in enumerate(_attr(found["list"], "AXChildren") or []):
            if _attr(el, "AXIdentifier") != "chat_bubble_item_view":
                continue
            s = _size(_attr(el, "AXSize"))
            p = _point(_attr(el, "AXPosition"))
            if not s or not p or s[1] <= 0:
                continue
            title = (_attr(el, "AXTitle") or "").strip()
            if not title:
                continue
            messages.append({"text": title, "x": p[0], "y": p[1], "w": s[0], "h": s[1], "idx": i})
        snap = {"window": win, "chat": chat, "draft": draft, "messages": messages,
                "input_box": input_box, "ts": time.time()}
        self._textarea = found["textarea"]
        self._assign_sides(snap)
        return snap

    # ---------- 我方 / 对方 ----------
    def _assign_sides(self, snap: dict) -> None:
        chat = snap["chat"]
        keys = [f"{chat}|{m['idx']}|{m['text']}" for m in snap["messages"]]
        missing = [k for k in keys if k not in self._side_cache]
        if missing:
            self._classify_by_pixels(snap, keys)
        for k, m in zip(keys, snap["messages"]):
            m["side"] = self._side_cache.get(k, "other")

    def _classify_by_pixels(self, snap: dict, keys: List[str]) -> None:
        from PIL import Image
        win = snap["window"]
        path = os.path.join(tempfile.gettempdir(), "laya-chat-side.png")
        r = subprocess.run(["screencapture", "-x", "-o", "-l", str(win["window_id"]), path],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(path):
            return
        im = Image.open(path).convert("RGB")
        scale = im.width / win["w"] if win["w"] else 1.0
        right_start = win["x"] + win["w"] - 110      # 跳过右侧头像列
        left_stop = win["x"] + 252 + 80              # 左侧头像列

        def px(sx, sy):
            ix, iy = int((sx - win["x"]) * scale), int((sy - win["y"]) * scale)
            if 0 <= ix < im.width and 0 <= iy < im.height:
                return im.getpixel((ix, iy))
            return (255, 255, 255)

        for k, m in zip(keys, snap["messages"]):
            if k in self._side_cache:
                continue
            cy = m["y"] + 24
            votes = {"me": 0, "other": 0}
            for sx in range(int(right_start), int(left_stop), -3):
                c = px(sx, cy)
                if min(c) > 242:
                    continue                                   # 背景
                if c[1] - max(c[0], c[2]) > 35:
                    votes["me"] += 1                           # 绿气泡
                elif min(c) >= 225 and max(c) - min(c) <= 6 and max(c) <= 242:
                    votes["other"] += 1                        # 浅灰气泡
            if any(votes.values()):
                self._side_cache[k] = max(votes, key=votes.get)
        try:
            os.remove(path)
        except OSError:
            pass

    # ---------- 写草稿 ----------
    def set_draft(self, text: str) -> bool:
        """把文字放进输入框（替换现有草稿）。只是放进去，不发送。"""
        ta = getattr(self, "_textarea", None)
        if ta is None:
            return False
        err = AXUIElementSetAttributeValue(ta, "AXValue", text)
        return err == 0


def dump(app_name="WeChat"):
    """命令行调试：python -m laya_chat.ax_reader"""
    import json
    r = ChatReader(app_name)
    t = time.time()
    s = r.read()
    print(f"took {(time.time() - t) * 1000:.0f} ms")
    if s is None:
        print("no window")
        return
    out = {"chat": s["chat"], "draft": s["draft"], "window": s["window"],
           "messages": [{"side": m["side"], "text": m["text"][:20], "y": m["y"]} for m in s["messages"]]}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    dump()
