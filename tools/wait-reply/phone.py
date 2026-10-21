"""直接调 iphone-use daemon 的 HTTP 接口操作手机（不经过大模型）。

接管 → 做事 → 回主屏幕 → 交还占用 → 关 runner，全部在 session() 里完成，和个人规则里的收尾步骤一致。
daemon 地址和密码和 iphone-agent-kit 的 stop_runner.sh 用的是同一处。
"""
import contextlib
import json
import os
import plistlib
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = "http://127.0.0.1:44321"
OWNER = "wx-waiter"
PLIST = os.path.expanduser("~/Library/LaunchAgents/com.leeguoo.iphone-use.plist")
KIT_HOME = os.environ.get("IPHONE_AGENT_KIT_HOME", os.path.expanduser("~/.config/iphone-agent-kit"))
STOP_RUNNER = os.path.join(KIT_HOME, "stop_runner.sh")
WECHAT = "com.tencent.xin"


class NeedsHuman(Exception):
    """手机锁屏或要输密码，只能叫人来。"""


def _password():
    with open(PLIST, "rb") as f:
        return plistlib.load(f)["EnvironmentVariables"]["IPHONE_USE_PASSWORD"]


def call(method, path, body=None, timeout=45):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HOST + path, data=data, method=method, headers={
        "Authorization": "Bearer " + _password(),
        "X-Phone-Control": "1",
        "X-Phone-Owner": OWNER,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e)
        except Exception:
            detail = {}
        raise RuntimeError(f"{method} {path} -> {e.code} {detail.get('error', '')} {detail.get('hint', '')}") from None


def status():
    return call("GET", "/agent/status")


def ensure_agent(wait=90):
    """把手机拿到可操作状态。锁屏或要密码就抛 NeedsHuman。"""
    s = status()
    if not s.get("drivable"):
        call("POST", "/agent/mode", {"mode": "agent"})
    end = time.time() + wait
    while time.time() < end:
        s = status()
        if s.get("drivable"):
            return
        if s.get("locked") or s.get("setup_blocked_on") == "needs_passcode_on_phone":
            raise NeedsHuman("手机锁屏或要输密码")
        time.sleep(2)
    raise NeedsHuman("手机没能在 %d 秒内就绪" % wait)


def act(action):
    return call("POST", "/agent/input?return=delta", action)


def elements(query=None, limit=None, scope=None):
    q = {}
    if scope:
        q["scope"] = scope  # 带 scope/query 的读取，每行才有原始 index，点击要用它
    if query:
        q["query"] = query
    if limit:
        q["limit"] = limit
    path = "/agent/elements" + ("?" + urllib.parse.urlencode(q) if q else "")
    return call("GET", path, timeout=60)


def rows(res):
    return res.get("elements") or []


@contextlib.contextmanager
def session():
    """接管手机；离开时一定回主屏幕、交还占用、关 runner。"""
    ensure_agent()
    try:
        yield
    finally:
        for step in (
            lambda: act({"type": "shortcut", "name": "home"}),
            lambda: call("POST", "/agent/owner", {"release": True}),
            lambda: subprocess.run(["sh", STOP_RUNNER], capture_output=True, timeout=90),
        ):
            try:
                step()
            except Exception as e:  # 收尾每一步都要试到，别因为前一步失败就漏掉关 runner
                print("cleanup step failed:", e, flush=True)
