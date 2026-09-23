---
name: laya-chat
description: Laya Chat 的安装步骤，给 AI 助手执行。带用户在 macOS 上装好这个悬浮窗程序：建环境、开权限、选求助工具、下权重、自检、设开机启动。装好之后程序独立运行，不再需要 AI 助手。
---

# laya-chat 安装向导

装完之后的程序长这样：一个常驻的小程序，读微信窗口里的聊天和你正在打的草稿，用本地 Laya 模型判断当前好感度和"这条发出去会怎样"，显示在微信旁边的悬浮窗里。它自己不调用任何大模型，只有用户点"求助 Claude/Codex"按钮时才调本机的命令行助手。你（助手）只负责把它装好，装好就退出。

仓库所在目录记为 `$R`（SKILL.md 所在目录，通常是 `~/laya-chat`）。程序就装在这个目录里运行，不要挪进任何 skills 目录。

## 步骤

1. **检查环境。** macOS 13 以上，有 `uv`（没有就 `brew install uv`），微信 mac 版 4.x 已安装。
2. **建虚拟环境。**
   ```bash
   cd $R && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
   ```
3. **求助工具。** 默认自动：本机装了 claude 就用 claude，否则用 codex，都没有就把按钮置灰。用 `which claude codex` 看装了哪个，告诉用户按钮上会显示哪个。用户想强制指定，把 `~/.laya-chat/config.json` 的 `ai_tool` 写成 `claude`、`codex` 或 `none`。
4. **关系设定。** 告诉用户默认把所有人当"朋友"，想给某个会话单独设定，在 config.json 的 `relationships` 里写 `{"会话名": "对方是我的伴侣"}`。不用现在填。
5. **下载权重并自检。** 运行
   ```bash
   cd $R && .venv/bin/python -c "from laya_chat import config; from laya_chat.engine import Engine; e=Engine(config.load()); e.load(); print('error:', e.error)"
   ```
   首次会下载约 850 MB，等它打印 `error: None`。
6. **读取自检。** 让用户打开微信并点开任意一个会话，然后运行 `cd $R && .venv/bin/python -m laya_chat --dump`。应该打印出会话名和几条消息。如果打印 `no window`，微信没开或被最小化；如果消息为空，让用户滚动一下聊天区再试。
7. **装成 .app 并设开机启动。** 运行 `$R/installer/make_app.sh`，然后 `open "$HOME/Applications/Laya Chat.app"`。
8. **权限。** 第一次启动时系统会弹两次权限请求（屏幕录制、辅助功能），让用户都允许。没弹的话，让用户到 系统设置 > 隐私与安全性 > 屏幕录制 和 辅助功能 里手动加上「Laya Chat」，然后 `pkill -f laya_chat; open "$HOME/Applications/Laya Chat.app"` 重启。
9. **验收。** 让用户在微信输入框随便打一句话，停一秒，悬浮窗应显示"发出去后…"那一段。点"求助 Claude/Codex"应在半分钟内出现三条候选和"填入"按钮。

## 出问题时

- 悬浮窗不出现：看 `~/.laya-chat/` 下有没有日志；用 `cd $R && .venv/bin/python -m laya_chat` 前台运行看报错。
- 我方/对方分反了：微信主题不是默认配色时绿色检测会失效，暂时只支持默认配色。
- 想清空本机记录的聊天历史：`cd $R && .venv/bin/python -m laya_chat --clear`。
- 卸载：`$R/installer/make_app.sh --remove`。

## 不要做的事

- 不要替用户发送任何消息，不要在验收时自己往输入框里填字，让用户自己打。
- 不要把用户的聊天内容写进任何文件或贴到对话里。
