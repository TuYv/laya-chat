"""python -m laya_chat            启动悬浮窗程序
python -m laya_chat --dump     打印一次读取到的聊天（调试）
python -m laya_chat --clear    清空本机聊天历史
"""
import sys


def main():
    args = sys.argv[1:]
    if "--dump" in args:
        from .ax_reader import dump
        from . import config
        dump(config.load()["app_name"])
    elif "--clear" in args:
        from . import config
        from .history import HistoryStore
        n = HistoryStore(config.HOME / "history").clear_all()
        print(f"已删除 {n} 个会话的历史")
    else:
        from .app import main as run
        run()


if __name__ == "__main__":
    main()
