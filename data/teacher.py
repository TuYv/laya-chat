"""调用老师模型：本机的 claude -p（默认）或 codex exec。批量、要严格 JSON、失败重试、每批完成即写盘。"""
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class TeacherPaused(Exception):
    """用量窗口耗尽之类的暂时性拒绝：不算失败，等一会再试。"""


WAIT_STEP = int(os.environ.get("TEACHER_WAIT_STEP", "600"))          # 等待时每次间隔（秒）
WAIT_MAX = float(os.environ.get("TEACHER_WAIT_HOURS", "8")) * 3600    # 最多等多久


def _run(tool: str, prompt: str, timeout: int, model=None) -> str:
    if tool == "claude":
        cmd = ["claude", "-p", prompt, "--output-format", "json"] + (["--model", model] if model else [])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            msg = (r.stderr or r.stdout).strip()
            if any(k in msg.lower() for k in ("limit", "usage", "credit", "rate")):
                raise TeacherPaused(msg[:300])
            raise RuntimeError(msg[:400])
        try:
            env = json.loads(r.stdout)
        except json.JSONDecodeError:
            return r.stdout
        if isinstance(env, dict):
            result = env.get("result") or ""
            # 用量耗尽时 CLI 返回 is_error 或者一个 duration_api_ms=0 的空信封
            if env.get("is_error") or (env.get("duration_api_ms") == 0 and not result.strip()):
                raise TeacherPaused(str(result)[:300] or "空信封，duration_api_ms=0")
            return result
        return r.stdout
    if tool == "codex":
        tmp = tempfile.NamedTemporaryFile("r", suffix=".txt", delete=False, encoding="utf-8")
        cmd = ["codex", "exec", "--skip-git-repo-check", "-o", tmp.name] + (["-m", model] if model else []) + [prompt]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[:400])
        text = open(tmp.name, encoding="utf-8").read()
        os.unlink(tmp.name)
        return text
    raise ValueError(f"未知老师 {tool!r}")


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    starts = [i for i in (text.find("["), text.find("{")) if i >= 0]
    text = text[min(starts):] if starts else text
    end = max(text.rfind("]"), text.rfind("}"))
    return json.loads(text[: end + 1])


def call_json(prompt: str, tool: str = "claude", retries: int = 2, timeout: int = 900, model=None):
    last = None
    attempt = 0
    waited = 0.0
    while attempt <= retries:
        try:
            p = prompt if attempt == 0 else prompt + "\n\n上一次输出无法解析为 JSON，这次只输出 JSON，不要任何别的文字。"
            return _extract_json(_run(tool, p, timeout, model))
        except TeacherPaused as e:
            if waited >= WAIT_MAX:
                raise RuntimeError(f"等了 {waited / 3600:.1f} 小时用量仍未恢复：{e}")
            if waited == 0:
                sys.stderr.write(f"[teacher:{tool}] 用量受限，每 {WAIT_STEP // 60} 分钟重试一次，最多等 {WAIT_MAX / 3600:.0f} 小时：{str(e)[:120]}\n")
            time.sleep(WAIT_STEP)
            waited += WAIT_STEP
        except Exception as e:  # noqa: BLE001
            last = e
            attempt += 1
            sys.stderr.write(f"[teacher:{tool}] 第 {attempt} 次失败：{str(e)[:200]}\n")
            time.sleep(3 * attempt)
    raise RuntimeError(f"老师调用失败：{last}")


def run_batches(batches, prompts, handle, tool="claude", model=None, workers=2, out_path=None, **kw):
    """并行跑每一批；某批完成后立刻 handle(batch, result) -> rows，并追加写到 out_path。
    返回 (写入条数, 作废条数)。result 为 None 表示该批老师调用失败。"""
    written = bad = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_safe_call, p, tool, model, kw): i for i, p in enumerate(prompts)}
        for fut in as_completed(futs):
            i = futs[fut]
            rows, nbad = handle(batches[i], fut.result())
            bad += nbad
            if rows and out_path:
                append_jsonl(out_path, rows)
            written += len(rows)
            sys.stderr.write(f"[teacher:{tool}] 批 {i + 1}/{len(prompts)} 完成，累计写入 {written}，作废 {bad}\n")
    return written, bad


def _safe_call(prompt, tool, model, kw):
    try:
        return call_json(prompt, tool, model=model, **kw)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[teacher:{tool}] 放弃一批：{e}\n")
        return None


def append_jsonl(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def add_common_args(ap, per_call):
    ap.add_argument("--tool", default="claude", choices=["claude", "codex"])
    ap.add_argument("--model", default="sonnet", help="claude 的模型别名（sonnet/opus/haiku）；codex 传给 -m；填 none 用默认")
    ap.add_argument("--per-call", type=int, default=per_call)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--shard", default="0/1", help="i/n：只处理第 i 份，用于两个老师分担")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条待办（冒烟测试用）")


def apply_shard(items, shard, limit):
    i, n = (int(x) for x in shard.split("/"))
    items = items[i::n]
    return items[:limit] if limit else items


def model_arg(args):
    return None if args.model in ("none", "", None) else args.model
