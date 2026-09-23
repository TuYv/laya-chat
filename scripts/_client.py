"""judge.py / rank.py 的薄客户端：确认守护进程在跑（不在就拉起来），然后发请求。"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from _bootstrap import SCRIPTS, STATE_DIR, venv_python

PORT = int(os.environ.get("LAYA_CHAT_PORT", "47321"))
BASE = f"http://127.0.0.1:{PORT}"
# 首次运行要下载约 850 MB 权重，给足时间
STARTUP_TIMEOUT = float(os.environ.get("LAYA_CHAT_STARTUP_TIMEOUT", "1200"))


def health():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return None


def spawn_daemon():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(STATE_DIR / "daemon.log", "ab")
    subprocess.Popen(
        [venv_python(), str(SCRIPTS / "_daemon.py")],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        start_new_session=True, cwd=str(SCRIPTS),
    )


def ensure_daemon():
    h = health()
    if h is None:
        sys.stderr.write("[laya-chat] 正在启动本地判断进程（首次运行会下载约 850 MB 权重，之后只需几秒）...\n")
        spawn_daemon()
    t0 = time.time()
    dots = 0
    while time.time() - t0 < STARTUP_TIMEOUT:
        h = health()
        if h and h.get("ready"):
            return h
        if h and h.get("error"):
            sys.stderr.write(f"[laya-chat] 模型加载失败：{h['error']}\n"
                             f"  日志在 {STATE_DIR / 'daemon.log'}\n")
            sys.exit(3)
        time.sleep(2)
        dots += 1
        if dots % 5 == 0:
            sys.stderr.write(".")
            sys.stderr.flush()
    sys.stderr.write(f"\n[laya-chat] 等了 {STARTUP_TIMEOUT:.0f} 秒模型还没就绪，看看 {STATE_DIR / 'daemon.log'}\n")
    sys.exit(3)


def call(path: str, payload: dict, timeout: float = 300) -> dict:
    ensure_daemon()
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except Exception:
            msg = str(e)
        sys.stderr.write(f"[laya-chat] 判断进程返回 HTTP {e.code}：{msg}\n")
        sys.exit(4)


def stop_daemon():
    h = health()
    if not h:
        return False
    os.kill(h["pid"], 15)
    return True
