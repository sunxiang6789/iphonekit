#!/usr/bin/env python3
"""可选验收：消耗少量模型用量；真实 CLI + 临时目录 + 假手机 MCP，绝不连接手机。"""
import argparse
from collections import deque
import json
import os
import pathlib
import sys
import tempfile
import threading
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'bridge'))
import bridge as b
from assistant_context import ContextStore, read_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agents', nargs='+', choices=b.AGENTS, default=['dsh', 'claude', 'codex'])
    parser.add_argument('--conversation', action='store_true', help='另测 dsh 提问→原会话续接→记住长期偏好（不连接手机）')
    parser.add_argument('--event-types', action='store_true', help='仅打印 Codex 事件类型和工具名（不打印内容）')
    args = parser.parse_args()
    cfg = b.load_config(write=False)
    with tempfile.TemporaryDirectory(prefix='iak-cli-') as tmp:
        fake = pathlib.Path(tmp, 'fake-phone-mcp')
        fake.write_text('''#!/usr/bin/python3
import json, sys
for line in sys.stdin:
    r = json.loads(line)
    if 'id' not in r: continue
    if r.get('method') == 'tools/list':
        result = {'tools':[{'name':name,'description':desc,'inputSchema':{'type':'object','properties':{}}} for name,desc in [
            ('phone_status','读取手机状态。操作手机前先检查 drivable。'),
            ('phone_elements','读取手机前台 App 可访问控件。'),
            ('phone_shortcut','在手机上按 Home 回主屏幕。')]]}
    elif r.get('method') == 'tools/call':
        result = {'content':[{'type':'text','text':'这是隔离验收的假手机，不能读取或操作手机。'}], 'isError':True}
    else:
        result = {'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'fake-phone','version':'1'}}
    print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}), flush=True)
''')
        fake.chmod(0o700)
        b.DATA_DIR, b.WORK_DIR, b.TASKS_PATH = tmp, os.path.join(tmp, 'work'), os.path.join(tmp, 'tasks.json')
        os.makedirs(b.WORK_DIR)
        cfg = b.deep_merge(cfg, {'iphone_use_mcp': str(fake), 'task_timeout_secs': 60,
                                'routing': {'enabled': False}, 'stop_runner_after_task': False})
        br = b.Bridge.__new__(b.Bridge)
        br.cfg, br.lock = cfg, threading.Lock()
        br.wake, br.finished_cv = threading.Condition(br.lock), threading.Condition(br.lock)
        br.queue, br.tasks, br.current = deque(), [], None
        br.cfg['ack_by_push'] = False
        br.context = ContextStore(tmp)
        br.context.preload()
        observed = []
        if args.event_types:
            original = br._run_codex
            def capture(task, proc, out_file):
                stream = proc.stdout
                def lines():
                    for raw in stream:
                        try:
                            ev = json.loads(raw)
                            item = ev.get('item') or {}
                            observed.append({k:v for k,v in {'type':ev.get('type'),'item_type':item.get('type'),
                                                              'tool':item.get('tool'), 'name':item.get('name'),
                                                              'item_keys':list(item)}.items() if v})
                        except ValueError:
                            pass
                        yield raw
                proc.stdout = lines()
                return original(task, proc, out_file)
            br._run_codex = capture
        failed = False
        for agent in args.agents:
            task = {'id': 'check-' + agent, 'agent': agent, 'mode': 'simple' if agent == 'claude' else None, 'resume': None,
                    'text': '上海现在几点？',
                    'state': 'running', 'result': '', 'session_id': None, 'entry': b.primary_entry(cfg, agent)}
            t0 = time.monotonic()
            try:
                br._attempt(task)
                events = read_trace(tmp, task['id'])
                time_called = any(e.get('tool') in ('kit_time', 'host_system_clock') and
                                  not e.get('is_error') for e in events)
                phone_called = any(e.get('tool','').startswith('phone_') for e in events)
                grounded = bool(task.get('clock_context', {}).get('source')) or time_called
                ok = task['state'] == 'done' and bool(task.get('session_id')) and grounded and not phone_called
                failed |= not ok
                print(json.dumps({'agent': agent, 'ok': ok, 'state': task['state'],
                                  'has_session': bool(task.get('session_id')),
                                  'time_tool_called': time_called,
                                  'phone_tool_called': phone_called,
                                  'system_clock_in_context': bool(task.get('clock_context')),
                                  'elapsed_secs': round(time.monotonic() - t0, 2),
                                  'reply': task['result'] if ok else 'CLI 未成功；本次未连接真实手机',
                                  'failure_reason': '' if ok else b.scrub(task['result'])[:400]}, ensure_ascii=False), flush=True)
            except Exception as e:
                failed = True
                print(json.dumps({'agent': agent, 'ok': False, 'error_type': type(e).__name__}))
        if observed:
            print(json.dumps({'event_types':observed},ensure_ascii=False))
        if args.conversation:
            first = {'id': '11111111', 'agent': 'dsh', 'mode': None, 'resume': None,
                     'text': '帮我整理一句旅行备忘“出门记得带伞”。先保存任务进度并询问我要保存到哪里，先不要操作手机。',
                     'goal': '整理旅行备忘并保存', 'state': 'running', 'result': '', 'session_id': None,
                     'client': 'isolated-check', 'entry': b.primary_entry(cfg, 'dsh')}
            br.tasks.append(first)
            br._attempt(first)
            br._classify_result(first)
            if first['state'] != 'waiting_user' or not first['session_id']:
                print(json.dumps({'conversation_ok': False, 'stage': 'question', 'state': first['state']}))
                return 1
            out = br.submit('以后旅行备忘都放苹果备忘录。这次只记住这个偏好，先别往手机保存。', client='isolated-check')
            second = br._find(out['id'])
            br._attempt(second)
            same_session = second['session_id'] == first['session_id']
            profile = pathlib.Path(tmp, 'profile.md').read_text() if pathlib.Path(tmp, 'profile.md').exists() else ''
            ok = same_session and second['state'] == 'done' and '苹果备忘录' in profile
            failed |= not ok
            print(json.dumps({'conversation_ok': ok, 'same_session': same_session,
                              'preference_saved': '苹果备忘录' in profile, 'state': second['state']}, ensure_ascii=False))
        return int(failed)


if __name__ == '__main__':
    sys.exit(main())
