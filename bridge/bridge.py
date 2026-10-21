#!/usr/bin/env python3
"""iPhone 助手桥接服务。

快捷指令把一句话发到这里，服务把它排进队列，一次只交给一个助手（Codex 或 Claude Code）
去执行；助手通过 iphone-use MCP 操作被控的那台手机，完成后用 Bark 把完整结果推送回来。

只用 Python 标准库，兼容 macOS 自带的 /usr/bin/python3 (3.9)。
数据目录默认 ~/.config/iphone-agent-kit（可用环境变量 IPHONE_AGENT_KIT_HOME 改）：
config.json（含令牌，权限 600）、tasks.json、logs/、work/。
规则模板按「数据目录 → 仓库 templates/」的顺序找，放在数据目录里的同名文件优先。

    python3 bridge.py                # 启动服务
    python3 bridge.py --print-token  # 打印令牌
    python3 bridge.py --check        # 打印自动探测到的 codex / claude / dsh / iphone-use-mcp 路径
"""

import glob
import hmac
import ipaddress
import json
import os
import plistlib
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

HOME = os.path.expanduser("~")
DATA_DIR = os.environ.get("IPHONE_AGENT_KIT_HOME", os.path.join(HOME, ".config", "iphone-agent-kit"))
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
TASKS_PATH = os.path.join(DATA_DIR, "tasks.json")
WORK_DIR = os.path.join(DATA_DIR, "work")
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
# 规则模板：数据目录里的同名文件优先（用户自己改的），其次仓库的 templates/。
TEMPLATE_DIRS = [DATA_DIR, os.path.join(os.path.dirname(SRC_DIR), "templates"), os.path.join(SRC_DIR, "templates")]

AGENTS = ("codex", "claude", "dsh")
AGENT_NAMES = {"codex": "Codex", "claude": "Claude", "dsh": "DeepSeek"}
CONFIRM_MARK = "【需要确认】"



def system_tz():
    """系统时区名（如 Asia/Shanghai）。iphone-use 校验进程时要求时区一致，所以跟系统走。"""
    try:
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return os.environ.get("TZ") or "UTC"


DEFAULT_CONFIG = {
    "port": 18800,
    "token": "",
    # 默认用哪个助手：codex、claude 或 dsh（DeepSeek）（没指定时用它；开头说「用 Codex，……」可以临时换）。
    "default_agent": "claude",
    # 人设：默认开。人设文件见 templates/persona-xiaoyou.md；关掉后回复和提示语都用中性口吻。
    "persona": {"enabled": True, "file": "persona-xiaoyou.md"},
    # 只接受这些网段的请求：本机、局域网、USB 数据线直连（169.254 / fe80）、Tailscale。
    "allowed_networks": ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                         "169.254.0.0/16", "100.64.0.0/10", "::1/128", "fe80::/10",
                         "fd7a:115c:a1e0::/48"],
    "task_timeout_secs": 900,
    # 收到任务时的回话；留空 = 按人设开关自动选。可用 {ahead}（前面排了几件）。
    "ack_template": "",
    "ack_queued_template": "",
    "ack_think_template": "",
    # 自动分流（只对 Claude）：要挑选、对比、花钱的交给 Opus 慢慢想，其他交给 Sonnet 快速做。
    # 开头说「用 Opus，……」或「用 Sonnet，……」可以手动指定。
    "routing": {
        "enabled": True,
        # haiku：先让 Haiku 判断一下（实测 38/38 对，约 3 秒）；失败或超时再用关键词。keywords：只用关键词（31/38，0 秒）。
        "classifier": "haiku",
        "classifier_model": "claude-haiku-5-5",
        "classifier_timeout_secs": 8,
        "simple": {"model": "claude-sonnet-5-5", "effort": "medium"},
        # 要做决定的任务另外放行上网查资料，证据够了可以不碰手机。
        "think": {"model": "claude-opus-5-5", "effort": "medium", "extra_tools": "WebSearch WebFetch"},
        "think_keywords": [
            # 只写"要做决定"的词；只说平台名（京东、美团）不算，"看看京东订单"是简单查询
            "外卖", "奶茶", "咖啡", "点餐", "点杯", "点份", "点一份", "点个外卖", "订个", "订一",
            "订票", "订餐", "订房", "预订", "下单", "买", "购物", "挑", "选", "比较", "对比", "推荐",
            "哪个好", "哪家", "划算", "便宜", "优惠", "券", "红包", "规划", "攻略", "计划", "酒店",
            "机票", "火车票", "高铁票", "帮我决定", "你觉得", "值不值",
        ],
    },
    # Bark 推送的标题，按任务结果选用；可用 {agent}。
    "push_titles": {
        "done": "iPhone 助手",
        "ack": "iPhone 助手",
        "needs_confirm": "iPhone 助手 · 等你付款/确认",
        "stopped": "iPhone 助手 · 已停下",
        "failed": "iPhone 助手 · 没办成",
        "interrupted": "iPhone 助手 · 没办成",
    },
    "bark": {
        "server": "https://api.day.app",
        # 多台手机用 device_keys 列表；留空则不推送（任务结果仍可用 /result 查）。
        "device_keys": [],
        "group": "iPhone助手",
        # 单条推送正文的字节上限（苹果整条推送 4KB，留出标题和格式的余量）。
        "max_body_bytes": 3000,
    },
    "codex": {
        # 留空 = 自动探测（PATH 里的 codex、ChatGPT/Codex 桌面版自带的 codex）。
        "bin": "",
        # 只影响桥接任务，不影响 Codex 桌面版。留空 = 用 Codex 自己的默认模型。
        "model": "",
        # low 最快；遇到复杂界面老是点错，可以改成 medium。
        "reasoning_effort": "low",
        # 留空 = 普通速度；"priority" = Codex 的 Fast 档（约 2 倍速度，用量消耗更多）。
        "service_tier": "",
        "sandbox": "read-only",
        # 快速启动：不加载 ~/.codex/config.toml 里的插件、其他 MCP、记忆，只带 iphone-use。
        # 能省掉每次约 5 秒的启动时间；关掉（false）则和 Codex 桌面版用同一套配置。
        "fast_start": True,
    },
    # iphone-use-mcp 可执行文件；留空 = 自动探测（~/Applications/iPhoneUse.app 等）。Codex 和 Claude 共用。
    "iphone_use_mcp": "",
    "claude": {
        # 留空 = 自动探测（PATH 里的 claude、~/.local/bin/claude、Claude 桌面版自带的最新 claude）。
        "bin": "",
        "model": "",
        # 不读 ~/.claude/settings.json（里面的 apiKeyHelper 等设置在无人值守时可能失效）。
        # 代价是需要自己先 `claude auth login` 登录一次。
        "setting_sources": "project,local",
        # 思考档位：low / medium / high / xhigh / max；留空 = Claude Code 默认。
        "effort": "",
        # 关掉"先查找工具"：一开始就把 iphone-use 的工具全给它，每个任务省一次约 2 秒的思考。
        "tool_search": False,
        "allowed_tools": "mcp__iphone-use",
    },
    # DeepSeek Harness（官方 dsh 命令行）。profile 是专用配置：只挂 iphone-use 的手机工具，
    # 关掉了跑命令、读写文件、联网等（iphone-agent-kit init 会建好；见 templates/dsh-profile.patch.yml）。
    "dsh": {
        "bin": "",
        "profile": "iak",
    },
    # 被控手机发来的任务做完后，让它自己运行「手机朗读」快捷指令把回复念出来（默认关）。
    # 需要被控手机装了「手机朗读」，且 iphone-use 允许打开 shortcuts:// 链接（IPHONE_USE_ALLOW_URL_SCHEMES=shortcuts）。
    "phone_speak": {
        "enabled": False,
        "shortcut": "手机朗读",
        "daemon_url": "http://127.0.0.1:44321",
        "daemon_plist": "~/Library/LaunchAgents/com.leeguoo.iphone-use.plist",
    },
    "env": {
        "TZ": system_tz(),
        "IPHONE_USE_OWNER": "bridge",
    },
}

# 提示语两套：(人设版, 中性版)。人设开关在 config 的 persona.enabled。
PHRASES = {
    "ack": ("老板我这就去看看～", "好的，我去办。"),
    "ack_queued": ("老板稍等喔，前面还有{ahead}件事～", "前面还有{ahead}件事，请稍等。"),
    "ack_think": ("老板这个我仔细挑一下～", "好的，这件事我仔细考虑一下。"),
    "stop_done": ("好啦好啦，停下来了～", "已停止。"),
    "stop_done_dropped": ("好啦，停下来了～后面排着的%d件也帮你取消啰", "已停止，后面排队的%d件也取消了。"),
    "stop_dropped": ("排着的%d件帮你取消啰", "排队的%d件已取消。"),
    "stop_idle": ("我本来就没在做事啦～", "现在没有在做的事。"),
    "stopped_result": ("好啦，停下来了～", "已停止。"),
    "cancelled": ("已经取消啰", "已取消。"),
    "stop_acked": ("好～", "好的。"),
    "no_task": ("没找到你刚刚发的任务耶", "没有找到你刚发的任务。"),
    "done_empty": ("做完了", "做完了。"),
    "busy_new": ("还在弄喔，刚开始没多久～", "还在做，刚开始不久。"),
    "busy_mins": ("还在弄喔，已经弄了%d分钟了，快好了啦", "还在做，已经%d分钟了。"),
    "busy_queue": ("，后面还有%d件等着", "，后面还有%d件排队。"),
    "waiting_you": ("在等你回我喔：", "在等你回复："),
    "idle_last": ("闲着啦～刚刚那个：", "空闲。上一件事的结果："),
    "idle": ("闲着啦，有事叫我喔～", "空闲，有事可以吩咐。"),
    "no_talk": ("你好像什么都没说耶", "没有收到内容。"),
    "no_history": ("我们还没聊过耶，先叫我做件事嘛", "还没有可以接着聊的对话，请先发一个任务。"),
    "no_result": ("还没好喔", "还没做完。"),
}


def phrase(cfg, key, *args, **kw):
    pair = PHRASES[key]
    text = pair[0] if (cfg.get("persona") or {}).get("enabled", True) else pair[1]
    if kw:
        text = text.format(**kw)
    return text % args if args else text


def log(msg):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print("[%s] %s" % (stamp, msg), flush=True)


def deep_merge(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(write=True):
    """write=False 时不建目录、不生成令牌（--check 用，保证只读）。"""
    if write:
        os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    user = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            user = json.load(f)
    cfg = deep_merge(DEFAULT_CONFIG, user)
    if not cfg.get("token") and write:
        # 第一次启动：生成令牌并写回配置文件。
        user["token"] = secrets.token_urlsafe(24)
        cfg["token"] = user["token"]
        save_json(CONFIG_PATH, user, mode=0o600)  # 只写用户自己的设置，默认值升级后才能跟着更新
        log("已生成新令牌，写入 %s" % CONFIG_PATH)
    return cfg


def save_json(path, data, mode=0o600):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def read_template(name):
    for d in TEMPLATE_DIRS:
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return ""


def read_rules(cfg):
    """规则 = 人设（开着时）+ rules.md。"""
    parts = []
    persona = cfg.get("persona") or {}
    if persona.get("enabled", True):
        parts.append(read_template(persona.get("file") or "persona-xiaoyou.md"))
    parts.append(read_template("rules.md"))
    if (cfg.get("kit") or {}).get("beginner"):
        # 纯小白模式：停下来要人动手时，把怎么做讲清楚。注意 clean_reply 只推最后一段，所以步骤要写在同一段里。
        parts.append(read_template("beginner-mode.md"))
    return "\n\n".join(p for p in parts if p)


def _first_executable(candidates):
    for c in candidates:
        c = os.path.expanduser(c)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _resolve(cfg_path, which_name, candidates, what, hint):
    """配置里写了就用配置；否则 PATH → 常见位置；都找不到给清楚的报错。"""
    if cfg_path:
        path = os.path.expanduser(cfg_path)
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            raise RuntimeError("config.json 里写的 %s 路径不存在或不能执行：%s" % (what, cfg_path))
        return path
    found = shutil.which(which_name) or _first_executable(candidates)
    if not found:
        raise RuntimeError("找不到 %s。%s" % (what, hint))
    return found


def find_claude(cfg):
    desktop = glob.glob(os.path.join(
        HOME, "Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude"))

    def version_key(path):
        ver = path.split("/claude-code/")[1].split("/")[0]
        return [int(p) if p.isdigit() else 0 for p in ver.split(".")]

    return _resolve(cfg["claude"].get("bin"), "claude",
                    ["~/.local/bin/claude", "~/.claude/local/claude", "/opt/homebrew/bin/claude",
                     "/usr/local/bin/claude"] + sorted(desktop, key=version_key, reverse=True),
                    "Claude Code（claude）",
                    "请先安装 Claude Code 并运行 `claude auth login`，或在 config.json 的 claude.bin 里写完整路径。")


def find_codex(cfg):
    return _resolve(cfg["codex"].get("bin"), "codex",
                    ["/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
                     "/Applications/Codex.app/Contents/Resources/codex-cli/bin/codex",
                     "/opt/homebrew/bin/codex", "/usr/local/bin/codex", "~/.local/bin/codex"],
                    "Codex（codex）",
                    "请先安装 Codex 命令行，或在 config.json 的 codex.bin 里写完整路径。")


def find_dsh(cfg):
    return _resolve((cfg.get("dsh") or {}).get("bin"), "dsh",
                    ["/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh",
                     "~/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh",
                     "~/.local/bin/dsh", "/opt/homebrew/bin/dsh", "/usr/local/bin/dsh"],
                    "DeepSeek Harness（dsh）",
                    "请先安装 DeepSeek Harness 桌面版（官方，自带 dsh 命令行），或在 config.json 的 dsh.bin 里写完整路径。")


def find_iphone_use_mcp(cfg):
    return _resolve(cfg.get("iphone_use_mcp"), "iphone-use-mcp",
                    ["~/Applications/iPhoneUse.app/Contents/MacOS/iphone-use-mcp",
                     "/Applications/iPhoneUse.app/Contents/MacOS/iphone-use-mcp"],
                    "iphone-use 的 MCP 程序（iphone-use-mcp）",
                    "请先安装并 setup iphone-use，或在 config.json 的 iphone_use_mcp 里写完整路径。")


def strip_confirm(text):
    return text[len(CONFIRM_MARK):].strip() if text.startswith(CONFIRM_MARK) else text


STOP_RE = re.compile(r"^(小柚|助手)?[，,\s]*(快)?(停|停止|停下|停下来|暂停|别做了|别弄了|不用做了|不要做了|取消|算了)"
                     r"(任务|吧|了|一下|啦|啊|呀|喔|哦)*$")


def is_stop_command(text):
    """「停止任务」「别弄了」这类整句只是叫停的话，直接当停止处理，不排队。"""
    return bool(STOP_RE.match(re.sub(r"[。！!？?～~\s]", "", text or "")))


def clean_reply(text):
    """只留最后一段。助手有时会在回复前自言自语一段"我看到了什么"，那段不推送。"""
    text = (text or "").strip()
    mark = text.startswith(CONFIRM_MARK)
    body = text[len(CONFIRM_MARK):].strip() if mark else text
    paras = [x.strip() for x in re.split(r"\n\s*\n", body) if x.strip()]
    body = paras[-1] if paras else body
    return (CONFIRM_MARK + "\n" + body) if mark else body


def parse_agent_prefix(text):
    """「用 Codex，打开设置」→ ("codex", None, "打开设置")；「用 Opus，……」→ ("claude", "think", …)。"""
    m = re.match(r"^\s*用\s*(codex|claude|克劳德|扣德克斯|opus|欧珀斯|sonnet|索内特|deepseek|dsh|深度求索|迪普西克)\s*[,，:：。\s]*",
                 text, re.I)
    if not m:
        return None, None, text
    word = m.group(1).lower()
    if word in ("codex", "扣德克斯"):
        return "codex", None, text[m.end():].strip()
    if word in ("deepseek", "dsh", "深度求索", "迪普西克"):
        return "dsh", None, text[m.end():].strip()
    mode = "think" if word in ("opus", "欧珀斯") else "simple" if word in ("sonnet", "索内特") else None
    return "claude", mode, text[m.end():].strip()


def classify(text, cfg):
    """简单任务还是要挑选、对比、花钱的任务。只看关键词：免费、零延迟，判断错了开头说「用 Opus/Sonnet」纠正。"""
    words = (cfg.get("routing") or {}).get("think_keywords") or []
    return "think" if any(w in text for w in words) else "simple"


CLASSIFY_PROMPT = (
    "判断下面这句手机任务属于哪一类，只回一个词：\n"
    "simple = 要做什么已经说清楚了，照做就行（发一条内容明确的消息、查个东西、定闹钟、看订单状态、闲聊）\n"
    "think = 需要自己挑选、比较、规划、判断，或者要花钱（点外卖、买东西、订票订房、做攻略、比价、分析数据、打车、充值）\n"
    "任务：")


def classify_with_haiku(text, cfg):
    """用 Haiku 判断 simple / think；出错或超时返回 None，由关键词兜底。"""
    r = cfg.get("routing") or {}
    env = dict(os.environ); env.update(cfg.get("env", {}))
    try:
        cmd = [find_claude(cfg), "-p", CLASSIFY_PROMPT + text, "--model", r.get("classifier_model", "claude-haiku-5-5"),
               "--setting-sources", cfg["claude"].get("setting_sources", "project,local"),
               "--strict-mcp-config", "--tools", "", "--output-format", "json"]
        out = subprocess.run(cmd, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
                             cwd=WORK_DIR, timeout=float(r.get("classifier_timeout_secs", 8)))
        answer = (json.loads(out.stdout).get("result") or "").lower()
    except Exception as e:
        log("Haiku 分类失败，改用关键词：%s" % e)
        return None
    return "think" if "think" in answer else "simple" if "simple" in answer else None


ACK_PROMPT_PERSONA = (
    "你是小柚，18 岁台湾女生，称呼用户“老板”。用户刚用语音发来一条指令，你先用一句话回应：表示收到、马上去办。"
    "要求：必须和指令内容相关（点出要做什么），不超过 20 个字，像 LINE 聊天，带「啦、喔、欸」这类语气，"
    "只能用简体字，绝对不能出现繁体字（例如“幫”要写“帮”，“鬧鐘”要写“闹钟”，“設定”要写“设定”），不要引号、不要解释、不要承诺结果，只输出这一句话。\n用户指令：")
ACK_PROMPT_PLAIN = (
    "用户刚用语音发来一条指令，你先用一句话回应：表示收到、马上去办。"
    "要求：必须和指令内容相关（点出要做什么），不超过 20 个字，语气自然礼貌，"
    "只用简体中文，不要引号、不要解释、不要承诺结果，只输出这一句话。\n用户指令：")


# 模型偶尔会漏出繁体字；常见的几十个在这里换成简体（不全，只是兜底）。
_TRAD = dict(zip("幫鬧鐘設開關這個麼們來說會時點還對現覺機訊號傳發請問題見學習電腦視頻後從處啟動體應當總於將為與讓無備麼戶歡離準確認長門間裡邊",
                 "帮闹钟设开关这个么们来说会时点还对现觉机讯号传发请问题见学习电脑视频后从处启动体应当总于将为与让无备么户欢离准确认长门间里边"))


def to_simplified(text):
    return "".join(_TRAD.get(ch, ch) for ch in text)


def generate_ack(cfg, text):
    """用 Haiku 现编一句和指令相关的「收到」。出错、超时或输出不像样都返回 None，由固定的话兜底。"""
    r = cfg.get("routing") or {}
    persona = (cfg.get("persona") or {}).get("enabled", True)
    env = dict(os.environ); env.update(cfg.get("env", {}))
    env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
    try:
        cmd = [find_claude(cfg), "-p", (ACK_PROMPT_PERSONA if persona else ACK_PROMPT_PLAIN) + text[:300],
               "--model", r.get("classifier_model", "claude-haiku-5-5"),
               "--setting-sources", cfg["claude"].get("setting_sources", "project,local"),
               "--strict-mcp-config", "--tools", "", "--output-format", "json"]
        out = subprocess.run(cmd, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
                             cwd=WORK_DIR, timeout=float(cfg.get("ack_timeout_secs", 10)))
        line = (json.loads(out.stdout).get("result") or "").strip().splitlines()
        line = (line[0] if line else "").strip().strip("\"“”'「」")
    except Exception as e:
        log("生成回复语失败，用固定的话：%s" % e)
        return None
    line = to_simplified(line)
    return line if 2 <= len(line) <= 40 else None


def strip_simple_rules(rules, mode):
    """rules.md 里 <!-- 简单任务 --> … <!-- /简单任务 --> 之间的"要快"规则只给简单任务。"""
    if mode == "think":
        rules = re.sub(r"<!-- 简单任务 -->.*?<!-- /简单任务 -->\n?", "", rules, flags=re.S)
    return re.sub(r"<!-- /?简单任务 -->\n?", "", rules)


# ---------------------------------------------------------------- 推送

def utf8_chunks(text, limit):
    """按字节上限切分，不切断字符，尽量在换行处断开。"""
    chunks, cur, size = [], [], 0
    for line in text.splitlines(keepends=True):
        b = len(line.encode("utf-8"))
        if b > limit:
            for ch in line:
                cb = len(ch.encode("utf-8"))
                if size + cb > limit:
                    chunks.append("".join(cur))
                    cur, size = [], 0
                cur.append(ch)
                size += cb
            continue
        if size + b > limit:
            chunks.append("".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += b
    if cur:
        chunks.append("".join(cur))
    return [c.strip() for c in chunks if c.strip()] or [""]


def bark_push(cfg, title, body):
    bark = cfg["bark"]
    # device_keys 可以放多台手机的 key；兼容只写一个 device_key 的旧配置。
    keys = [k for k in (bark.get("device_keys") or [bark.get("device_key")]) if k]
    if not keys:
        log("未配置 Bark key，跳过推送：%s" % title)
        return False
    parts = utf8_chunks(body, int(bark.get("max_body_bytes", 3000)))
    ok = True
    for i, part in enumerate(parts, 1):
        t = title if len(parts) == 1 else "%s (%d/%d)" % (title, i, len(parts))
        for key in keys:
            payload = {"device_key": key, "title": t, "body": part or "（无内容）",
                       "group": bark.get("group", "iPhone助手")}
            req = urllib.request.Request(bark["server"].rstrip("/") + "/push",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json; charset=utf-8"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    r.read()
            except Exception as e:  # 推送失败不影响任务结果，状态里仍能查到。
                log("Bark 推送失败（%s…）：%s" % (key[:4], e))
                ok = False
        if len(parts) > 1:
            time.sleep(0.6)  # 保持分段顺序
    return ok


def phone_owner(cfg):
    """所有桥接任务共用的占用名：任务之间不会互相挡住，做完也由桥接服务统一交还。"""
    return cfg.get("env", {}).get("IPHONE_USE_OWNER", "bridge")


def daemon_call(cfg, path, payload, what, retries=0):
    """以桥接服务的占用名调用 iphone-use；手机被别的会话占着（409）时等 5 秒重试。"""
    ps = cfg.get("phone_speak") or {}
    try:
        with open(os.path.expanduser(ps["daemon_plist"]), "rb") as f:
            password = plistlib.load(f)["EnvironmentVariables"]["IPHONE_USE_PASSWORD"]
    except Exception as e:
        log("读不到 iphone-use 密码，跳过%s：%s" % (what, e))
        return False
    headers = {"Authorization": "Bearer " + password, "X-Phone-Control": "1",
               "X-Phone-Owner": phone_owner(cfg), "Content-Type": "application/json"}
    url = ps["daemon_url"].rstrip("/") + path
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                r.read()
            return True
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode("utf-8", "replace")
            if e.code == 409 and attempt < retries:
                time.sleep(5)
                continue
            log("%s失败：%s %s" % (what, e.code, detail))
        except Exception as e:
            log("%s失败：%s" % (what, e))
        return False
    return False


def release_phone(cfg):
    """把手机交还出去。Codex 被提前结束时来不及自己交还，所以每个任务结束都由这里兜底。"""
    return daemon_call(cfg, "/agent/owner", {"release": True}, "交还手机")


RUNNER_MARK = os.path.join(DATA_DIR, "runner_stopped_by_bridge")


def stop_runner(cfg):
    """关掉 runner（交给人用，手机不再处于自动化状态）。优先用配置目录里的 stop_runner.sh（已验证的路径）。
    成功后留一个标记文件：说明这次是桥接自己关的，下个任务开始前可以放心地重新接管；用户自己手动关的没有标记，不去抢。"""
    script = os.path.join(DATA_DIR, "stop_runner.sh")
    if os.path.exists(script):
        try:
            r = subprocess.run(["sh", script], capture_output=True, text=True, timeout=90)
            if '"ok":true' in r.stdout.replace(" ", ""):
                try:
                    open(RUNNER_MARK, "w").close()
                except OSError:
                    pass
                return True
            log("关 runner 没成功：%s" % (r.stdout + r.stderr).strip()[-200:])
        except Exception as e:
            log("关 runner 出错：%s" % e)
        return False
    return daemon_call(cfg, "/agent/mode", {"mode": "human"}, "关 runner")


def iphone_use_ready(cfg):
    """iphone-use status：手机可以被控制时退出码为 0。"""
    exe = shutil.which("iphone-use") or os.path.expanduser("~/.local/bin/iphone-use")
    env = dict(os.environ)
    env.update(cfg.get("env", {}))
    try:
        return subprocess.run([exe, "status"], capture_output=True, env=env, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resume_runner(cfg):
    """上个任务结束时桥接自己关了 runner，这次任务开始前把它重新打开并等到可用（最多 90 秒）。
    没有标记文件（比如用户自己手动关的）就什么都不做，不去抢手机。"""
    if not os.path.exists(RUNNER_MARK):
        return False
    t0 = time.time()
    if not daemon_call(cfg, "/agent/mode", {"mode": "agent"}, "重新接管手机"):
        log("重新接管手机没成功，交给助手自己重连")
        return False
    try:
        os.remove(RUNNER_MARK)
    except OSError:
        pass
    while time.time() - t0 < 90:
        if iphone_use_ready(cfg):
            log("手机已就绪（重新接管用了 %.0f 秒）" % (time.time() - t0))
            return True
        time.sleep(3)
    log("等了 90 秒手机还没就绪，交给助手自己重连")
    return True


def phone_speak(cfg, text):
    """在被控手机上运行「手机朗读」快捷指令，把回复念出来。"""
    ps = cfg.get("phone_speak") or {}
    if not ps.get("enabled") or not text:
        return False
    prefix = "shortcuts://run-shortcut?name=%s&input=text&text=" % quote(ps["shortcut"])
    body = text
    while len(prefix + quote(body)) > 2000:  # iphone-use 限制链接 2048 字节
        body = body[:-10]
    return daemon_call(cfg, "/agent/input", {"type": "open_url", "url": prefix + quote(body)},
                       "手机朗读", retries=3)


# ---------------------------------------------------------------- 任务

class Bridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.finished_cv = threading.Condition(self.lock)
        self.resume_lock = threading.Lock()  # 叫醒和任务开始前的接管不能同时进行
        self.warm_until = 0.0  # 叫醒后在这个时间点之前不重复叫醒
        self.last_task_at = 0.0
        self.stop_acked = {}  # 来源地址 → 刚用语音叫停的时间，免得等结果的快捷指令再念一遍
        self.queue = deque()
        self.current = None
        self.proc = None
        self.tasks = self._load_tasks()
        os.makedirs(WORK_DIR, exist_ok=True)
        threading.Thread(target=self._worker, daemon=True).start()

    def _push_ack(self, text, fallback, queued):
        """推「收到」。默认让小模型按指令内容现编一句（排队时仍用固定的话，因为要说前面还有几件）；失败就用固定的话。"""
        msg = None
        if self.cfg.get("ack_mode", "llm") == "llm" and not queued:
            t0 = time.time()
            msg = generate_ack(self.cfg, text)
            log("回复语：%s（%.1f 秒）" % (msg or "生成失败，用固定的话", time.time() - t0))
        bark_push(self.cfg, self.cfg["push_titles"].get("ack", "iPhone 助手"), msg or fallback)

    def warm_up(self):
        """快捷指令一开始（用户还在说话）就叫醒：提前把桥接自己关掉的 runner 重新接管好，说完话就能直接开工。
        用户自己手动关的（没有标记文件）不会动。叫醒后 90 秒内没有任务来（用户取消了），就再把 runner 关掉。"""
        now = time.time()
        with self.lock:
            if self.current or self.queue or now < self.warm_until:
                return {"ok": True, "warming": False}
            self.warm_until = now + 90
        threading.Thread(target=self._warm_worker, args=(now,), daemon=True).start()
        return {"ok": True, "warming": True}

    def _warm_worker(self, woke_at):
        with self.resume_lock:
            resumed = resume_runner(self.cfg)
        if not resumed:
            return
        time.sleep(max(0.0, woke_at + 90 - time.time()))
        with self.lock:
            used = self.last_task_at >= woke_at or self.current or self.queue
        if not used:
            log("叫醒后 90 秒没有任务，重新关掉 runner")
            stop_runner(self.cfg)

    def _load_tasks(self):
        try:
            with open(TASKS_PATH, encoding="utf-8") as f:
                tasks = json.load(f)
        except (OSError, ValueError):
            return []
        for t in tasks:  # 上次关机时没跑完的任务
            if t.get("state") in ("queued", "running"):
                t["state"] = "interrupted"
        return tasks

    def _save(self):
        save_json(TASKS_PATH, self.tasks[-100:])

    def _find(self, task_id):
        for t in reversed(self.tasks):
            if t["id"] == task_id:
                return t
        return None

    def wait_latest(self, client, timeout):
        """等这个来源最近提交的那个任务做完，最多等 timeout 秒。

        快捷指令拿不到任务编号，所以按来源地址找"它刚发的那个任务"。
        """
        deadline = time.time() + timeout
        with self.lock:
            if time.time() - self.stop_acked.pop(client, 0) < 120:
                return {"ok": True, "done": True, "speech": phrase(self.cfg, "stop_acked")}
            task = next((t for t in reversed(self.tasks) if t.get("client") == client), None)
            if not task:
                return {"ok": True, "done": True, "speech": phrase(self.cfg, "no_task")}
            while task["state"] in ("queued", "running") and time.time() < deadline:
                self.finished_cv.wait(max(0.1, deadline - time.time()))
            if task["state"] in ("queued", "running"):
                return {"ok": True, "done": False, "speech": ""}
            result = task.get("result") or ""
        result = strip_confirm(result)
        return {"ok": True, "done": True, "state": task["state"], "speech": result or phrase(self.cfg, "done_empty")}

    def submit(self, text, agent=None, session="new", reply_to=None, client=None, speak=False):
        prefix_agent, mode, text = parse_agent_prefix(text)
        agent = (agent or prefix_agent or self.cfg["default_agent"]).lower()
        if agent not in AGENTS:
            raise ValueError("不支持的助手：%s（可选 codex / claude / dsh）" % agent)
        if not text:
            raise ValueError(phrase(self.cfg, "no_talk"))
        resume = None
        with self.lock:
            if reply_to is not None:
                base = self._find(reply_to) if reply_to else next(
                    (t for t in reversed(self.tasks)
                     if t.get("session_id") and t["state"] in ("done", "needs_confirm")), None)
                if not base or not base.get("session_id"):
                    raise ValueError(phrase(self.cfg, "no_history"))
                agent, resume = base["agent"], base["session_id"]
                mode = base.get("mode")  # 接着聊时沿用原来那个模型
            elif session == "last":
                base = next((t for t in reversed(self.tasks)
                             if t["agent"] == agent and t.get("session_id")
                             and t["state"] in ("done", "needs_confirm")), None)
                resume = base["session_id"] if base else None
            elif session and session != "new":
                resume = session
            routing = self.cfg.get("routing") or {}
            if agent != "claude" or not routing.get("enabled"):
                mode = None
            elif not mode and routing.get("classifier") != "haiku":
                mode = classify(text, self.cfg)
            # classifier=haiku 时 mode 留空，开始执行前再判断，不耽误马上回「收到」
            task = {"id": uuid.uuid4().hex[:8], "text": text, "agent": agent, "resume": resume,
                    "mode": mode,
                    "state": "queued", "created": time.time(), "result": "", "session_id": None,
                    "client": client, "speak_on_phone": bool(speak)}
            ahead = len(self.queue) + (1 if self.current else 0)
            self.tasks.append(task)
            self.queue.append(task)
            self._save()
            self.wake.notify()
        if ahead:
            tpl = self.cfg.get("ack_queued_template") or phrase(self.cfg, "ack_queued")
        elif mode == "think" and not resume:
            tpl = self.cfg.get("ack_think_template") or phrase(self.cfg, "ack_think")
        else:
            tpl = self.cfg.get("ack_template") or phrase(self.cfg, "ack")
        ack = tpl.format(agent=AGENT_NAMES[agent], ahead=ahead, id=task["id"], text=text)
        self.last_task_at = time.time()
        log("收到任务 %s [%s%s] %s" % (task["id"], agent, "/" + mode if mode else "", text))
        # 快捷指令不出声，「收到」用 Bark 推送告诉用户（放后台线程，不拖慢响应）。
        if self.cfg.get("ack_by_push", True):
            threading.Thread(target=self._push_ack, args=(text, ack, bool(ahead)), daemon=True).start()
        return {"ok": True, "id": task["id"], "agent": agent, "ahead": ahead,
                "resumed": bool(resume), "ack": ack}

    def stop(self):
        with self.lock:
            dropped = len(self.queue)
            for t in self.queue:
                t["state"] = "cancelled"
                t["result"] = phrase(self.cfg, "cancelled")
            self.queue.clear()
            self.finished_cv.notify_all()
            cur, proc = self.current, self.proc
            if cur:
                cur["stopped"] = True
            self._save()
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        stopped = bool(cur)
        if stopped and dropped:
            speech = phrase(self.cfg, "stop_done_dropped", dropped)
        elif stopped:
            speech = phrase(self.cfg, "stop_done")
        elif dropped:
            speech = phrase(self.cfg, "stop_dropped", dropped)
        else:
            speech = phrase(self.cfg, "stop_idle")
        return {"ok": True, "stopped_current": stopped, "cancelled": dropped, "speech": speech}

    def status(self):
        with self.lock:
            cur = dict(self.current) if self.current else None
            queued = len(self.queue)
            last = next((dict(t) for t in reversed(self.tasks)
                         if t["state"] in ("done", "needs_confirm", "failed")), None)
        if cur:
            mins = int((time.time() - cur.get("started", time.time())) // 60)
            speech = phrase(self.cfg, "busy_new") if mins < 1 else phrase(self.cfg, "busy_mins", mins)
            if queued:
                speech += phrase(self.cfg, "busy_queue", queued)
        elif last and last["state"] == "needs_confirm":
            speech = phrase(self.cfg, "waiting_you") + strip_confirm(last.get("result") or "")
        elif last and last.get("result"):
            speech = phrase(self.cfg, "idle_last") + last["result"]
        else:
            speech = phrase(self.cfg, "idle")
        return {"ok": True, "running": cur, "queued": queued, "last": last, "speech": speech}

    # ------------------------------------------------------------ 执行

    def _worker(self):
        while True:
            with self.lock:
                while not self.queue:
                    self.wake.wait()
                task = self.queue.popleft()
                task["state"] = "running"
                task["started"] = time.time()
                self.current = task
                self._save()
            if task["agent"] == "claude" and not task.get("mode") and (self.cfg.get("routing") or {}).get("enabled"):
                t0 = time.time()
                task["mode"] = classify_with_haiku(task["text"], self.cfg) or classify(task["text"], self.cfg)
                log("任务 %s 分流：%s（%.1f 秒）" % (task["id"], task["mode"], time.time() - t0))
            try:
                self._run(task)
            except Exception as e:
                task["state"], task["result"] = "failed", "桥接服务出错：%s" % e
                log("任务 %s 出错：%s" % (task["id"], e))
            with self.lock:
                if task.get("stopped"):
                    task["state"] = "stopped"
                    task["result"] = phrase(self.cfg, "stopped_result")
                task["finished"] = time.time()
                self.current, self.proc = None, None
                self._save()
                self.finished_cv.notify_all()
            self._notify(task)
            release_phone(self.cfg)
            with self.lock:
                idle = not self.queue
            # 停在付款/确认页，或后面没有排队的任务了：关 runner，免得手机一直处在自动化状态打扰用户。
            if self.cfg.get("stop_runner_after_task", True) and (task["state"] == "needs_confirm" or idle):
                stop_runner(self.cfg)

    def _prompt(self, task):
        if task["resume"]:
            return task["text"]
        rules = strip_simple_rules(read_rules(self.cfg), task.get("mode"))
        return "%s\n\n---\n用户指令：%s" % (rules, task["text"]) if rules else task["text"]

    def _command(self, task, out_file):
        prompt = self._prompt(task)
        if task["agent"] == "codex":
            c = self.cfg["codex"]
            codex_bin = find_codex(self.cfg)
            mcp_bin = find_iphone_use_mcp(self.cfg)
            tz = self.cfg.get("env", {}).get("TZ") or system_tz()
            # 无人值守时 Codex 没法弹窗确认，所以只对 iphone-use 的工具预先放行。
            opts = ["--skip-git-repo-check", "--json", "-o", out_file,
                    "-c", 'sandbox_mode="%s"' % c.get("sandbox", "read-only"),
                    "-c", 'mcp_servers.iphone-use.default_tools_approval_mode="approve"',
                    # Codex 不把自己的环境变量传给 MCP，所以占用名要在这里单独给。
                    "-c", "mcp_servers.iphone-use.env={IPHONE_USE_OWNER=%s, TZ=%s}"
                    % (json.dumps(phone_owner(self.cfg)), json.dumps(tz))]
            if c.get("fast_start", True):
                opts += ["--ignore-user-config", "--disable", "apps", "--disable", "plugins",
                         "--disable", "memories",
                         "-c", 'approval_policy="never"',
                         "-c", "suppress_unstable_features_warning=true",
                         "-c", "mcp_servers.iphone-use.command=%s" % json.dumps(mcp_bin)]
            if c.get("model"):
                opts += ["-m", c["model"]]
            if c.get("reasoning_effort"):
                opts += ["-c", 'model_reasoning_effort="%s"' % c["reasoning_effort"]]
            if c.get("service_tier"):
                opts += ["-c", 'service_tier="%s"' % c["service_tier"]]
            if task["resume"]:
                return [codex_bin, "exec", "resume"] + opts + [task["resume"], prompt]
            return [codex_bin, "exec"] + opts + [prompt]
        if task["agent"] == "dsh":
            d = self.cfg.get("dsh") or {}
            cmd = [find_dsh(self.cfg), "--profile", d.get("profile") or "iak", "--json"]
            if task["resume"]:
                cmd += ["--session-id", task["resume"]]
            return cmd + [prompt]
        c = self.cfg["claude"]
        route = (self.cfg.get("routing") or {}).get(task.get("mode") or "", {})
        extra = (route.get("extra_tools") or "").split()
        tools = " ".join([c.get("allowed_tools", "mcp__iphone-use")] + extra)
        # --tools 限定内置工具：默认一个都不给（没有 Bash、读写文件），要做决定的任务只多给上网查资料。
        cmd = [find_claude(self.cfg), "-p", prompt, "--output-format", "json", "--allowedTools", tools,
               "--tools", ",".join(extra)]
        if c.get("setting_sources"):
            cmd += ["--setting-sources", c["setting_sources"]]
        # 不读用户设置时，注册在用户级的 iphone-use 也不会加载，所以直接在命令里给它；
        # --strict-mcp-config 让它只加载 iphone-use，启动更快。
        mcp = {"mcpServers": {"iphone-use": {
            "type": "stdio", "command": find_iphone_use_mcp(self.cfg), "args": [],
            "env": {"TZ": self.cfg.get("env", {}).get("TZ") or system_tz(),
                    "IPHONE_USE_OWNER": phone_owner(self.cfg)}}}}
        cmd += ["--mcp-config", json.dumps(mcp), "--strict-mcp-config"]
        model, effort = route.get("model") or c.get("model"), route.get("effort") or c.get("effort")
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        if task["resume"]:
            cmd += ["--resume", task["resume"]]
        return cmd

    def _run(self, task):
        out_file = os.path.join(WORK_DIR, "last-%s.txt" % task["id"])
        cmd = self._command(task, out_file)
        env = dict(os.environ)
        env.update(self.cfg.get("env", {}))
        if self.cfg.get("stop_runner_after_task", True):
            with self.resume_lock:
                resume_runner(self.cfg)
        if task["agent"] == "claude" and not self.cfg["claude"].get("tool_search", False):
            env["ENABLE_TOOL_SEARCH"] = "false"
        if task["agent"] == "claude":
            # 不读用户自己的 ~/.claude/CLAUDE.md：里面直接对话用的规则（关 runner、推送、不抢手机……）会和桥接的规则打架。
            env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
        log("开始任务 %s：%s%s" % (task["id"], task["agent"], "（接着上次对话）" if task["resume"] else ""))
        proc = subprocess.Popen(cmd, cwd=WORK_DIR, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        with self.lock:
            self.proc = proc
        if task["agent"] == "codex":
            return self._run_codex(task, proc, out_file)
        try:
            out, err = proc.communicate(timeout=int(self.cfg["task_timeout_secs"]))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            out, err = proc.communicate()
            task["state"] = "failed"
            task["result"] = "超时（超过%d秒）已停止。" % int(self.cfg["task_timeout_secs"])
            return
        out = out.decode("utf-8", "replace")
        err = err.decode("utf-8", "replace")
        if task["agent"] == "codex":
            self._parse_codex(task, proc.returncode, out, err, out_file)
        elif task["agent"] == "dsh":
            self._parse_dsh(task, proc.returncode, out, err)
        else:
            self._parse_claude(task, proc.returncode, out, err)
        try:
            os.remove(out_file)
        except OSError:
            pass

    def _run_codex(self, task, proc, out_file):
        """边读 Codex 的事件边判断：一轮结束就拿结果，不等它慢吞吞地退出（能省几秒）。"""
        state = {"turn": None, "message": "", "error": ""}
        turn_done = threading.Event()
        err_lines = []

        def read_stdout():
            for raw in proc.stdout:
                try:
                    ev = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                kind, item = ev.get("type"), ev.get("item") or {}
                if kind == "thread.started":
                    task["session_id"] = ev.get("thread_id")
                elif kind == "item.completed" and item.get("type") == "agent_message":
                    state["message"] = (item.get("text") or "").strip()
                elif kind in ("turn.completed", "turn.failed"):
                    state["turn"] = kind
                    state["error"] = json.dumps(ev.get("error") or "", ensure_ascii=False)
                    turn_done.set()
            turn_done.set()

        def read_stderr():
            for raw in proc.stderr:
                err_lines.append(raw.decode("utf-8", "replace"))
                del err_lines[:-30]

        threading.Thread(target=read_stdout, daemon=True).start()
        threading.Thread(target=read_stderr, daemon=True).start()
        if not turn_done.wait(int(self.cfg["task_timeout_secs"])):
            os.killpg(proc.pid, signal.SIGTERM)
            task["state"] = "failed"
            task["result"] = "超时（超过%d秒）已停止。" % int(self.cfg["task_timeout_secs"])
            return
        try:
            proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)  # 回复已经拿到了，剩下的只是退出
            except ProcessLookupError:
                pass
        task["session_id"] = task["session_id"] or task["resume"]
        result = state["message"]
        if not result and os.path.exists(out_file):
            with open(out_file, encoding="utf-8") as f:
                result = f.read().strip()
        try:
            os.remove(out_file)
        except OSError:
            pass
        if state["turn"] == "turn.completed" and result:
            task["state"], task["result"] = "done", clean_reply(result)
        else:
            task["state"] = "failed"
            task["result"] = result or "Codex 没有回复：%s %s" % (state["error"], "".join(err_lines)[-600:])

    def _parse_codex(self, task, code, out, err, out_file):
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "thread.started":
                task["session_id"] = ev.get("thread_id")
        task["session_id"] = task["session_id"] or task["resume"]
        result = ""
        if os.path.exists(out_file):
            with open(out_file, encoding="utf-8") as f:
                result = f.read().strip()
        task["state"] = "done" if code == 0 and result else "failed"
        task["result"] = result or ("Codex 退出码 %s：%s" % (code, err.strip()[-800:]))

    def _parse_dsh(self, task, code, out, err):
        """dsh --json：每行一个事件，session 事件带会话号，final 事件是最终回复。"""
        final, errors = "", []
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kind = ev.get("type")
            if kind == "session":
                task["session_id"] = ev.get("sessionId")
            elif kind == "final":
                final = (ev.get("text") or "").strip()
            elif kind == "error":
                errors.append(json.dumps(ev, ensure_ascii=False)[:300])
        task["session_id"] = task["session_id"] or task["resume"]
        if code == 0 and final:
            task["state"], task["result"] = "done", clean_reply(final)
        else:
            tail = "；".join(errors) or err.strip()[-600:]
            task["state"] = "failed"
            task["result"] = final or "DeepSeek 退出码 %s：%s" % (code, tail)

    def _parse_claude(self, task, code, out, err):
        try:
            data = json.loads(out)
        except ValueError:
            task["state"] = "failed"
            task["result"] = "Claude 退出码 %s：%s" % (code, (err or out).strip()[-800:])
            return
        task["session_id"] = data.get("session_id") or task["resume"]
        task["result"] = clean_reply(data.get("result"))
        task["state"] = "failed" if data.get("is_error") or code != 0 else "done"
        if task["state"] == "failed" and not task["result"]:
            task["result"] = "Claude 退出码 %s：%s" % (code, err.strip()[-800:])

    def _notify(self, task):
        result = task.get("result") or ""
        if task["state"] == "done" and result.startswith(CONFIRM_MARK):
            task["state"] = "needs_confirm"
            self._save()
            result = result[len(CONFIRM_MARK):].strip()
        log("任务 %s 结束：%s" % (task["id"], task["state"]))
        titles = self.cfg["push_titles"]
        title = titles.get(task["state"]) or titles.get("done", "iPhone 助手")
        title = title.format(agent=AGENT_NAMES[task["agent"]])
        # 正文只放助手自己的回复，不重复你说的指令。
        bark_push(self.cfg, title, result)
        if task.get("speak_on_phone") and task["state"] != "stopped":
            phone_speak(self.cfg, result)


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    bridge = None
    server_version = "iphone-agent-kit-bridge/1"

    def log_message(self, fmt, *args):
        pass  # 不记录每个请求，避免日志里出现内容

    def _send(self, code, data):
        # ?say=1：只回一句纯文字，快捷指令直接朗读，不用解析 JSON。
        # /wait 没等到结果时回空文字，快捷指令据此决定继续等。
        if parse_qs(urlparse(self.path).query).get("say"):
            text = data.get("ack") or data.get("speech") or data.get("error") or ""
            body = text.encode("utf-8")
            ctype = "text/plain; charset=utf-8"
        else:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self):
        cfg = self.bridge.cfg
        try:
            ip = ipaddress.ip_address(self.client_address[0])
            nets = [ipaddress.ip_network(n) for n in cfg["allowed_networks"]]
            if not any(ip in n for n in nets if n.version == ip.version):
                log("拒绝来自 %s 的请求（不在 allowed_networks 里）" % ip)
                self._send(403, {"ok": False, "error": "这个网络不允许访问"})
                return False
        except ValueError:
            self._send(403, {"ok": False, "error": "无法识别来源地址"})
            return False
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else self.headers.get("X-Token", "")
        if not hmac.compare_digest(token.encode(), cfg["token"].encode()):
            self._send(401, {"ok": False, "error": "令牌不对"})
            return False
        return True

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64 * 1024:
            raise ValueError("请求太大")
        raw = self.rfile.read(n) if n else b""
        # 快捷指令直接把听写结果当纯文字发来；助手和对话用网址参数指定。
        query = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        if self.headers.get("Content-Type", "").startswith("text/plain"):
            query["text"] = raw.decode("utf-8", "replace")
            return query
        if not raw:
            return query
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            return {"text": raw.decode("utf-8", "replace")}

    def do_GET(self):
        if not self._allowed():
            return
        url = urlparse(self.path)
        if url.path == "/status":
            return self._send(200, self.bridge.status())
        if url.path == "/result":
            q = parse_qs(url.query)
            task_id = (q.get("id") or [""])[0]
            with self.bridge.lock:
                t = self.bridge._find(task_id) if task_id else next(
                    (x for x in reversed(self.bridge.tasks) if x["state"] not in ("queued", "running")), None)
                t = dict(t) if t else None
            if not t:
                return self._send(404, {"ok": False, "error": "没有找到任务"})
            return self._send(200, {"ok": True, "task": t, "speech": t.get("result") or phrase(self.bridge.cfg, "no_result")})
        if url.path == "/wait":
            q = parse_qs(url.query)
            secs = min(55.0, float((q.get("timeout") or ["45"])[0]))
            return self._send(200, self.bridge.wait_latest(self.client_address[0], secs))
        if url.path == "/health":
            return self._send(200, {"ok": True})
        if url.path == "/wake":
            return self._send(200, self.bridge.warm_up())
        self._send(404, {"ok": False, "error": "没有这个接口"})

    def do_POST(self):
        if not self._allowed():
            return
        path = urlparse(self.path).path
        try:
            body = self._body()
            client = self.client_address[0]
            if path in ("/task", "/reply") and is_stop_command(str(body.get("text", ""))):
                result = self.bridge.stop()
                result["ack"] = result["speech"]
                with self.bridge.lock:
                    self.bridge.stop_acked[client] = time.time()
                return self._send(200, result)
            if path == "/task":
                return self._send(200, self.bridge.submit(
                    str(body.get("text", "")).strip(), body.get("agent") or None,
                    body.get("session") or "new", client=client, speak=body.get("speak")))
            if path == "/reply":
                return self._send(200, self.bridge.submit(
                    str(body.get("text", "")).strip(), reply_to=body.get("id") or "",
                    client=client, speak=body.get("speak")))
            if path == "/stop":
                return self._send(200, self.bridge.stop())
            if path == "/wake":
                return self._send(200, self.bridge.warm_up())
        except ValueError as e:
            return self._send(400, {"ok": False, "error": str(e), "ack": str(e)})
        self._send(404, {"ok": False, "error": "没有这个接口"})


def main():
    cfg = load_config(write="--check" not in sys.argv)
    if "--print-token" in sys.argv:
        print(cfg["token"])
        return
    if "--check" in sys.argv:
        for name, fn in (("codex", find_codex), ("claude", find_claude), ("dsh", find_dsh), ("iphone_use_mcp", find_iphone_use_mcp)):
            try:
                print("%s: %s" % (name, fn(cfg)))
            except RuntimeError as e:
                print("%s: 未找到（%s）" % (name, e))
        return
    Handler.bridge = Bridge(cfg)
    server = ThreadingHTTPServer(("0.0.0.0", int(cfg["port"])), Handler)
    log("桥接服务已启动，端口 %s，默认助手 %s" % (cfg["port"], cfg["default_agent"]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
