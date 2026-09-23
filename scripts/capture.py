#!/usr/bin/env python3
"""截取聊天软件的窗口，不用把它切到前台。

用法：
  python scripts/capture.py                 # 默认找微信
  python scripts/capture.py --app QQ

输出 JSON（同时写到图片旁边的同名 .json，供 fill.py 换算坐标）：
  {
    "image": "/tmp/laya-chat/capture-20260923-101500.png",
    "json":  "/tmp/laya-chat/capture-20260923-101500.json",
    "app": "微信", "window_id": 1234, "pid": 460,
    "window": {"x": 100, "y": 60, "w": 1200, "h": 800},   # 屏幕坐标，单位是点
    "image_size": [2400, 1600],                            # 图片像素
    "scale": 2.0                                           # 像素 / 点
  }

需要给运行它的终端开「屏幕录制」权限，否则截出来是黑图或空图。
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bootstrap import SHOT_DIR, print_json, reexec_in_venv_if_missing  # noqa: E402

# 进程名（kCGWindowOwnerName）可能的写法
APP_ALIASES = {
    "wechat": ["WeChat", "微信"],
    "微信": ["WeChat", "微信"],
    "qq": ["QQ"],
    "feishu": ["Lark", "Feishu", "飞书"],
    "飞书": ["Lark", "Feishu", "飞书"],
    "lark": ["Lark", "Feishu", "飞书"],
    "textedit": ["TextEdit", "文本编辑"],
}


def find_window(app: str):
    reexec_in_venv_if_missing("Quartz")
    import Quartz
    names = [n.lower() for n in APP_ALIASES.get(app.lower(), [app])]
    wins = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    best = None
    for w in wins:
        owner = (w.get("kCGWindowOwnerName") or "").lower()
        # 进程名会跟系统语言本地化（WeChat 显示为「微信」），所以按别名表和包含关系匹配
        if owner not in names and not any(n in owner for n in names):
            continue
        if w.get("kCGWindowLayer", 0) != 0:      # 0 是普通窗口，菜单、悬浮层不是
            continue
        b = w.get("kCGWindowBounds") or {}
        area = b.get("Width", 0) * b.get("Height", 0)
        if b.get("Width", 0) < 300 or b.get("Height", 0) < 300:
            continue
        if best is None or area > best[0]:
            best = (area, w)
    if best is None:
        return None
    w = best[1]
    b = w["kCGWindowBounds"]
    return {
        "app": w["kCGWindowOwnerName"],
        "window_id": int(w["kCGWindowNumber"]),
        "pid": int(w.get("kCGWindowOwnerPID", 0)),
        "title": w.get("kCGWindowName") or "",
        "window": {"x": int(b["X"]), "y": int(b["Y"]), "w": int(b["Width"]), "h": int(b["Height"])},
    }


def image_size(path):
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
                         capture_output=True, text=True).stdout
    w = h = None
    for line in out.splitlines():
        if "pixelWidth" in line:
            w = int(line.split()[-1])
        elif "pixelHeight" in line:
            h = int(line.split()[-1])
    return [w, h]


KEEP_SHOTS = 10


def prune_shots() -> None:
    """截图里有聊天内容，只留最近 KEEP_SHOTS 张，其余删掉。"""
    files = sorted(SHOT_DIR.glob("*.png"), key=lambda f: f.stat().st_mtime)
    for f in files[:-KEEP_SHOTS]:
        try:
            f.unlink()
            f.with_suffix(".json").unlink(missing_ok=True)
        except OSError:
            pass


def capture(app: str = "WeChat", tag: str = "capture") -> dict:
    info = find_window(app)
    if info is None:
        return {"error": f"没找到 {app} 的窗口。它是不是没打开、被最小化了、或者在另一个桌面空间？"}
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    prune_shots()
    stem = f"{tag}-{time.strftime('%Y%m%d-%H%M%S')}"
    png = SHOT_DIR / f"{stem}.png"
    r = subprocess.run(["screencapture", "-x", "-o", "-l", str(info["window_id"]), str(png)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not png.exists() or png.stat().st_size < 1000:
        return {"error": "screencapture 失败。多半是没给终端开「屏幕录制」权限："
                         "系统设置 > 隐私与安全性 > 屏幕录制。" + (r.stderr or "")}
    size = image_size(str(png))
    scale = round(size[0] / info["window"]["w"], 2) if size[0] and info["window"]["w"] else 1.0
    out = {"image": str(png), "json": str(SHOT_DIR / f"{stem}.json"),
           "image_size": size, "scale": scale, **info}
    with open(out["json"], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="WeChat")
    args = ap.parse_args()
    out = capture(args.app)
    print_json(out)
    sys.exit(1 if "error" in out else 0)


if __name__ == "__main__":
    main()
