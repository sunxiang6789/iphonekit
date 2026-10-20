#!/bin/sh
# 关掉 iphone-use 的 runner（交给人用）：向 Mac 上的 iphone-use 守护进程发 mode=human。
# 地址是 Mac 上的 127.0.0.1:44321（不是 8787，那是手机上的服务），密码从 iphone-use 的 LaunchAgent 配置里读。
# 用法：先调用 phone_release_owner 交还占用，再运行  sh ~/.config/iphone-agent-kit/stop_runner.sh
# 可用环境变量覆盖：IPHONE_USE_PLIST（LaunchAgent 文件）、IPHONE_USE_DAEMON_URL（守护进程地址）。
PLIST="${IPHONE_USE_PLIST:-$HOME/Library/LaunchAgents/com.leeguoo.iphone-use.plist}"
URL="${IPHONE_USE_DAEMON_URL:-http://127.0.0.1:44321}"
PW=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:IPHONE_USE_PASSWORD" "$PLIST") || {
  echo "读不到 iphone-use 密码（$PLIST），请先运行 iphone-use setup"; exit 1; }
curl -s -m 60 \
  -H "Authorization: Bearer $PW" \
  -H "X-Phone-Control: 1" \
  -H "Content-Type: application/json" \
  -X POST "$URL/agent/mode" -d '{"mode":"human"}'
echo
