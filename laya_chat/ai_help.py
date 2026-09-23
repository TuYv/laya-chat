"""「求助 Claude/Codex」按钮：只有用户点了才运行。把对话、好感度、草稿和 Laya 的判断交给
本机已装的命令行助手，要它给一句评价和三条改写。其余时候程序不碰任何大模型。"""
import os
import shutil
import subprocess
import tempfile
from typing import List, Tuple

PROMPT = """你是我的聊天回复参谋。下面是我和「{chat}」的最近对话（{relationship}），我正准备发出一条草稿。
一个本地小模型对「当前好感度」和「这条草稿发出去的后果」给了概率判断，仅供参考，它经常不准。
请你自己判断，然后严格按下面的格式回答，不要多说：

评价：<一句话说这条草稿发出去会怎样、问题在哪>
候选1：<改写后的回复，口语化，像我本人打字>
候选2：<另一种写法，更短>
候选3：<换一个角度>

## 对话（最近在前面的是更早的）
{messages}

## 当前好感度（本地模型判断）
{affinity}

## 我的草稿
{draft}

## 本地模型对草稿的判断
{judgment}
"""


DISPLAY = {"claude": "Claude", "codex": "Codex"}


def available(tool: str) -> bool:
    return tool in ("claude", "codex") and shutil.which(tool) is not None


def resolve(setting: str):
    """按配置决定用哪个工具。auto：本机装了哪个用哪个，优先 claude；都没有返回 None。"""
    if setting in ("claude", "codex"):
        return setting if available(setting) else None
    if setting == "auto":
        for t in ("claude", "codex"):
            if available(t):
                return t
    return None


def _run(tool: str, prompt: str, timeout: int = 120) -> str:
    if tool == "claude":
        cmd = ["claude", "-p", prompt, "--output-format", "text"]
    elif tool == "codex":
        # codex exec 的标准输出夹着日志，用 -o 把最后一条回复单独写到文件
        out = tempfile.NamedTemporaryFile("r", suffix=".txt", delete=False, encoding="utf-8")
        cmd = ["codex", "exec", "--skip-git-repo-check", "-o", out.name, prompt]
    else:
        raise ValueError(f"未知工具 {tool!r}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300] or f"{tool} 退出码 {r.returncode}")
    if tool == "codex":
        text = open(out.name, encoding="utf-8").read()
        os.unlink(out.name)
        return text
    return r.stdout


def parse(text: str) -> Tuple[str, List[str]]:
    verdict, cands = "", []
    for line in text.splitlines():
        s = line.strip().lstrip("*-# ").strip()
        if s.startswith("评价"):
            verdict = s.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif s.startswith("候选"):
            body = s.split("：", 1)[-1].split(":", 1)[-1].strip()
            if body:
                cands.append(body)
    return verdict, cands[:3]


def ask(tool: str, chat: str, relationship: str, messages, affinity, draft: str, judgment) -> dict:
    msg_lines = "\n".join(f"{'我' if m.get('from', m.get('side')) == 'me' else '对方'}：{m['text']}"
                          for m in messages[-10:])
    aff = "（还没算出来）"
    if affinity:
        aff = f"{affinity.get('score100', round(affinity['score'] / 9 * 100))}/100 {affinity['label']}，走势{affinity['trend_zh']}，{affinity['open_issue_zh']}"
    jd = "（还没算出来）"
    if judgment:
        jd = "；".join(f"{k}: {v['zh']}" for k, v in judgment["items"].items())
    prompt = PROMPT.format(chat=chat, relationship=relationship, messages=msg_lines,
                           affinity=aff, draft=draft or "（空）", judgment=jd)
    raw = _run(tool, prompt)
    verdict, cands = parse(raw)
    return {"verdict": verdict, "candidates": cands, "raw": raw}
