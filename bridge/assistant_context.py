"""所有助手共用的本机经验与偏好；纯标准库，不启动手机或模型。"""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import re
import tempfile
import sys
import threading
import time

PUBLIC_CONTROLS = frozenset(("设置", "通用", "iPhone储存空间", "iPhone 储存空间", "关于本机", "返回", "完成",
                             "取消", "搜索", "首页", "我的", "备忘录", "新建备忘录", "文件夹", "闹钟", "时钟",
                             "添加", "编辑", "保存", "确定", "照片", "最近项目", "外卖", "购物车", "去结算",
                             "美团红包", "吃喝玩乐神券", "确认", "极速支付", "允许", "不允许"))


def atomic_text(path, text):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".iak-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_text(path, limit=100000):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(limit)
    except (OSError, UnicodeError):
        return ""


def revision(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def scrub(text):
    """额外记录不保存凭据；不是通用隐私匿名化器，记录始终只留本机。"""
    text = str(text)
    text = re.sub(r"https?://[^\s<>]+", "[网址省略]", text)
    text = re.sub(r"(?i)(bearer\s+|sk-)[A-Za-z0-9._-]+", "[凭据省略]", text)
    text = re.sub(r"(?i)(password|token|api[_ -]?key|密码|验证码|银行卡号|身份证号)\s*[:：=]\s*[^\s,，;；]+",
                  r"\1：[省略]", text)
    return re.sub(r"(?<!\d)\d{6,}(?!\d)", "[号码省略]", text)


class ContextStore:
    def __init__(self, home, max_chars=1500):
        self.home = home
        self.root = os.path.join(home, "experience")
        self.summary_path = os.path.join(self.root, "summary.md")
        self.max_chars = max(200, min(int(max_chars), 5000))
        self._cache_lock = threading.Lock()
        self._cache = None

    @contextlib.contextmanager
    def locked(self):
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        fd = os.open(os.path.join(self.root, ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def preload(self):
        """启动或 /wake 读整份文档，没有检索、分类或模型调用。"""
        summary = read_text(self.summary_path)
        # 超长手工修改不截断指令；拒绝注入并显式提示通过 CLI 整理。
        too_long = len(summary) > self.max_chars
        profile = read_text(os.path.join(self.home, "profile.md"), 16000)
        profile = re.sub(r"<!--.*?-->", "", profile, flags=re.S).strip()
        value = {"summary": "" if too_long else summary, "revision": revision(summary),
                 "profile": profile, "oversized": too_long}
        with self._cache_lock:
            self._cache = value
        return dict(value)

    def snapshot(self):
        with self._cache_lock:
            cached = dict(self._cache) if self._cache is not None else None
        return cached if cached is not None else self.preload()

    def write_summary(self, text, expected_revision):
        text = scrub(text).strip()
        if len(text) > self.max_chars:
            raise ValueError("精简经验超过 %d 字，请先合并压缩" % self.max_chars)
        with self.locked():
            previous = read_text(self.summary_path)
            if revision(previous) != expected_revision:
                raise ValueError("经验已被其他助手更新，请重新读取后合并")
            if previous:
                atomic_text(os.path.join(self.root, "history", revision(previous) + ".md"), previous)
            atomic_text(self.summary_path, text)
        return self.preload()

    def append_review(self, task_id, report):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", task_id):
            raise ValueError("无效任务编号")
        def clean(value):
            if isinstance(value, str):
                return scrub(value)
            if isinstance(value, list):
                return [clean(x) for x in value]
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items()}
            return value
        safe = clean(report)
        safe["task_id"] = task_id
        text = json.dumps(safe, ensure_ascii=False, indent=2)
        with self.locked():
            atomic_text(os.path.join(self.root, "reviews", task_id + ".json"), text + "\n")

    def set_preference(self, key, value, quote, user_text):
        """只接受本轮真实用户原话；不能靠后台复盘推测永久偏好。"""
        key, value, quote = key.strip(), value.strip(), quote.strip()
        if not key or len(key) > 60 or any(c in key for c in "\r\n:：#<>"):
            raise ValueError("偏好名称无效")
        if not value or len(value) > 400 or "\n" in value:
            raise ValueError("偏好值应为简短的一行")
        if not quote or quote not in user_text:
            raise ValueError("必须引用本轮用户明确表达的原话")
        if re.search(r"密码|验证码|银行卡|身份证|token|api.?key", key + value, re.I):
            raise ValueError("不保存凭据或身份号码")
        if scrub(value) != value:
            raise ValueError("偏好含敏感号码或凭据，请去掉后再记")
        path = os.path.join(self.home, "profile.md")
        stamp = datetime.date.today().isoformat()
        with self.locked():
            text = read_text(path)
            line = "- %s：%s（更新于 %s）" % (key, value, stamp)
            pat = r"(?m)^- " + re.escape(key) + r"[:：].*$"
            if re.search(pat, text):
                seen = []
                def replace(_):
                    seen.append(True)
                    return line if len(seen) == 1 else ""
                text = re.sub(pat, replace, text)
            else:
                text = text.rstrip() + "\n" + line + "\n"
            atomic_text(path, text)
        self.preload()
        return {"ok": True, "key": key, "value": value}


def trace_path(home, task_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", task_id):
        raise ValueError("无效任务编号")
    return os.path.join(home, "experience", "traces", task_id + ".jsonl")


def append_trace(home, task_id, event):
    path = trace_path(home, task_id)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_trace(home, task_id):
    out = []
    for line in read_text(trace_path(home, task_id), 1000000).splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def record_call(home, task_id, name, args, result, duration):
    """只记录动作结构、控件标签与明确错误，不保存输入正文、树、截图或内部思考。"""
    def safe_args(a):
        if not isinstance(a, dict):
            return {}
        safe = {}
        for k in ("type", "shortcut", "direction", "bundle_id", "bundleId", "app", "key", "action"):
            if isinstance(a.get(k), (str, int, float, bool)):
                safe[k] = scrub(str(a[k]))[:100]
        # 不记录 label/text/query 等自由文本，避免把姓名、消息、账号写进操作经验。
        for k in ("x", "y", "dx", "dy", "element_id"):
            if isinstance(a.get(k), (int, float)):
                safe[k] = a[k]
        if isinstance(a.get("label"), str) and a["label"] in PUBLIC_CONTROLS:
            safe["label"] = a["label"]
        if isinstance(a.get("steps"), list):
            safe["steps"] = [safe_args(s) for s in a["steps"][:100]]
        return safe
    data = result.get("structuredContent") or {}
    if not data:
        for block in result.get("content") or []:
            if block.get("type") == "text":
                try:
                    data = json.loads(block["text"])
                    break
                except (ValueError, TypeError):
                    pass
    if not isinstance(data, dict):
        data = {}
    facts = {k: data[k] for k in ("ok", "drivable", "locked", "human_handoff", "retry_safe", "outcome_unknown")
             if isinstance(data.get(k), bool)}
    # 只保留白名单内的通用导航控件，不把聊天列表、输入内容或完整控件树写进经验。
    elements = data.get("elements") or []
    if isinstance(elements, list):
        visible = sorted({e.get("label") for e in elements if isinstance(e, dict) and
                          isinstance(e.get("label"), str) and e["label"] in PUBLIC_CONTROLS})
        if visible:
            facts["visible_controls"] = visible
    # 错误只保存机器可读的代码，不截取可能包含用户输入的报错正文。
    error = data.get("error")
    if isinstance(error, str) and re.fullmatch(r"[a-z_]{1,80}", error):
        facts["error"] = error
    try:
        append_trace(home, task_id, {"tool": name, "arguments": safe_args(args), "facts": facts,
                                   "is_error": bool(result.get("isError")),
                                   "duration_ms": round(duration * 1000), "at": time.time()})
        return True
    except OSError:
        # 动作可能已经成功，不能因为复盘记录失败把它改成“操作失败”诱发重试。
        print("iphone-agent-kit: 无法写入操作记录，保留工具原始结果", file=sys.stderr)
        return False


def phone_used(events):
    return any(e.get("tool", "").startswith("phone_") and e["tool"] not in
               ("phone_status", "phone_apps", "phone_release_owner", "phone_flow_list") for e in events)


def recovery_context(task):
    return {"goal": task.get("goal") or task["text"], "last_question": task.get("question", ""),
            "checkpoint": task.get("checkpoint") or {}, "last_result": task.get("result", ""),
            "instruction": "先核对真实进度再继续；未确认结果的发送、付款、提交等动作禁止直接重试。"}
