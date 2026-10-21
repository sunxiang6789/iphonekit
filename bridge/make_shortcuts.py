#!/usr/bin/env python3
"""生成快捷指令：只有一个「让手机做事」（听写一句话发给桥接服务，朗读“收到”；结果用 Bark 推送，不朗读）。

每个快捷指令都很短：（听写）→ 把文字发给 Mac 上的桥接服务 → 朗读服务回的那句话；
等结果版之后再反复问 /wait，拿到助手的回复就朗读。
服务用 ?say=1 回纯文字，所以快捷指令里不用解析 JSON。

    python3 make_shortcuts.py --out ./shortcuts
    python3 make_shortcuts.py --url http://my-mac.local:18800 --out ./shortcuts

服务地址默认用本机的 .local 名（scutil --get LocalHostName）加配置里的端口。
令牌从 ~/.config/iphone-agent-kit/config.json 读取，写在快捷指令的请求头里，不会出现在网址中，
所以生成的文件含令牌，只能在自己的 Mac 上生成，不要发给别人。
生成后用 `shortcuts sign` 签名（偶尔返回 500，会自动重试），得到可以隔空投送到手机上导入的 .shortcut 文件。
"""

import argparse
import json
import os
import plistlib
import subprocess
import sys
import time
import uuid

OBJ = "￼"  # 快捷指令里代表"变量"的占位符


def _uuid():
    return str(uuid.uuid4()).upper()


def _token(text, attachments=None):
    return {"Value": {"string": text, "attachmentsByRange": attachments or {}},
            "WFSerializationType": "WFTextTokenString"}


def _var_token(out_uuid, name):
    return _token(OBJ, {"{0, 1}": {"Type": "ActionOutput", "OutputUUID": out_uuid, "OutputName": name}})


def _output(out_uuid, name):
    return {"Value": {"Type": "ActionOutput", "OutputUUID": out_uuid, "OutputName": name},
            "WFSerializationType": "WFTextTokenAttachment"}


def dictate(u):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.dictatetext",
            "WFWorkflowActionParameters": {"UUID": u, "WFDictateTextStopListening": "After Pause"}}


def request(u, url, token, method, body_uuid=None):
    header = lambda k, v: {"WFItemType": 0, "WFKey": _token(k), "WFValue": _token(v)}
    params = {
        "UUID": u,
        "WFURL": url,
        "WFHTTPMethod": method,
        "ShowHeaders": True,
        "WFHTTPHeaders": {"Value": {"WFDictionaryFieldValueItems": [
            header("Authorization", "Bearer " + token),
            header("Content-Type", "text/plain; charset=utf-8"),
        ]}, "WFSerializationType": "WFDictionaryFieldValue"},
    }
    if body_uuid:
        params["WFHTTPBodyType"] = "File"
        params["WFRequestVariable"] = _output(body_uuid, "Dictated Text")
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": params}


def speak(src_uuid):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.speaktext",
            "WFWorkflowActionParameters": {"WFText": _var_token(src_uuid, "Contents of URL")}}


def speak_text(text):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.speaktext",
            "WFWorkflowActionParameters": {"WFText": _token(text)}}


HAS_ANY_VALUE = 100  # 快捷指令里「有任何值」的条件编号


def wait_and_speak(base, token, still_working_text, rounds=6, secs=45):
    """重复问 Mac「做完没」：/wait 最多挂 secs 秒，有文字就朗读并结束。"""
    loop, cond, r = _uuid(), _uuid(), _uuid()
    return [
        {"WFWorkflowActionIdentifier": "is.workflow.actions.repeat.count",
         "WFWorkflowActionParameters": {"GroupingIdentifier": loop, "WFControlFlowMode": 0,
                                        "WFRepeatCount": rounds}},
        request(r, "%s/wait?say=1&timeout=%d" % (base, secs), token, "GET"),
        {"WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
         "WFWorkflowActionParameters": {
             "GroupingIdentifier": cond, "WFControlFlowMode": 0,
             # 必须包成 Variable，否则条件永远不成立（上游在 iOS 27 实测过）。
             "WFInput": {"Type": "Variable", "Variable": _output(r, "Contents of URL")},
             "WFCondition": HAS_ANY_VALUE}},
        speak(r),
        {"WFWorkflowActionIdentifier": "is.workflow.actions.exit", "WFWorkflowActionParameters": {}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
         "WFWorkflowActionParameters": {"GroupingIdentifier": cond, "WFControlFlowMode": 2}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.repeat.count",
         "WFWorkflowActionParameters": {"GroupingIdentifier": loop, "WFControlFlowMode": 2}},
        speak_text(still_working_text),
    ]


def workflow(actions, color, glyph):
    return {
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowClientVersion": "2607.0.3",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": color, "WFWorkflowIconGlyphNumber": glyph},
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": [],
        "WFQuickActionSurfaces": [],
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowActions": actions,
    }


def spoken(base, token, path, color, glyph, wait=False, still_working_text="还在做，做完会推送给你。", say=False):
    """听写 → POST；say=True 才朗读「收到」，wait=True 时再等结果并朗读。默认不出声，「收到」由 Bark 推送。"""
    d, r = _uuid(), _uuid()
    # 第一步先「叫醒」桥接服务：用户还在说话的时候，它就在后台把手机准备好（说完话就不用再等十几秒）。
    actions = [request(_uuid(), base + "/wake", token, "GET"), dictate(d),
               request(r, base + path, token, "POST", d)] + ([speak(r)] if say else [])
    if wait:
        actions += wait_and_speak(base, token, still_working_text)
    return workflow(actions, color, glyph)


def plain(base, token, path, method, color, glyph):
    """不听写，直接请求 → 朗读。"""
    r = _uuid()
    return workflow([request(r, base + path, token, method), speak(r)], color, glyph)


def reader():
    """「手机朗读」：把传进来的文字念出来。由 Mac 通过 shortcuts:// 链接触发，只装在被控的那台手机上。"""
    wf = workflow([
        {"WFWorkflowActionIdentifier": "is.workflow.actions.speaktext",
         "WFWorkflowActionParameters": {"WFText": _token(OBJ, {"{0, 1}": {"Type": "ExtensionInput"}})}},
        # 不留输出，免得 iOS 弹「允许输出 1 个文本项目？」（上游实测）。
        {"WFWorkflowActionIdentifier": "is.workflow.actions.nothing", "WFWorkflowActionParameters": {}},
    ], 4292093695, 59758)
    wf["WFWorkflowHasShortcutInputVariables"] = True
    return wf


def local_url(port):
    """默认地址：本机 .local 名 + 端口（手机和 Mac 在同一 Wi-Fi 时能直接解析）。"""
    r = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True)
    name = r.stdout.strip()
    if r.returncode != 0 or not name:
        sys.exit("读不到本机名，请用 --url 指定桥接服务地址，如 http://my-mac.local:18800")
    return "http://%s.local:%s" % (name, port)


def sign(unsigned, signed, tries=4):
    """shortcuts sign 偶尔会返回 500，重试几次。"""
    r = None
    for _ in range(tries):
        r = subprocess.run(["shortcuts", "sign", "--mode", "anyone", "-i", unsigned, "-o", signed],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(signed):
            return True, ""
        time.sleep(1.5)
    return False, (r.stdout + r.stderr) if r else ""


def main():
    home = os.environ.get("IPHONE_AGENT_KIT_HOME", os.path.expanduser("~/.config/iphone-agent-kit"))
    p = argparse.ArgumentParser()
    p.add_argument("--url", help="桥接服务地址，如 http://my-mac.local:18800（默认：本机 .local 名 + 配置里的端口）")
    p.add_argument("--out", default="shortcuts")
    p.add_argument("--config", default=os.path.join(home, "config.json"))
    p.add_argument("--no-sign", action="store_true")
    a = p.parse_args()

    try:
        with open(a.config, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:
        sys.exit("读不到配置 %s：%s（先启动一次桥接服务让它生成令牌）" % (a.config, e))
    token = cfg["token"]
    base = (a.url or local_url(cfg.get("port", 18800))).rstrip("/")
    persona = (cfg.get("persona") or {}).get("enabled", True)
    still = "还在做喔，做完我再推给你～" if persona else "还在做，做完会推送给你。"
    os.makedirs(a.out, exist_ok=True)
    print("服务地址：" + base)

    # 只生成一个快捷指令：听写 → 发给桥接服务。不出声、不等结果：「收到」和结果都用 Bark 推送。
    # 叫停靠说话：说「停止」「别弄了」服务会直接停。
    # 其余几个（等结果版、回复助手、手机状态、停止助手、手机朗读）的生成函数保留在上面，需要时再加回这里。
    items = {
        "让手机做事": spoken(base, token, "/task?say=1", 4282601983, 61440),
    }
    for name, wf in items.items():
        unsigned = os.path.join(a.out, name + ".unsigned.shortcut")
        with open(unsigned, "wb") as f:
            plistlib.dump(wf, f)
        if a.no_sign:
            print("已生成（未签名）：" + unsigned)
            continue
        signed = os.path.join(a.out, name + ".shortcut")
        ok, detail = sign(unsigned, signed)
        if not ok:
            print("签名失败 %s：%s" % (name, detail), file=sys.stderr)
            return 1
        os.remove(unsigned)
        print("已生成：" + signed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
