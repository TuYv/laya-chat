"""悬浮窗：贴在聊天窗口右侧、底边和输入框平齐，不抢焦点。

内容由 app 以「行」的形式给进来（setRows_），每行是一个 dict：
  {"type": "text", "text": "...", "size": 12, "bold": False, "color": "white|green|dim|amber|red|title"}
  {"type": "bar", "value": 0.57, "color": "auto|risk|green|amber|red"}      # 0 到 1
  {"type": "gap", "h": 6}
候选和求助按钮单独管理。AppKit 只能在主线程动，外部一律通过 AppHelper.callAfter 调这里的方法。
"""
import objc
from AppKit import (
    NSBackingStoreBuffered, NSButton, NSColor, NSFloatingWindowLevel, NSFont, NSMakeRect, NSPanel,
    NSScreen, NSTextField, NSView, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary, NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
    NSBezelStyleRounded,
)
from Foundation import NSObject
from Quartz import CATransaction
from AppKit import NSAnimationContext

PAD = 14
BAR_H = 7
PANEL_H = 640          # 窗口固定高度，内容卡片贴底往上长；窗口本身从不改大小，所以不闪


def _rgb(r, g, b):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)


COLORS = {
    "white": NSColor.whiteColor(),
    "title": _rgb(0.95, 0.95, 0.97),
    "dim": NSColor.colorWithCalibratedWhite_alpha_(0.62, 1.0),
    "green": _rgb(0.50, 0.88, 0.42),
    "amber": _rgb(0.97, 0.76, 0.28),
    "red": _rgb(0.93, 0.42, 0.38),
    "blue": _rgb(0.45, 0.72, 0.98),
}


def level_color(v):
    """0 到 1，低=红、中=琥珀、高=绿。"""
    return COLORS["red"] if v < 0.35 else COLORS["amber"] if v < 0.6 else COLORS["green"]


class Overlay(NSObject):

    def initWithWidth_callbacks_(self, width, callbacks):
        self = objc.super(Overlay, self).init()
        if self is None:
            return None
        self.width = width
        self.callbacks = callbacks          # {"help": fn(), "fill": fn(i), "copy": fn(i)}
        self.rows = [{"type": "text", "text": "模型加载中…", "color": "dim"}]
        self.candidates = []
        self.help_title = "求助"
        self.help_enabled = True
        self.status = ""
        self._widgets = []
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, width, PANEL_H), style, NSBackingStoreBuffered, False)
        self.panel.setLevel_(NSFloatingWindowLevel)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary)
        self.panel.setAlphaValue_(0.97)
        self.card = None                                  # 当前显示的内容卡片
        self.root = self._new_root(120)
        self.relayout()
        return self

    # ---------- 部件 ----------
    @objc.python_method
    def _label(self, text, size=12, bold=False, color="white", width=None):
        w = width or (self.width - 2 * PAD)
        f = NSTextField.alloc().initWithFrame_(NSMakeRect(PAD, 0, w, 18))
        f.setStringValue_(text)
        f.setBezeled_(False); f.setDrawsBackground_(False); f.setEditable_(False); f.setSelectable_(False)
        f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
        f.setTextColor_(COLORS.get(color, COLORS["white"]))
        f.setLineBreakMode_(0)
        f.setMaximumNumberOfLines_(0)
        f.setPreferredMaxLayoutWidth_(w)
        h = f.sizeThatFits_((w, 10000)).height
        f.setFrame_(NSMakeRect(PAD, 0, w, h))
        return f, h

    @objc.python_method
    def _bar(self, y, value, color):
        w = self.width - 2 * PAD
        v = max(0.0, min(1.0, float(value)))
        track = NSView.alloc().initWithFrame_(NSMakeRect(PAD, y, w, BAR_H))
        track.setWantsLayer_(True)
        track.layer().setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.13).CGColor())
        track.layer().setCornerRadius_(BAR_H / 2)
        fill = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, max(BAR_H, w * v), BAR_H))
        fill.setWantsLayer_(True)
        if color == "auto":
            c = level_color(v)
        elif color == "risk":
            c = level_color(1.0 - v)          # 风险越高越红
        else:
            c = COLORS.get(color, COLORS["green"])
        fill.layer().setBackgroundColor_(c.CGColor())
        fill.layer().setCornerRadius_(BAR_H / 2)
        track.addSubview_(fill)
        self.root.addSubview_(track); self._widgets.append(track)

    @objc.python_method
    def _button(self, title, x, y, w, action, tag=0, enabled=True):
        b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 26))
        b.setTitle_(title); b.setBezelStyle_(NSBezelStyleRounded)
        b.setEnabled_(enabled); b.setTarget_(self); b.setAction_(action); b.setTag_(tag)
        self.root.addSubview_(b); self._widgets.append(b)

    # ---------- 布局 ----------
    @objc.python_method
    def _new_root(self, height):
        root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, self.width, height))
        root.setWantsLayer_(True)
        root.layer().setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.11, 0.12, 0.14, 0.94).CGColor())
        root.layer().setCornerRadius_(14)
        root.layer().setBorderWidth_(1.0)
        root.layer().setBorderColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.08).CGColor())
        return root

    @objc.python_method
    def relayout(self):
        # 在一个新的容器里把内容整个搭好，最后一次性换进窗口，避免中间出现空白
        self.root = self._new_root(120)
        self._widgets = []
        # 先量高度
        items = []                                   # (kind, obj, height)
        for r in self.rows:
            if r["type"] == "text":
                f, h = self._label(r["text"], r.get("size", 12), r.get("bold", False), r.get("color", "white"))
                items.append(("text", f, h + 4))
            elif r["type"] == "bar":
                items.append(("bar", r, BAR_H + 8))
            elif r["type"] == "gap":
                items.append(("gap", None, r.get("h", 6)))
        cand = []
        for i, text in enumerate(self.candidates):
            f, h = self._label(f"{i + 1}. {text}", 12, False, "white")
            cand.append((f, h))
        total = PAD + sum(h for _, _, h in items)
        total += sum(h + 4 + 26 + 8 for _, h in cand)
        total += 30                                   # 求助按钮
        if self.status:
            sf, sh = self._label(self.status, 11, False, "dim")
            total += sh + 6
        total += PAD
        # 再从上往下放（AppKit 原点在左下，所以 y 往下减）
        y = total - PAD
        for kind, obj, h in items:
            y -= h
            if kind == "text":
                obj.setFrameOrigin_((PAD, y + 4))
                self.root.addSubview_(obj); self._widgets.append(obj)
            elif kind == "bar":
                self._bar(y + 4, obj["value"], obj.get("color", "auto"))
        for i, (f, h) in enumerate(cand):
            y -= h
            f.setFrameOrigin_((PAD, y))
            self.root.addSubview_(f); self._widgets.append(f)
            y -= 4 + 26
            self._button("填入", PAD, y, 60, "fillClicked:", i)
            self._button("复制", PAD + 66, y, 60, "copyClicked:", i)
            y -= 8
        y -= 30
        self._button(self.help_title, PAD, y + 2, 190, "helpClicked:", 0, self.help_enabled)
        if self.status:
            y -= sh + 6
            sf.setFrameOrigin_((PAD, y))
            self.root.addSubview_(sf); self._widgets.append(sf)
        total = min(total, PANEL_H)
        self.card_h = total
        self.title_h = items[0][2] if items and items[0][0] == "text" else 0
        self.root.setFrame_(NSMakeRect(0, 0, self.width, total))       # 贴在窗口底部
        CATransaction.begin(); CATransaction.setDisableActions_(True)
        NSAnimationContext.beginGrouping(); NSAnimationContext.currentContext().setDuration_(0)
        self.panel.contentView().addSubview_(self.root)
        if self.card is not None:
            self.card.removeFromSuperview()
        self.card = self.root
        NSAnimationContext.endGrouping(); CATransaction.commit()
        self.panel.invalidateShadow()

    # ---------- 外部调用（主线程） ----------
    def setRows_(self, rows):
        rows = list(rows or [])
        if rows == self.rows:
            return
        self.rows = rows
        self.relayout()

    def setStatus_(self, text):
        text = text or ""
        if text == self.status:
            return
        self.status = text
        self.relayout()

    def setCandidates_(self, cands):
        cands = list(cands or [])
        if cands == self.candidates:
            return
        self.candidates = cands
        self.relayout()

    def setHelpTitle_enabled_(self, title, enabled):
        self.help_title = title
        self.help_enabled = bool(enabled)
        self.relayout()

    def moveNextTo_anchor_(self, win, box):
        """win 是 Quartz 坐标（原点在第一块屏幕左上角，y 向下）的窗口框；box 是输入框的框。
        面板底边和输入框底边平齐，内容多了往上长。换算必须用第一块屏幕的高度，和窗口在哪块屏无关。"""
        if not win:
            self.panel.orderOut_(None)
            return
        screens = NSScreen.screens()
        primary_h = screens[0].frame().size.height
        ph = self.panel.frame().size.height
        win_top_ak = primary_h - win["y"]
        cx, cy = win["x"] + win["w"] / 2, win_top_ak - win["h"] / 2
        screen = screens[0]
        for s in screens:
            f = s.frame()
            if f.origin.x <= cx <= f.origin.x + f.size.width and f.origin.y <= cy <= f.origin.y + f.size.height:
                screen = s
                break
        sf = screen.frame()
        x = win["x"] + win["w"] + 8
        if x + self.width > sf.origin.x + sf.size.width:
            x = max(sf.origin.x, win["x"] - self.width - 8)
        if box:
            y = primary_h - (box["y"] + box["h"])           # 窗口底边和输入框底边平齐
        else:
            y = win_top_ak - win["h"]
        y = max(sf.origin.y, y)
        avail = sf.origin.y + sf.size.height - y             # 这块屏上、输入框底边以上还有多高
        want_h = max(120, min(PANEL_H, avail))
        cur = self.panel.frame()
        if abs(cur.size.height - want_h) > 1:                # 极少发生：换屏或窗口贴顶时
            self.panel.setFrame_display_(NSMakeRect(x, y, self.width, want_h), False)
        elif abs(cur.origin.x - x) > 0.5 or abs(cur.origin.y - y) > 0.5:
            self.panel.setFrameOrigin_((x, y))
        try:                                                  # 卡片几何（Quartz 坐标，原点左上）
            import json, os
            fr = self.panel.frame()
            os.makedirs("/tmp/laya-chat", exist_ok=True)
            with open("/tmp/laya-chat/overlay.json", "w") as f:
                json.dump({"x": fr.origin.x, "panel_top": primary_h - (fr.origin.y + fr.size.height),
                           "panel_h": fr.size.height, "w": self.width,
                           "card_top": primary_h - fr.origin.y - getattr(self, "card_h", 0),
                           "card_h": getattr(self, "card_h", 0), "title_h": getattr(self, "title_h", 0)}, f)
        except Exception:
            pass
        if not self.panel.isVisible():
            self.panel.orderFrontRegardless()

    def hide(self):
        self.panel.orderOut_(None)

    # ---------- 按钮 ----------
    def helpClicked_(self, sender):
        self.callbacks["help"]()

    def fillClicked_(self, sender):
        self.callbacks["fill"](sender.tag())

    def copyClicked_(self, sender):
        self.callbacks["copy"](sender.tag())
