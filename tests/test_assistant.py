"""离线验收：临时目录、假 CLI/MCP；绝不连接真实手机、模型或 Bark。"""
import copy
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections import deque
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bridge"))
import bridge as b
from assistant_context import ContextStore, atomic_text, read_text, read_trace, record_call
from assistant_mcp import Gateway, validate_public_url


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        os.makedirs(os.path.join(self.home, "work"))
        self.paths = patch.multiple(b, DATA_DIR=self.home, WORK_DIR=os.path.join(self.home, "work"),
                                    TASKS_PATH=os.path.join(self.home, "tasks.json"),
                                    RUNNER_MARK=os.path.join(self.home, "stopped"),
                                    RUNNER_STARTED=os.path.join(self.home, "started"))
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.cfg = b.deep_merge(b.DEFAULT_CONFIG, {"ack_by_push": False, "routing": {"enabled": False},
                                                  "experience": {"review_enabled": False}})
        # 不构造 Bridge：正式构造会启动工作线程。
        self.br = b.Bridge.__new__(b.Bridge)
        self.br.cfg = self.cfg
        self.br.lock = threading.Lock()
        self.br.wake = threading.Condition(self.br.lock)
        self.br.finished_cv = threading.Condition(self.br.lock)
        self.br.resume_lock = threading.Lock()
        self.br.warm_until = self.br.last_task_at = 0
        self.br.current = self.br.proc = None
        self.br.queue, self.br.tasks = deque(), []
        self.br.context = ContextStore(self.home)
        self.br.context.preload()

    def waiting(self, ident="11111111", client="client", session="native-session", state="waiting_user"):
        task = {"id": ident, "text": "做旅行攻略", "goal": "做旅行攻略", "agent": "dsh", "mode": None,
                "session_id": session, "state": state, "client": client, "result": "放哪里？",
                "question": "放哪里？", "checkpoint": {"completed": ["已整理攻略"], "remaining": ["保存"]},
                "entry": {"agent": "dsh", "model": "provider/model", "effort": "low"}}
        self.br.tasks.append(task)
        return task

    def test_same_shortcut_resumes_and_keeps_model(self):
        parent = self.waiting()
        out = self.br.submit("备忘录，以后都放那里", client="client")
        task = self.br._find(out["id"])
        self.assertEqual(task["resume"], "native-session")
        self.assertEqual(task["entry"], parent["entry"])
        self.assertEqual(task["recovery"]["checkpoint"]["completed"], ["已整理攻略"])
        self.assertEqual(parent["state"], "answered")

    def test_explicit_new_and_other_client_do_not_resume(self):
        self.waiting()
        out = self.br.submit("新任务：现在几点", client="client")
        self.assertFalse(out["resumed"])
        self.assertEqual(self.br.tasks[0]["state"], "waiting_user")
        self.assertFalse(self.br.submit("备忘录", client="other")["resumed"])

    def test_ambiguous_reply_and_explicit_id(self):
        self.waiting()
        self.waiting("22222222")
        with self.assertRaises(ValueError):
            self.br.submit("放备忘录", client="client")
        out = self.br.submit("回复 22222222 放备忘录", client="client")
        self.assertEqual(self.br._find(out["id"])["parent_id"], "22222222")

    def test_lost_session_still_carries_checkpoint(self):
        self.waiting(session=None)
        out = self.br.submit("备忘录", client="client")
        task = self.br._find(out["id"])
        prompt = self.br._prompt(task)
        self.assertFalse(task["resume"])
        self.assertIn("已整理攻略", prompt)
        self.assertIn("做旅行攻略", prompt)

    def test_question_marks_survive_clean_reply_and_push(self):
        for mark, state in ((b.WAIT_MARK, "waiting_user"), (b.UNLOCK_MARK, "waiting_unlock"),
                            (b.CONFIRM_MARK, "needs_confirm")):
            task = {"id": "33333333", "state": "done", "agent": "dsh",
                    "result": b.clean_reply(mark + "\n\n请回答这个问题")}
            self.br._classify_result(task)
            self.assertEqual(task["state"], state)
            with patch.object(b, "bark_push") as push:
                self.br._notify(task)
                self.assertEqual(push.call_args[0][2], "请回答这个问题")

    def test_normal_question_does_not_wait_for_or_touch_phone(self):
        task = {"id": "33333333", "state": "done"}
        with patch.object(b, "phone_state") as status, patch.object(b, "release_phone") as release:
            self.br._finish_phone(task)
            status.assert_not_called()
            release.assert_not_called()

    def test_cleanup_respects_foreign_owner_and_human(self):
        atomic_text(b.RUNNER_STARTED, "1")
        with patch.object(b, "phone_state", return_value={"owner": "another"}), patch.object(b, "stop_runner") as stop:
            self.br._finish_phone({"id": "33333333", "state": "done"})
            stop.assert_not_called()
        with patch.object(b, "phone_state", return_value={"human_handoff": True}), patch.object(b, "stop_runner") as stop:
            self.br._finish_phone({"id": "33333333", "state": "done"})
            stop.assert_not_called()
            self.assertFalse(os.path.exists(b.RUNNER_STARTED))

    def test_question_after_wake_closes_only_own_runner_without_home(self):
        atomic_text(b.RUNNER_STARTED, "1")
        with patch.object(b, "phone_state", return_value={"owner": "bridge", "drivable": True}), \
                patch.object(b, "release_phone") as release, patch.object(b, "stop_runner") as stop:
            self.br._finish_phone({"id": "33333333", "state": "done"})
            release.assert_called_once()
            stop.assert_called_once()

    def test_delayed_wake_cannot_restart_runner_after_fast_answer(self):
        woke_at = time.time() - 1
        self.br._finish_phone({"id": "33333333", "state": "done"})
        with patch.object(b, "resume_runner") as resume:
            self.br._warm_worker(woke_at)
            resume.assert_not_called()

    def test_lock_is_reported_without_90_second_wait_or_reconnect(self):
        atomic_text(b.RUNNER_MARK, "1")
        with patch.object(b, "phone_state", return_value={"locked": True}), patch.object(b, "daemon_call") as call:
            self.assertFalse(b.resume_runner(self.cfg))
            call.assert_not_called()

    def test_whole_summary_in_all_agents_and_resume_prompt(self):
        store = self.br.context
        store.write_summary("候选：先确认界面，已知步骤一次批量完成。", store.preload()["revision"])
        self.waiting()
        task = self.br._find(self.br.submit("备忘录", client="client")["id"])
        for agent in b.AGENTS:
            task = dict(task, agent=agent)
            with patch.object(b, "find_codex", return_value="fake-codex"), \
                    patch.object(b, "find_claude", return_value="fake-claude"), \
                    patch.object(b, "find_dsh", return_value="fake-dsh"), \
                    patch.object(b, "find_iphone_use_mcp", return_value="fake-phone"):
                command = self.br._command(task, "/tmp/fake-output")
            self.assertIn("候选：先确认界面", " ".join(command))
            self.assertIn("已整理攻略", " ".join(command))
            if agent == "dsh":
                overlay = read_text(task["_overlay"])
                self.assertIn("assistant_mcp.py", overlay)
                self.assertIn("serverName: iphone-use", overlay)
                self.assertIn("transport: stdio", overlay)
                self.assertLess(command.index("--patch"), command.index("--json"))
            else:
                self.assertIn("assistant_mcp.py", " ".join(command))

    def test_shared_writes_are_atomic_and_stale_revision_refused(self):
        a, c = ContextStore(self.home), ContextStore(self.home)
        rev = a.preload()["revision"]
        a.write_summary("经验A", rev)
        with self.assertRaises(ValueError):
            c.write_summary("经验B", rev)
        with self.assertRaises(ValueError):
            a.write_summary("x" * 1600, a.preload()["revision"])
        self.assertEqual(c.preload()["summary"], "经验A")
        self.assertEqual(os.stat(a.summary_path).st_mode & 0o777, 0o600)

    def test_preference_updates_same_key_and_requires_real_user_quote(self):
        s = self.br.context
        atomic_text(os.path.join(self.home, "profile.md"), "- 攻略保存位置：旧位置\n- 其他习惯：保留\n")
        s.set_preference("攻略保存位置", "苹果备忘录", "以后都放备忘录", "嗯，以后都放备忘录")
        s.set_preference("攻略保存位置", "聊天回复", "以后发聊天", "以后发聊天")
        text = read_text(os.path.join(self.home, "profile.md"))
        self.assertEqual(text.count("攻略保存位置"), 1)
        self.assertIn("其他习惯：保留", text)
        with self.assertRaises(ValueError):
            s.set_preference("攻略保存位置", "猜测位置", "我猜的", "以后发聊天")

    def test_trace_omits_typed_messages_and_page_contents(self):
        record_call(self.home, "12345678", "phone_run_steps",
                    {"steps": [{"type": "text", "text": "private message"}, {"type": "tap", "label": "private name"}]},
                    {"content": [{"type": "text", "text": json.dumps({"ok": True, "elements": ["private tree"]})}]}, .2)
        text = json.dumps(read_trace(self.home, "12345678"))
        self.assertNotIn("private", text)
        self.assertIn('"ok": true', text)

    def test_background_review_has_evidence_and_does_not_invent_verification(self):
        self.br.cfg["experience"]["review_enabled"] = True
        task = {"id": "12345678", "agent": "dsh", "state": "done", "started": 10, "finished": 11}
        record_call(self.home, task["id"], "phone_scroll", {"dy": 400}, {"isError": True}, .1)
        fake = lambda *args: json.dumps({"mistakes": ["滚动失败"], "redundant": [], "correct_steps": [],
                                        "evidence_refs": [0], "summary": "候选：失败后先核对当前页面。"})
        with patch.dict(b.ACK_RUNNERS, {"dsh": fake}):
            self.br._review(task)
        report = json.loads(read_text(os.path.join(self.home, "experience", "reviews", task["id"] + ".json")))
        self.assertEqual(report["verification"], "not_verified")
        self.assertEqual(report["review_state"], "candidate")
        self.assertIn("候选", self.br.context.snapshot()["summary"])

    def test_stale_native_session_recovers_without_repeating_phone_actions(self):
        task = {"id": "12345678", "agent": "dsh", "mode": None, "resume": "lost-session", "state": "running",
                "result": "", "recovery": {"checkpoint": {"completed": ["已保存"]}}}
        count = []
        def fake_run(t):
            count.append(t.get("resume"))
            t.update(state="failed" if t.get("resume") else "done", result="session not found" if t.get("resume") else "继续完成")
        with patch.object(self.br, "_run", side_effect=fake_run):
            self.br._attempt(task)
        self.assertEqual(count, ["lost-session", None])
        self.assertEqual(task["state"], "done")
        record_call(self.home, "22222222", "phone_tap", {"x": 1, "y": 1}, {}, .1)
        task.update(id="22222222", resume="lost-session", state="running")
        count.clear()
        with patch.object(self.br, "_run", side_effect=fake_run):
            self.br._attempt(task)
        self.assertEqual(len(count), 1)

    def test_model_only_tools_do_not_start_phone(self):
        g = Gateway(self.home, command="")
        with patch.object(g.phone, "request", side_effect=AssertionError("phone must stay unused")):
            result = g.dispatch("tools/call", {"name": "kit_time", "arguments": {"timezone": "Asia/Shanghai"}})
            self.assertIn("+08:00", result["content"][0]["text"])

    def test_other_confirmation_blocks_phone_without_reconnect(self):
        atomic_text(os.path.join(self.home, "tasks.json"), '[{"state":"needs_confirm"}]')
        g = Gateway(self.home, task_id="12345678", command="")
        with patch.object(g.phone, "request", side_effect=AssertionError("no phone")):
            response = g.dispatch("tools/call", {"name": "phone_tap", "arguments": {"x": 1, "y": 2}})
        self.assertTrue(response["isError"])

    def test_public_web_tool_rejects_private_network_and_credentials(self):
        with self.assertRaises(ValueError):
            validate_public_url("http://user:password@example.com")
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValueError):
                validate_public_url("https://example.com")

    def test_stdio_gateway_shared_read_write_without_phone(self):
        env = dict(os.environ, IPHONE_AGENT_KIT_HOME=self.home, IAK_PHONE_MCP="")
        script = str(pathlib.Path(__file__).resolve().parents[1] / "bridge" / "assistant_mcp.py")
        with subprocess.Popen([sys.executable, script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, env=env) as proc:
            def request(ident, method, params):
                proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": ident, "method": method, "params": params}) + "\n")
                proc.stdin.flush()
                return json.loads(proc.stdout.readline())["result"]
            request(1, "initialize", {"protocolVersion": "2024-11-05"})
            tools = request(2, "tools/list", {})["tools"]
            self.assertIn("kit_experience_write", [t["name"] for t in tools])
            ctx = json.loads(request(3, "tools/call", {"name": "kit_context_read"})["content"][0]["text"])
            request(4, "tools/call", {"name": "kit_experience_write", "arguments": {"summary": "候选：批量执行", "revision": ctx["revision"]}})
            self.assertEqual(ContextStore(self.home).preload()["summary"], "候选：批量执行")
            proc.stdin.close()
            proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
