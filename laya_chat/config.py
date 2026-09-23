"""配置文件 ~/.laya-chat/config.json。缺的键用默认值补。"""
import json
import os
from pathlib import Path

HOME = Path(os.environ.get("LAYA_CHAT_HOME", Path.home() / ".laya-chat"))
CONFIG_PATH = HOME / "config.json"

DEFAULTS = {
    "app_name": "WeChat",                 # 盯哪个聊天软件（进程名，中英文都认）
    "ai_tool": "auto",                    # 求助按钮用什么：auto（本机装了哪个用哪个，优先 claude）| claude | codex | none
    "keep_history": True,                 # 按联系人在本机记录聊天历史，供好感度判断
    "poll_interval": 1.0,                 # 多久读一次屏幕（秒）
    "draft_debounce": 1.2,                # 草稿停止变化多久后判断（秒）
    "model": "ricky136/laya-chat",        # 微调后的权重（Hugging Face），test 集 0.615；出厂权重约 0.32
    "subfolder": "",                      # 想用出厂权重：model 改 convaiinnovations/laya，subfolder 填 typed-decisions
    "head_max_len": 512,
    "max_len": 1024,
    "relationship_default": "对方是我的朋友",
    "memory_messages": 30,                # 好感度判断用最近多少条消息（含本机记录的历史）
    "memory_chars": 700,                  # 上限字数：模型一次读不了太多，超过就从最早的开始丢，最新的永远保留
    "context_messages": 10,               # 草稿判断带最近多少条消息
    "history_max": 500,                   # 每个会话在本机最多记多少条
    "relationships": {},                  # 会话名 -> 一句话关系，例如 {"张经理": "对方是我的同事"}
    "overlay_width": 320,
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def save(cfg: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def relationship_for(cfg: dict, chat: str) -> str:
    return cfg.get("relationships", {}).get(chat) or cfg["relationship_default"]
