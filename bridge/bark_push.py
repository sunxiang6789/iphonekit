#!/usr/bin/env python3
"""用 Bark 把一句话推送到手机。给 Claude Code / Codex 在直接对话里任务结束时调用。

用法：python3 bark_push.py "推送内容" [标题]
配置：~/.config/iphone-agent-kit/config.json 里的 bark 段（server、group、device_keys），
      和桥接服务共用同一份。没配 key 时只提示，不报错退出。
"""
import json
import os
import sys
import urllib.request

HOME = os.environ.get("IPHONE_AGENT_KIT_HOME", os.path.expanduser("~/.config/iphone-agent-kit"))
CONFIG = os.path.join(HOME, "config.json")


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit('用法：bark_push.py "推送内容" [标题]')
    body = sys.argv[1].strip()
    try:
        with open(CONFIG, encoding="utf-8") as f:
            bark = json.load(f).get("bark") or {}
    except (OSError, ValueError) as e:
        sys.exit("读不到配置 %s：%s" % (CONFIG, e))
    keys = [k for k in (bark.get("device_keys") or [bark.get("device_key")]) if k]
    if not keys:
        print("还没配置 Bark key（%s 里的 bark.device_keys），跳过推送" % CONFIG)
        return
    title = sys.argv[2] if len(sys.argv) > 2 else "iPhone 助手"
    failed = 0
    for key in keys:
        data = json.dumps({"device_key": key, "title": title, "body": body,
                           "group": bark.get("group", "iPhone助手")}).encode("utf-8")
        req = urllib.request.Request(bark.get("server", "https://api.day.app").rstrip("/") + "/push", data=data,
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                r.read()
        except Exception as e:
            failed += 1
            print("推送失败（%s…）：%s" % (key[:4], e), file=sys.stderr)
    if failed:
        sys.exit(1)
    print("已推送")


if __name__ == "__main__":
    main()
