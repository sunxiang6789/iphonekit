#!/usr/bin/env python3
"""微信「发出去 → 等回复 → 汇报」长任务。

流程：
  ask   发一条带 AI 标识的消息（手机，固定流程，不看截图）并登记等待任务
  run   后台常驻：盯 Mac 的微信横幅（NotifWatch 写的 watch.log），有人回了才调一次小模型判断
        完成条件满足 → 推送结果；没满足 → 继续等；到点 → 推送汇报
等待期间不调用模型、不碰手机。只有这几种情况才接管手机读聊天列表预览：
  群里有人 @ 我（横幅只有「某某@了你」，没有内容）、横幅内容被「…」截断、到点兜底检查一次。

数据文件（都在本目录）：tasks.json 等待任务；config.json {me_names, ai_prefix}；state.json 读到 watch.log 的位置。

用法：
  python3 waiter.py run
  python3 waiter.py ask --chat 周末出游群 --type group --text "周六几点出发？" \\
       --done "有人给出了具体出发时间" --deadline "2026-10-21 22:00" [--id t1] [--dry-run]
  python3 waiter.py list | rm <id>
  python3 waiter.py add ...      只登记任务、不发消息（消息已经自己发过时用）
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.environ.get("NW_DIR") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
WATCH_LOG = os.path.join(HERE, "watch.log")
TASKS = os.path.join(HERE, "tasks.json")
CONFIG = os.path.join(HERE, "config.json")
STATE = os.path.join(HERE, "state.json")
KIT_HOME = os.environ.get("IPHONE_AGENT_KIT_HOME", os.path.expanduser("~/.config/iphone-agent-kit"))
PUSH = os.path.join(KIT_HOME, "bark_push.py")  # iphone-agent-kit 自带的 Bark 推送
DEDUPE_SECS = 3
DEFAULT_PREFIX = "【AI助手】"
# 读不了内容的消息：语音、图片等只显示占位文字。不拿它去判断，直接推送让人自己看。
PLACEHOLDERS = ("[语音]", "[图片]", "[视频]", "[文件]", "[动画表情]", "[表情]", "[位置]", "[链接]")
AT_MARKERS = ["[有人@我]", "[@所有人]", "@所有人"]


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def push(text):
    print("PUSH:", text, flush=True)
    if os.environ.get("NW_NO_PUSH"):
        return
    subprocess.run(["python3", PUSH, text], check=False, capture_output=True)


def parse(entry):
    """横幅 -> {chat, sender, text, group}。群聊正文是「发送者: 内容」，单聊没有。"""
    texts = entry.get("texts") or []
    if len(texts) < 3 or not texts[0].startswith("微信"):
        return None
    chat, body = texts[1], texts[2]
    # 实测：被 @ 时横幅只有「某某在群聊中@了你」，不带消息内容
    if body.endswith("在群聊中@了你"):
        return {"chat": chat, "sender": body[: -len("在群聊中@了你")], "text": "", "group": True,
                "at_me": True, "ts": entry.get("ts", 0)}
    sender, sep, content = body.partition(": ")
    if not sep:
        sender, sep, content = body.partition("：")
    if sep:
        return {"chat": chat, "sender": sender.strip(), "text": content.strip(), "group": True, "ts": entry.get("ts", 0)}
    return {"chat": chat, "sender": chat, "text": body.strip(), "group": False, "ts": entry.get("ts", 0)}


def is_at_me(msg, cfg):
    if not msg["group"]:
        return False
    if msg.get("at_me"):
        return True
    names = ["@" + n for n in cfg.get("me_names", [])]
    return any(m in msg["text"] for m in AT_MARKERS + names)


def judge_settings():
    """判断用的小模型，OpenAI 兼容接口。config.json 的 judge 段：
    {"base_url": "https://api.deepseek.com", "model": "deepseek-chat",
     "key_env": "DEEPSEEK_API_KEY", "key_file": "~/some/file.env", "push_style": "口语化的一句话"}
    key 取自环境变量 key_env，其次 key_file（文件里 NAME=value 或整个文件就是 key）。key 永远不写进本目录。"""
    j = load(CONFIG, {}).get("judge") or {}
    env_name = j.get("key_env", "DEEPSEEK_API_KEY")
    key = os.environ.get(env_name, "")
    if not key and j.get("key_file"):
        raw = open(os.path.expanduser(j["key_file"]), encoding="utf-8").read().strip()
        key = raw.split("=", 1)[1].strip() if raw.startswith(env_name + "=") else raw
    if not key:
        raise RuntimeError("没有判断模型的 key：设环境变量 %s，或在 config.json 的 judge.key_file 指向存 key 的文件" % env_name)
    return {"base_url": j.get("base_url", "https://api.deepseek.com").rstrip("/"), "model": j.get("model", "deepseek-chat"),
            "key": key, "push_style": j.get("push_style", "口语化的一句话")}


def judge(task):
    """一次小模型调用：已收到的消息是否满足完成条件。返回 {status, push}。"""
    cfg = judge_settings()
    lines = "\n".join(f"- {m['sender']}: {m['text']}" for m in task["received"])
    prompt = (
        f"我在微信里问了：「{task['ask']}」\n完成条件：{task['done']}\n已收到的消息（按时间）：\n{lines}\n\n"
        "判断 status：done=已满足完成条件；not_done=没满足（无关或没答到点上）；"
        "truncated=消息以「…」结尾或明显被截断，无法判断。\n"
        f"push：status=done 时写一句汇报，≤30字，只写结论（如谁说了什么时间），风格：{cfg['push_style']}，简体字；其他情况留空。\n"
        '只输出 JSON：{"status":"...","push":"..."}'
    )
    body = json.dumps({
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        cfg["base_url"] + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["key"]})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.load(r)
    return json.loads(out["choices"][0]["message"]["content"])


# ---------- 手机 ----------

def phone_replies(chat):
    """接管手机进聊天，读「我最后一条消息」之后别人的所有回复，语音转成文字。失败返回 None 并推送。"""
    import phone
    import wx
    try:
        with phone.session():
            return wx.read_replies(chat)
    except phone.NeedsHuman as e:
        push(f"手机要你来一下喔（{e}），{chat}的消息我还没读到")
    except Exception as e:
        print("phone_replies failed:", e, flush=True)
    return None


def absorb_replies(t, replies):
    """把读到的回复并进任务的已收消息（按发送者+内容去重）。返回是否有新增。"""
    added = False
    for m in replies or []:
        sender, text = m["sender"] or t["chat"], m["text"]
        if m["kind"] == "voice" and not text:  # 转文字没成功
            push(f"{sender}在{t['chat']}回了语音，我转不出文字，你自己听一下喔")
            continue
        if text.startswith(PLACEHOLDERS) or not text:
            continue
        if any(x["sender"] == sender and x["text"] == text for x in t["received"]):
            continue
        t["received"].append({"sender": sender, "text": text, "ts": int(time.time()), "voice": m["kind"] == "voice"})
        added = True
    return added


def run_then(t, result):
    """任务完成后接着执行登记时给的命令（比如叫另一个 agent 去下单）。结果通过环境变量传进去。"""
    cmd = t.get("then")
    if not cmd:
        return
    env = dict(os.environ, NW_TASK_ID=t["id"], NW_CHAT=t["chat"], NW_RESULT=result,
               NW_RECEIVED=json.dumps(t["received"], ensure_ascii=False))
    log = open(os.path.expanduser("~/Library/Logs/waiter-then.log"), "a")
    print("THEN:", cmd, flush=True)
    subprocess.Popen(["sh", "-c", cmd], env=env, stdout=log, stderr=log, start_new_session=True)


def evaluate(t):
    """判断一次；done 就汇报并结束任务。返回是否已结束。"""
    try:
        r = judge(t)
    except Exception as e:  # 判断失败也别漏：任务继续等，推送让你看一眼
        print("judge failed:", e, flush=True)
        push(f"{t['chat']}有新回复，我没判断出来，你看一眼喔")
        return False
    if r.get("status") == "done":
        push(r.get("push") or f"{t['chat']}有结果了喔")
        t["status"] = "done"
        run_then(t, r.get("push") or "")
        return True
    if r.get("status") == "truncated" and not t.get("truncated_pushed"):
        last = t["received"][-1]["text"][:30] if t["received"] else ""
        push(f"{t['chat']}回的太长被截断了，开头是「{last}」，你自己看一眼喔")
        t["truncated_pushed"] = True
    return False


# ---------- 主循环 ----------

def run():
    pos = load(STATE, {}).get("pos")
    if pos is None:  # 首次启动：从日志末尾开始，不处理历史
        pos = os.path.getsize(WATCH_LOG) if os.path.exists(WATCH_LOG) else 0
    last = {}
    print("waiter running, pos =", pos, flush=True)
    while True:
        tasks = load(TASKS, [])
        cfg = load(CONFIG, {})
        now = time.time()
        new = []
        if os.path.exists(WATCH_LOG):
            with open(WATCH_LOG, encoding="utf-8") as f:
                f.seek(pos)
                for line in f.readlines():
                    try:
                        m = parse(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if m:
                        new.append(m)
                pos = f.tell()
            save(STATE, {"pos": pos})

        touched, need_read = {}, {}
        for m in new:
            key = (m["chat"], m["sender"], m["text"])
            if m["ts"] - last.get(key, -999) < DEDUPE_SECS:
                continue
            last[key] = m["ts"]
            for t in tasks:
                if t["status"] != "waiting" or m["chat"] != t["chat"] or m["ts"] < t["created"]:
                    continue
                if (t["type"] == "group") != m["group"]:
                    continue
                if m.get("at_me"):  # @我优先：立刻推送；横幅没有内容，要接管手机读
                    push(f"{m['sender']}在{m['chat']}里@你啦，快去看喔")
                    need_read[t["id"]] = t
                    continue
                if m["text"].startswith("[语音]"):  # 语音：进聊天长按转文字
                    need_read[t["id"]] = t
                    continue
                if m["text"].startswith(PLACEHOLDERS):
                    push(f"{m['sender']}在{m['chat']}回了{m['text'].split()[0]}，我读不了内容，你自己看一下喔")
                    continue
                t["received"].append({"sender": m["sender"], "text": m["text"], "ts": m["ts"]})
                touched[t["id"]] = t
                if is_at_me(m, cfg):
                    push(f"{m['chat']}里 {m['sender']} @你：{m['text'][:40]}")
                if m["text"].endswith(("…", "...")):  # 横幅被截断：读列表预览补全
                    need_read[t["id"]] = t

        # 需要读预览的（@ 或被截断）：接管手机读一次，并进已收消息
        for t in need_read.values():
            if absorb_replies(t, phone_replies(t["chat"])):
                touched[t["id"]] = t

        # 每个任务一次判断（判断期间来的消息自然合并到下一轮）
        for t in touched.values():
            evaluate(t)

        # 到点：先接管手机兜底查一次（防漏横幅），还没满足才汇报超时
        for t in tasks:
            if t["status"] == "waiting" and now >= t["deadline_ts"]:
                if absorb_replies(t, phone_replies(t["chat"])) and evaluate(t):
                    continue
                n = len(t["received"])
                push(f"{t['chat']}到点了还没问到结果" + (f"（回了{n}条但没答到点上）" if n else "，对方还没回"))
                t["status"] = "timeout"
                touched[t["id"]] = t

        if touched or need_read:
            save(TASKS, tasks)
        time.sleep(0.5)


# ---------- 命令行 ----------

def verify_sent(a):
    """登记前核对：此刻手机屏幕上的聊天页里，我最后一条消息就是刚问的这句。
    防止助手没真的发送（比如以为上一轮已经问过）就直接登记监测。读不了屏幕时只警告，不拦。"""
    import phone
    import wx
    try:
        rows = phone.rows(phone.elements(scope="app"))
    except Exception as e:
        print("verify skipped (屏幕读不了):", e, flush=True)
        return
    mine = [b for b in wx.chat_bubbles(rows) if b["sender"] == "我"]
    key = a.text.replace(load(CONFIG, {}).get("ai_prefix", DEFAULT_PREFIX), "").strip()[:8]
    if not mine or key not in mine[-1]["text"]:
        sys.exit("没在当前聊天页看到刚发出的这条消息（「%s…」），可能还没发送。请先在「%s」里真的发出去，再登记等待。" % (key, a.chat))


def new_task(a):
    if getattr(a, "verify_sent", False) and not os.environ.get("NW_NO_VERIFY"):
        verify_sent(a)
    tasks = load(TASKS, [])
    if any(t["status"] == "waiting" and t["chat"] == a.chat for t in tasks):
        sys.exit(f"{a.chat} 已有等待中的任务，同一对象同时只允许一个")
    # 截止时间按 config.json 的 timezone 理解（默认北京时间），不依赖 shell 的 TZ
    dl = datetime.strptime(a.deadline, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(load(CONFIG, {}).get("timezone", "Asia/Shanghai")))
    tid = a.id or "t" + str(int(time.time()))
    tasks = [t for t in tasks if t["id"] != tid]
    tasks.append({"id": tid, "chat": a.chat, "type": a.type, "ask": a.text, "done": a.done,
                  "deadline": a.deadline, "deadline_ts": dl.timestamp(), "created": int(time.time()) - (a.backdate or 0),
                  "status": "waiting", "received": [], "then": a.then})
    save(TASKS, tasks)
    return tid


def ask(a):
    a.backdate = 0
    """发消息（带 AI 标识）→ 核对发出去了 → 登记等待任务。"""
    import phone
    import wx
    prefix = load(CONFIG, {}).get("ai_prefix", DEFAULT_PREFIX)
    if any(t["status"] == "waiting" and t["chat"] == a.chat for t in load(TASKS, [])):
        sys.exit(f"{a.chat} 已有等待中的任务，同一对象同时只允许一个")
    with phone.session():
        res = wx.send(a.chat, prefix + a.text, dry_run=a.dry_run)
    print(json.dumps(res, ensure_ascii=False))
    if a.dry_run:
        return
    if not res.get("sent"):
        sys.exit("没能确认消息已发出，任务没有登记，请手动看一下手机")
    print("added", new_task(a))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("list")
    rm = sub.add_parser("rm")
    rm.add_argument("id")
    for name in ("add", "ask"):
        p = sub.add_parser(name)
        p.add_argument("--id")
        p.add_argument("--chat", required=True, help="微信里显示的名字（备注名/群名）")
        p.add_argument("--type", choices=["group", "person"], required=True)
        p.add_argument("--text", "--ask", dest="text", required=True, help="要问的话（ask 会自动加 AI 标识）")
        p.add_argument("--done", required=True, help="一句话写完成条件")
        p.add_argument("--deadline", required=True, help="YYYY-MM-DD HH:MM，北京时间")
        p.add_argument("--then", help="对方回复满足条件后要执行的 shell 命令；环境变量 NW_RESULT=汇报、NW_RECEIVED=收到的消息(JSON)")
        if name == "add":
            p.add_argument("--verify-sent", action="store_true", help="登记前核对屏幕上聊天页里我最后一条消息就是 --text（防止没发就登记）")
            p.add_argument("--backdate", type=int, default=0, help="把任务创建时间往前推几秒（消息先发出去、后登记时，防止漏掉很快的回复）")
        if name == "ask":
            p.add_argument("--dry-run", action="store_true", help="只把字打进输入框再清掉，不发送、不登记")
    a = ap.parse_args()

    if a.cmd == "run":
        run()
    elif a.cmd == "list":
        for t in load(TASKS, []):
            print(t["id"], t["status"], t["type"], t["chat"], t["deadline"], f"收到{len(t['received'])}条")
    elif a.cmd == "rm":
        save(TASKS, [t for t in load(TASKS, []) if t["id"] != a.id])
    elif a.cmd == "add":
        print("added", new_task(a))
    elif a.cmd == "ask":
        ask(a)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
