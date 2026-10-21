#!/usr/bin/env python3
"""把一条新任务交给 iphone-agent-kit 的桥接（本机 POST /task），让助手接着去办事。

给等待器的 --then 用：对方回复满足条件后，自动叫助手继续做下一步（比如去下单）。
文字里可以用环境变量占位：$NW_RESULT（汇报）、$NW_RECEIVED（收到的消息 JSON）、$NW_CHAT（聊天名）。

用法：
  python3 submit_task.py "对方回复了：$NW_RESULT。接着去美团订早餐，订不了就告诉我"
"""
import json
import os
import sys
import urllib.request

CONFIG = os.path.expanduser("~/.config/iphone-agent-kit/config.json")


def main():
    if len(sys.argv) < 2:
        sys.exit("用法: submit_task.py \"任务文字\"")
    text = os.path.expandvars(sys.argv[1])
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    req = urllib.request.Request(
        "http://127.0.0.1:%s/task" % cfg.get("port", 18800),
        data=json.dumps({"text": text}, ensure_ascii=False).encode(),
        headers={"Authorization": "Bearer " + cfg["token"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(r.read().decode())


if __name__ == "__main__":
    main()
