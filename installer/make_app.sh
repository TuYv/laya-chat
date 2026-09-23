#!/bin/zsh
# 把程序包成一个 .app 壳，这样「屏幕录制」「辅助功能」两项权限归属于「Laya Chat」，
# 而不是某个 python 二进制；再加为登录启动项。
#   installer/make_app.sh            安装
#   installer/make_app.sh --remove   卸载（删 .app 和登录项，不删代码和权重）
#   installer/make_app.sh --no-login-item   只打包，不加登录项
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Applications/Laya Chat.app"

if [[ "$1" == "--remove" ]]; then
  osascript -e 'tell application "System Events" to delete (every login item whose name is "Laya Chat")' >/dev/null 2>&1 || true
  pkill -f "laya_chat" 2>/dev/null || true
  rm -rf "$APP"
  echo "已删除 $APP 和登录项"
  exit 0
fi

[[ -x "$ROOT/.venv/bin/python" ]] || { echo "先建虚拟环境：uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt"; exit 1; }

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>com.laya-chat.app</string>
  <key>CFBundleName</key><string>Laya Chat</string>
  <key>CFBundleDisplayName</key><string>Laya Chat</string>
  <key>CFBundleExecutable</key><string>laya-chat</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>0.2.0</string>
  <key>CFBundleShortVersionString</key><string>0.2.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
cat > "$APP/Contents/MacOS/laya-chat" <<LAUNCH
#!/bin/zsh
cd "$ROOT"
exec "$ROOT/.venv/bin/python" -m laya_chat "\$@"
LAUNCH
chmod +x "$APP/Contents/MacOS/laya-chat"

if [[ "$1" == "--no-login-item" ]]; then
  echo "已打包 $APP（未加登录项）。"
else
  osascript -e 'tell application "System Events" to delete (every login item whose name is "Laya Chat")' >/dev/null 2>&1 || true
  osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$APP\", hidden:true}" >/dev/null
  echo "已安装 $APP 并加入登录启动项。"
fi
echo "首次运行会弹出权限请求；也可以手动到 系统设置 > 隐私与安全性 里给「Laya Chat」打开「屏幕录制」和「辅助功能」。"
echo "现在启动：open \"$APP\""
