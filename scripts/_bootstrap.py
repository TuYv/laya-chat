"""脚本共用的小工具：项目根目录、虚拟环境里的 python、需要时用它重新执行自己。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
STATE_DIR = Path(os.environ.get("LAYA_CHAT_HOME", Path.home() / ".laya-chat"))
SHOT_DIR = Path(os.environ.get("LAYA_CHAT_SHOTS", "/tmp/laya-chat"))


def venv_python() -> str:
    cand = ROOT / ".venv" / "bin" / "python"
    return str(cand) if cand.exists() else sys.executable


def reexec_in_venv_if_missing(module: str) -> None:
    """当前解释器缺某个包、而项目的 .venv 里有时，用 .venv 的 python 重新跑一遍自己。"""
    try:
        __import__(module)
        return
    except ImportError:
        pass
    vp = venv_python()
    if os.path.realpath(vp) != os.path.realpath(sys.executable):
        os.execv(vp, [vp] + sys.argv)
    sys.stderr.write(
        f"[laya-chat] 缺少 python 包 {module}，请先在项目根目录执行：\n"
        f"  uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt\n"
    )
    sys.exit(2)


def read_json_input(args_file):
    """从 --file 或标准输入读一段 JSON。"""
    import json
    if args_file:
        with open(args_file, encoding="utf-8") as f:
            return json.load(f)
    raw = sys.stdin.read()
    if not raw.strip():
        sys.stderr.write("[laya-chat] 标准输入为空，需要一段 JSON\n")
        sys.exit(2)
    return json.loads(raw)


def print_json(obj) -> None:
    import json
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
