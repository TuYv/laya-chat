"""常驻进程：加载一次 Laya，之后在本机端口上回答 judge / rank 请求。

由 judge.py / rank.py 在需要时自动拉起，不用手动运行。
闲置超过 LAYA_CHAT_IDLE_MIN 分钟（默认 60）自动退出，释放内存。
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import Engine  # noqa: E402

PORT = int(os.environ.get("LAYA_CHAT_PORT", "47321"))
IDLE_MIN = float(os.environ.get("LAYA_CHAT_IDLE_MIN", "60"))

engine = Engine()
last_used = time.time()


def _load():
    try:
        engine.load()
    except Exception as e:  # 记下来，health 接口会把原因报出去
        engine.load_error = f"{type(e).__name__}: {e}"
        sys.stderr.write(f"[laya-chat] 模型加载失败：{engine.load_error}\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[laya-chat] %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "ready": engine.ready, "error": engine.load_error,
                             "pid": os.getpid(), **engine.info()})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        global last_used
        last_used = time.time()
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            return self._send(400, {"error": f"bad json: {e}"})
        if engine.load_error:
            return self._send(503, {"error": engine.load_error})
        if not engine.ready:
            return self._send(503, {"error": "model still loading"})
        try:
            if self.path == "/judge":
                out = engine.judge(payload["messages"], payload.get("relationship", ""),
                                   payload.get("background", ""))
            elif self.path == "/rank":
                out = engine.rank(payload["messages"], payload.get("relationship", ""),
                                  payload["candidates"], payload.get("background", ""))
            else:
                return self._send(404, {"error": "not found"})
        except (KeyError, ValueError) as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        self._send(200, out)


def _idle_watch(server):
    while True:
        time.sleep(30)
        if time.time() - last_used > IDLE_MIN * 60:
            sys.stderr.write(f"[laya-chat] 闲置超过 {IDLE_MIN:g} 分钟，退出\n")
            threading.Thread(target=server.shutdown, daemon=True).start()
            return


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=_load, daemon=True).start()
    threading.Thread(target=_idle_watch, args=(server,), daemon=True).start()
    sys.stderr.write(f"[laya-chat] 守护进程 pid={os.getpid()} 监听 127.0.0.1:{PORT}\n")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
