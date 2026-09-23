#!/usr/bin/env python3
"""把一条回复填进聊天软件的输入框。只粘贴，不发送。

用法：
  python scripts/fill.py --text "好的，我八点到" --x 1500 --y 1480 --capture /tmp/laya-chat/capture-xxx.json
  python scripts/fill.py --text "..." --clipboard-only          # 只复制到剪贴板，不碰界面
  echo "..." | python scripts/fill.py --x ... --y ... --capture ...

--x --y 是「截图上的像素坐标」，取输入框里面的一个点（由看图的助手给出）。
脚本用 capture 记录的窗口位置和缩放倍数换算成屏幕坐标。

顺序：文字进剪贴板 → 按进程号把聊天软件调到前台 → 确认它真的在前台 →
确认点击位置上最前面的窗口就是截图时那个窗口 → 点一下 → 再确认前台没变 → Cmd+V → 再截一张图供核对。
任何一步确认失败就中止，不点、不粘贴，文字留在剪贴板里。
这个文件里没有回车键。发送永远由人来按。

需要给终端开「辅助功能」权限（系统设置 > 隐私与安全性 > 辅助功能）。
填入的两三秒内用户不要碰鼠标键盘，否则焦点会被抢走，脚本会中止。
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bootstrap import print_json, reexec_in_venv_if_missing  # noqa: E402


def pbcopy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def osascript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True)


def frontmost_pid():
    r = osascript('tell application "System Events" to get unix id of first application process whose frontmost is true')
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def activate_pid(pid: int) -> None:
    osascript(f'tell application "System Events" to set frontmost of (first application process whose unix id is {pid}) to true')


def wait_frontmost(pid: int, seconds: float = 1.5) -> bool:
    t0 = time.time()
    while time.time() - t0 < seconds:
        if frontmost_pid() == pid:
            return True
        time.sleep(0.1)
    return frontmost_pid() == pid


def window_at_point(sx: float, sy: float):
    """屏幕上这个点最前面的普通窗口的编号。CGWindowListCopyWindowInfo 返回的顺序就是从前到后。"""
    import Quartz
    wins = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    for w in wins:
        if w.get("kCGWindowLayer", 0) != 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        if b.get("X", 0) <= sx <= b.get("X", 0) + b.get("Width", 0) and \
           b.get("Y", 0) <= sy <= b.get("Y", 0) + b.get("Height", 0):
            return int(w["kCGWindowNumber"]), w.get("kCGWindowOwnerName")
    return None, None


def abort(reason: str, **extra):
    print_json({"copied": True, "filled": False, "error": reason,
                "note": "没有点击、没有粘贴。文字在剪贴板里，用户可以自己 Cmd+V。", **extra})
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--x", type=float)
    ap.add_argument("--y", type=float)
    ap.add_argument("--capture", help="capture.py 输出的 .json 路径")
    ap.add_argument("--clipboard-only", action="store_true")
    ap.add_argument("--no-verify", action="store_true", help="填完不再截图核对")
    args = ap.parse_args()

    text = args.text if args.text is not None else sys.stdin.read()
    text = text.rstrip("\r\n")          # 去掉末尾换行，避免任何和「回车」沾边的东西
    if not text.strip():
        sys.stderr.write("[laya-chat] 文本为空\n")
        sys.exit(2)

    pbcopy(text)
    if args.clipboard_only:
        return print_json({"copied": True, "filled": False, "chars": len(text)})

    if args.x is None or args.y is None or not args.capture:
        sys.stderr.write("[laya-chat] 需要 --x --y --capture，或者用 --clipboard-only\n")
        sys.exit(2)
    reexec_in_venv_if_missing("Quartz")
    with open(args.capture, encoding="utf-8") as f:
        cap = json.load(f)
    win, scale = cap["window"], cap.get("scale") or 1.0
    pid, wid, app = cap.get("pid"), cap.get("window_id"), cap.get("app", "WeChat")
    sx = win["x"] + args.x / scale
    sy = win["y"] + args.y / scale
    inside = (win["x"] <= sx <= win["x"] + win["w"]) and (win["y"] <= sy <= win["y"] + win["h"])
    if not inside:
        abort(f"换算后的点 ({sx:.0f},{sy:.0f}) 不在 {app} 窗口范围内")
    if not pid:
        abort("capture json 里没有 pid，请重新截图")

    # 1. 调到前台并确认
    activate_pid(pid)
    if not wait_frontmost(pid):
        abort(f"{app} 没能成为前台应用（可能用户正在操作别的窗口）", frontmost_pid=frontmost_pid())
    # 2. 点击位置上最前面的窗口必须就是截图时那个窗口
    top_wid, top_owner = window_at_point(sx, sy)
    if top_wid != wid:
        abort(f"点击位置上最前面的窗口是 {top_owner!r}（编号 {top_wid}），和截图时的 {app}（编号 {wid}）不一致，"
              f"窗口可能被移动或遮挡，请重新截图")
    # 3. 点击，然后再确认一次前台没被抢走
    r = osascript(f'tell application "System Events" to click at {{{sx:.0f}, {sy:.0f}}}')
    if r.returncode != 0:
        err = r.stderr.strip()
        hint = ("没给终端开「辅助功能」权限：系统设置 > 隐私与安全性 > 辅助功能。"
                if ("1002" in err or "1719" in err or "not allowed" in err or "assistive" in err.lower()) else "")
        abort(f"点击失败：{err}", hint=hint)
    time.sleep(0.25)
    if frontmost_pid() != pid:
        abort(f"点击后前台应用变了（{frontmost_pid()}），放弃粘贴")
    # 4. 粘贴。只有 Cmd+V，没有别的按键。
    r = osascript('tell application "System Events" to keystroke "v" using command down')
    if r.returncode != 0:
        abort(f"粘贴失败：{r.stderr.strip()}")

    out = {"copied": True, "filled": True, "chars": len(text),
           "clicked_at": [round(sx), round(sy)],
           "note": "Cmd+V 已发给目标窗口，没有发送。请看 verify_image 确认文字进了输入框，再让用户自己按回车。"}
    if not args.no_verify:
        from capture import capture
        v = {}
        for _ in range(4):                      # 刚粘贴完窗口列表偶尔还没刷新，多试几次
            time.sleep(0.5)
            v = capture(app, tag="verify")
            if "image" in v:
                break
        out["verify_image"] = v.get("image") or v.get("error")
    print_json(out)


if __name__ == "__main__":
    main()
