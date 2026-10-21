#!/bin/sh
# 编译并安装 NotifWatch.app（读 Mac 上微信通知横幅的小程序）到 ~/Applications。
# 用法：sh build-notifwatch.sh
# 注意：app 是临时签名（ad-hoc），每次重新编译签名都会变，macOS 里「辅助功能」的授权会对不上。
#       所以只编译一次；重新编译后要在 系统设置 → 隐私与安全性 → 辅助功能 里删掉 NotifWatch 再重新添加，
#       或运行 tccutil reset Accessibility com.iphone-agent-kit.notifwatch 后重新授权。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Applications/NotifWatch.app"
mkdir -p "$APP/Contents/MacOS"
swiftc -O "$HERE/notif-watch.swift" -o "$APP/Contents/MacOS/notif-watch"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>com.iphone-agent-kit.notifwatch</string>
<key>CFBundleName</key><string>NotifWatch</string>
<key>CFBundleExecutable</key><string>notif-watch</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>0.1</string>
<key>LSUIElement</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$APP"
echo "已安装 $APP"
echo "下一步：用 open -n \"$APP\" --args --check --prompt --log /tmp/nw-check.log 触发辅助功能授权请求，"
echo "然后在 系统设置 → 隐私与安全性 → 辅助功能 里打开 NotifWatch。"
