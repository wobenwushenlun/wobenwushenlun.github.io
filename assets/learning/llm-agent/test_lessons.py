"""Offline control/protocol tests. No SDK import, network calls, or paid requests."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ch01_client import summarize
from ch02_loop import AgentState, run
from ch03_tools import dispatch, execute, offline_ask, read_allowed, run_agent


def tool_call(name="read_file", args=None, call_id="test_1"):
    return {"type": "tool_use", "id": call_id, "name": name,
            "input": {"path": "pricing.py"} if args is None else args}


def tool_response(*calls, reason="tool_use"):
    return {"stop_reason": reason, "content": list(calls)}


def final_response(text="Done"):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


class ClientTests(unittest.TestCase):
    def test_extract_text_blocks_only(self):
        message = {"content": [{"type": "text", "text": "A"}, tool_call(),
                               {"type": "text", "text": "B"}],
                   "stop_reason": "tool_use", "usage": {"input_tokens": 3}}
        self.assertEqual(summarize(message), {
            "text": "AB", "stop_reason": "tool_use", "usage": {"input_tokens": 3}})

    def test_truncation_is_preserved(self):
        self.assertEqual(summarize({"content": [], "stop_reason": "max_tokens"})["stop_reason"], "max_tokens")


class LoopTests(unittest.TestCase):
    def test_normal(self):
        state = run("Explain")
        self.assertEqual((state.status, state.steps, len(state.history)), ("finished", 3, 2))

    def test_finish_uses_budget(self):
        state = run("Explain", max_steps=2)
        self.assertEqual((state.status, state.steps, state.answer), ("step_limit", 2, None))

    def test_repeating_policy_stops(self):
        state = run("Explain", lambda s: {"name": "inspect_tests"}, max_steps=4)
        self.assertEqual((state.status, state.steps), ("step_limit", 4))

    def test_unknown_action_is_an_observation(self):
        state = run("Explain", lambda s: {"name": "not_registered"}, max_steps=1)
        self.assertFalse(state.history[0]["observation"]["ok"])

    def test_malformed_action(self):
        for action in (None, "finish", {}, {"name": 3}, {"name": "finish"}, {"name": "finish", "answer": ""}):
            with self.subTest(action=action):
                self.assertEqual(run("Explain", lambda s: action).status, "invalid_action")

    def test_history_is_not_shared(self):
        a, b = AgentState("A"), AgentState("B")
        a.history.append({"observation": "private to A"})
        self.assertEqual(b.history, [])

    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            run("Explain", max_steps=0)


class ToolTests(unittest.TestCase):
    def test_list_and_read(self):
        self.assertEqual(len(execute("list_files", {})), 3)
        self.assertIn("price * discount", read_allowed("pricing.py"))

    def test_search_has_line_numbers(self):
        result = execute("search_code", {"query": "return price"})
        self.assertEqual(result["hits"][0]["path"], "pricing.py")
        self.assertIsInstance(result["hits"][0]["line"], int)

    def test_search_is_literal(self):
        self.assertEqual(execute("search_code", {"query": ".*"})["hits"], [])

    def test_bad_arguments(self):
        cases = [("read_file", {}), ("read_file", {"path": 3}),
                 ("read_file", {"path": "pricing.py", "extra": True}),
                 ("list_files", {"extra": True}), ("search_code", {"query": ""}),
                 ("search_code", {"query": "x" * 81}), ("read_file", [])]
        for name, args in cases:
            with self.subTest(name=name, args=args):
                with self.assertRaises(ValueError):
                    execute(name, args)

    def test_denied_paths(self):
        for path in ("../secret.txt", "C:/Windows/win.ini", ".env", "fixtures/pricing.py"):
            with self.subTest(path=path):
                self.assertTrue(dispatch(tool_call(args={"path": path}))["is_error"])

    def test_unknown_tool_keeps_id(self):
        result = dispatch(tool_call(name="run_shell", args={}, call_id="denied"))
        self.assertEqual(result["tool_use_id"], "denied")
        self.assertTrue(result["is_error"])

    def test_missing_file_returns_error_without_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp, patch("ch03_tools.ROOT", Path(temp)):
            result = dispatch(tool_call())
            self.assertTrue(result["is_error"])
            self.assertNotIn(temp, result["content"])

    def test_resolved_path_escape_is_denied(self):
        # Simulate a symlink resolution without Windows symlink privileges.
        root = Path(__file__).resolve().parent
        outside = root.parent / "outside.txt"
        with patch("ch03_tools.Path.resolve", side_effect=[root, outside]):
            with self.assertRaises(ValueError):
                read_allowed("pricing.py")

    def test_oversized_read_is_denied(self):
        with patch("ch03_tools.MAX_FILE_BYTES", 4):
            self.assertTrue(dispatch(tool_call())["is_error"])


class ToolLoopTests(unittest.TestCase):
    def test_offline_demo(self):
        result = run_agent(offline_ask, "Explain")
        self.assertEqual((result["status"], result["tool_calls"], len(result["trace"])), ("finished", 4, 3))
        self.assertEqual(result["usage"], {"input_tokens": 0, "output_tokens": 0})

    def test_multi_call_pairing_and_error(self):
        snapshots = []
        responses = iter([tool_response(tool_call(call_id="good"),
                                       tool_call(args={"path": "bad"}, call_id="bad")), final_response()])

        def ask(messages):
            snapshots.append(copy.deepcopy(messages))
            return next(responses)

        result = run_agent(ask, "Explain")
        prior, following = snapshots[1][-2:]
        self.assertEqual(prior["role"], "assistant")
        self.assertEqual(following["role"], "user")
        self.assertEqual([b["tool_use_id"] for b in following["content"]], ["good", "bad"])
        self.assertTrue(following["content"][1]["is_error"])
        self.assertEqual(result["tool_calls"], 2)

    def test_round_limit(self):
        result = run_agent(lambda messages: tool_response(tool_call()), "Explain", max_rounds=2)
        self.assertEqual((result["status"], result["tool_calls"]), ("round_limit", 2))

    def test_tool_limit_rejects_whole_batch(self):
        response = tool_response(tool_call(call_id="a"), tool_call(call_id="b"))
        with patch("ch03_tools.dispatch") as execute_mock:
            result = run_agent(lambda m: response, "Explain", max_tool_calls=1)
        execute_mock.assert_not_called()
        self.assertEqual((result["status"], result["tool_calls"]), ("tool_limit", 0))

    def test_truncated_response_never_executes(self):
        with patch("ch03_tools.dispatch") as execute_mock:
            result = run_agent(lambda m: tool_response(tool_call(), reason="max_tokens"), "Explain")
        execute_mock.assert_not_called()
        self.assertEqual(result["status"], "stopped:max_tokens")

    def test_unsupported_stop_reason(self):
        for reason in ("refusal", "pause_turn", "unknown"):
            with self.subTest(reason=reason):
                result = run_agent(lambda m: tool_response(reason=reason), "Explain")
                self.assertEqual(result["status"], "stopped:" + reason)

    def test_invalid_protocol(self):
        cases = [tool_response(), tool_response(tool_call(), tool_call()),
                 tool_response({"type": "tool_use", "id": None, "name": "read_file", "input": {}}),
                 final_response(""), tool_response(tool_call(), reason="end_turn")]
        for response in cases:
            with self.subTest(response=response):
                self.assertEqual(run_agent(lambda m: response, "Explain")["status"], "protocol_error")

    def test_usage_aggregation(self):
        first, last = tool_response(tool_call()), final_response()
        first["usage"] = {"input_tokens": 10, "output_tokens": 3}
        last["usage"] = {"input_tokens": 20, "output_tokens": 7}
        responses = iter([first, last])
        result = run_agent(lambda m: next(responses), "Explain")
        self.assertEqual(result["usage"], {"input_tokens": 30, "output_tokens": 10})

    def test_bad_budgets(self):
        with self.assertRaises(ValueError):
            run_agent(offline_ask, "Explain", max_rounds=0)
        with self.assertRaises(ValueError):
            run_agent(offline_ask, "Explain", max_tool_calls=-1)


if __name__ == "__main__":
    unittest.main()
