"""手机微信的固定操作：读聊天列表预览、给某个聊天发一条消息。

全部靠控件元素表定位（按名字找，不看截图、不靠坐标）。需要在 phone.session() 里调用。
  读：聊天列表里每个聊天一行，预览已经带 [有人@我]、发送者和最新一条内容（长了会被「…」截断）。
  发：进聊天 → 点输入框 → 输入文字 → 回车（微信里回车就是发送）→ 回列表，用预览核对发出去了。
"""
import re
import time

import phone

MAX_TRIES = 4


def _rows(query):
    return phone.rows(phone.elements(query))


def _chat_cell(rows, chat):
    for r in rows:
        if r.get("kind") == "Cell" and (r.get("label") or "").startswith(chat + ","):
            return r
    return None


def go_chat_list(chat):
    """回到微信的聊天列表，并确认能看到目标聊天那一行；返回那一行。"""
    phone.act({"type": "launch_app", "bundle": phone.WECHAT})
    time.sleep(1.0)
    for _ in range(MAX_TRIES):
        res = phone.elements(chat)
        cell = _chat_cell(phone.rows(res), chat)
        if cell:
            return res["snapshot"], cell
        back = [r for r in _rows("返回") if r.get("kind") == "Button" and (r.get("label") or "").startswith("返回")]
        if not back:  # 页面可能还没稳定，等一下再读
            time.sleep(1.0)
            continue
        phone.act({"type": "tap", "element": back[0]["index"], "snapshot": phone.elements("返回")["snapshot"]})
        time.sleep(0.5)
    raise RuntimeError(f"聊天列表里找不到「{chat}」")


def parse_preview(label):
    """「群名,6条未读,[有人@我] ,发送者: 内容,22:57」-> 字段。群聊内容前有「发送者: 」，单聊没有。"""
    parts = label.split(",")
    name, time_ = parts[0], parts[-1]
    middle = ",".join(parts[1:-1])
    at_me = "[有人@我]" in middle
    unread = 0
    m = re.search(r"(\d+)条未读", middle)
    if m:
        unread = int(m.group(1))
    last = re.sub(r"^(\d+条未读,)?(\[有人@我\]\s*,)?", "", middle).strip()
    sender, sep, text = last.partition(": ")
    if not sep:
        sender, text = "", last
    return {"chat": name, "unread": unread, "at_me": at_me, "sender": sender, "text": text,
            "truncated": last.endswith("…") or last.endswith("..."), "time": time_, "raw": label}


def read_preview(chat):
    _, cell = go_chat_list(chat)
    return parse_preview(cell["label"])


def _enter_chat(chat):
    snap, cell = go_chat_list(chat)
    phone.act({"type": "tap", "element": cell["index"], "snapshot": snap})
    time.sleep(0.8)


def _input_box():
    res = phone.elements(scope="app")
    for r in phone.rows(res):
        if r.get("kind") == "TextView" and "index" in r:
            return res["snapshot"], r
    raise RuntimeError("聊天页里找不到输入框")


def clear_input():
    """清空输入框。先直接写空值；不行就按删除键删到空（草稿留在输入框里会被下次误发）。"""
    for _ in range(2):
        snap, box = _input_box()
        if not box.get("value"):
            return
        try:
            phone.act({"type": "set_value", "element": box["index"], "snapshot": snap, "value": ""})
        except RuntimeError:
            pass
    for _ in range(6):
        snap, box = _input_box()
        n = len(box.get("value") or "")
        if not n:
            return
        phone.call("POST", "/agent/actions", {"steps": [{"action": {"type": "key", "name": "delete"}}] * min(n, 24)})
    raise RuntimeError("输入框没能清空")


def send(chat, text, dry_run=False):
    """给 chat 发一条消息。dry_run=True 只把字打进输入框再清掉，不按发送。"""
    text = " / ".join(line.strip() for line in text.splitlines() if line.strip())  # 回车就是发送，一律单行
    _enter_chat(chat)
    snap, box = _input_box()
    phone.act({"type": "tap", "element": box["index"], "snapshot": snap})
    phone.act({"type": "text", "text": text})
    snap, box = _input_box()
    if text[:10] not in (box.get("value") or ""):  # 读回输入框，没打进去就不发
        raise RuntimeError("输入框里没读到刚打的字，没有发送")
    if dry_run:
        clear_input()
        return {"sent": False, "dry_run": True, "typed": text}
    phone.act({"type": "key", "name": "return"})
    time.sleep(1.0)
    # 核对：回列表，预览里最新一条应当是刚发的内容
    preview = read_preview(chat)
    ok = text[:10] in preview["text"]
    return {"sent": ok, "typed": text, "preview": preview["raw"]}


# ---------- 读聊天里的新回复（含语音转文字） ----------

SCREEN_W, SCREEN_H = 402.0, 874.0
SKIP_LABELS = ("垂直滚动条", "水平滚动条")


def chat_bubbles(rows):
    """聊天页里的气泡行：整屏读取里是 kind=Other、label=「发送者,内容」、前一行是空 label 的 Cell。
    语音气泡的内容是「语音,2'',转出来的文字」，没转过的就只有「语音,2''」。"""
    out = []
    for i, r in enumerate(rows):
        label = r.get("label") or ""
        if r.get("kind") != "Other" or "," not in label or label.startswith(SKIP_LABELS):
            continue
        prev = rows[i - 1] if i else {}
        if prev.get("kind") != "Cell" or (prev.get("label") or ""):
            continue
        sender, rest = label.split(",", 1)
        b = {"sender": sender, "index": r.get("index"), "rect": r.get("rect"), "kind": "text", "text": rest}
        if rest.startswith("语音,"):
            parts = rest.split(",", 2)
            b.update(kind="voice", dur=parts[1], text=parts[2].strip() if len(parts) > 2 else "")
        out.append(b)
    return out


def _transcribe(bubble):
    """长按语音气泡 → 点「转文字」。成功返回 True。菜单里没有「转文字」就把菜单关掉。"""
    x0, y0, w, h = bubble["rect"]
    phone.act({"type": "longpress", "x": 100 / SCREEN_W, "y": (y0 + 22) / SCREEN_H, "duration_ms": 900})
    time.sleep(0.5)
    res = phone.elements("转文字")
    btn = [r for r in phone.rows(res) if r.get("kind") == "Button" and r.get("label") == "转文字"]
    if not btn:
        phone.act({"type": "tap", "x": 0.5, "y": 0.02})  # 关菜单（已经转过时菜单里是「取消转文字」）
        return False
    phone.act({"type": "tap", "element": btn[0]["index"], "snapshot": res["snapshot"]})
    time.sleep(2.5)  # 转写要等一下
    return True


def read_replies(chat):
    """进聊天，返回「我最后一条消息」之后别人发来的所有消息；语音自动转成文字。
    每条 {sender, kind, text}；转不出来的语音 text 为空。"""
    _enter_chat(chat)
    for _ in range(3):
        rows = phone.rows(phone.elements(scope="app"))
        bubbles = chat_bubbles(rows)
        last_mine = max((i for i, b in enumerate(bubbles) if b["sender"] == "我"), default=-1)
        replies = bubbles[last_mine + 1:]
        todo = [b for b in replies if b["kind"] == "voice" and not b["text"] and b["rect"] and 0 <= b["rect"][1] < SCREEN_H - 120]
        if not todo:
            break
        if not _transcribe(todo[0]):  # 一次转一条，转完重新读
            break
    return [{"sender": b["sender"], "kind": b["kind"], "text": b["text"]} for b in replies]
