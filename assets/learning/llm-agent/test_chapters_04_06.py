"""Offline regression tests for evidence baselines, DAG repair and context budgets."""
import json
import unittest
from unittest.mock import patch

from ch04_react import demo_answer, grade, run_case, scripted_react
from ch05_planning import Task, initial_plan, run_plan, validate_plan
from ch06_context import build_context, make_chunks, verify_manifest


class ReactTests(unittest.TestCase):
    def test_three_offline_modes_are_labelled(self):
        rows = [run_case(mode) for mode in ("blind", "provided", "react")]
        self.assertEqual([row["rounds"] for row in rows], [1, 1, 4])
        self.assertEqual([row["tool_calls"] for row in rows], [0, 0, 3])
        self.assertEqual([row["grade"]["correct"] for row in rows], [False, True, True])
        self.assertTrue(all(row["usage"] is None and row["execution"] == "scripted_offline" for row in rows))

    def test_rejects_missing_evidence_and_false_test_claim(self):
        answer = demo_answer(True)
        self.assertFalse(grade(json.dumps(answer), {"pricing.py"})["correct"])
        answer["verified_by_tests"] = True
        self.assertFalse(grade(json.dumps(answer), set(answer["evidence"]))["correct"])

    def test_schema_rejects_bad_json_and_bad_types(self):
        for text in ("not JSON", "[]", "null", "{}"):
            self.assertFalse(grade(text, set())["schema_ok"])
        for key, value in (("expected", True), ("evidence", "README.md"), ("formula", 123), ("verified_by_tests", 0)):
            answer = demo_answer(True)
            answer[key] = value
            self.assertFalse(grade(json.dumps(answer), set())["schema_ok"])

    def test_format_sensitive_rubric_is_explicit(self):
        answer = demo_answer(True)
        answer["formula"] = "price - price * discount"
        self.assertFalse(grade(json.dumps(answer), set(answer["evidence"]))["correct"])

    def test_tool_failure_prevents_scripted_diagnosis(self):
        messages = [{"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "read_file", "input": {"path": "README.md"}}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "is_error": True, "content": "missing"}]}]
        answer = json.loads(scripted_react(messages)["content"][0]["text"])
        self.assertIsNone(answer["expected"])

    def test_real_client_adapter_without_network(self):
        class Response:
            def model_dump(self, **kwargs):
                return {"content": [{"type": "text", "text": json.dumps(demo_answer(True))}],
                        "stop_reason": "end_turn", "usage": {"input_tokens": 11, "output_tokens": 7}}
        class FakeClient:
            def __init__(self):
                self.messages = self
                self.requests = []
            def create(self, **kwargs):
                self.requests.append(kwargs)
                return Response()
        client = FakeClient()
        row = run_case("provided", client, "fake-test-model")
        self.assertNotIn("tools", client.requests[0])
        self.assertIn("FILE pricing.py", client.requests[0]["messages"][0]["content"])
        self.assertEqual(row["usage"]["input_tokens"], 11)
        self.assertEqual(row["model"], "fake-test-model")


class PlanningTests(unittest.TestCase):
    def test_normal(self):
        state = run_plan(initial_plan())
        self.assertEqual((state.status, state.attempts, state.revisions), ("completed", 3, 0))

    def test_repair_retains_completed_work(self):
        state = run_plan(initial_plan(True))
        self.assertEqual((state.status, state.attempts, state.revisions), ("completed", 4, 1))
        self.assertEqual(len([x for x in state.trace if x.get("task") == "spec"]), 1)

    def test_no_repair(self):
        state = run_plan(initial_plan(True), repair=None)
        self.assertEqual((state.status, state.attempts, list(state.done)), ("repair_limit", 2, ["spec"]))

    def test_total_budget_survives_revision(self):
        state = run_plan(initial_plan(True), max_attempts=2)
        self.assertEqual((state.status, state.attempts, state.revisions), ("attempt_limit", 2, 1))

    def test_repeated_failure_has_finite_revisions(self):
        state = run_plan(initial_plan(True), repair=lambda tasks, failed, error: tasks)
        self.assertEqual((state.status, state.attempts, state.revisions), ("repair_limit", 3, 1))

    def test_invalid_plans_are_rejected_before_execution(self):
        cases = [[], [Task("a", "read_file", {}), Task("a", "read_file", {})],
                 [Task("a", "read_file", {}, ("b",))],
                 [Task("a", "read_file", {}, ("a",))],
                 [Task("a", "read_file", {}, ("b",)), Task("b", "read_file", {}, ("a",))],
                 [Task("a", "run_shell", {})]]
        for tasks in cases:
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                validate_plan(tasks)

    def test_revision_cannot_change_done_or_drop_tasks(self):
        def change_done(tasks, failed, error):
            tasks[0].args["path"] = "pricing.py"
            return tasks
        for repair in (change_done, lambda tasks, failed, error: tasks[:1]):
            state = run_plan(initial_plan(True), repair=repair)
            self.assertEqual(state.status, "invalid_revision")

    def test_future_dependencies_execute_in_order(self):
        tasks = [Task("second", "list_files", {}, ("first",)), Task("first", "list_files", {})]
        calls = []
        state = run_plan(tasks, executor=lambda name, args: calls.append(name))
        self.assertEqual(list(state.done), ["first", "second"])

    def test_input_plan_is_not_mutated(self):
        plan = initial_plan(True)
        run_plan(plan)
        self.assertEqual(plan[1].args["path"], "missing.py")


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.docs = {"a.py": "def price():\n    return 80\n", "b.md": "discount means money off\n"}

    def test_budget_includes_metadata(self):
        for budget in (0, 10, 180, 500):
            result = build_context("price discount", self.docs, budget)
            self.assertLessEqual(len(result["context"]), budget)
            self.assertEqual(result["used"], len(result["context"]))

    def test_zero_budget_preserves_drop_reason(self):
        result = build_context("price", self.docs, 0)
        self.assertEqual(result["selected"], [])
        self.assertIn("budget", [row["reason"] for row in result["dropped"]])

    def test_no_overlap_does_not_fill_with_noise(self):
        result = build_context("nonexistent", self.docs, 3000)
        self.assertEqual(result["context"], "")
        self.assertTrue(all(x["reason"] == "no_term_overlap" for x in result["dropped"]))

    def test_pure_chinese_query_is_not_silently_semantic(self):
        self.assertEqual(build_context("折扣价格", self.docs)["selected"], [])

    def test_stable_sort_independent_of_input_order(self):
        first = build_context("price discount", self.docs)
        second = build_context("price discount", dict(reversed(list(self.docs.items()))))
        self.assertEqual(first, second)

    def test_line_boundaries(self):
        chunks = make_chunks({"x": "a\nb\nc\nd\ne\n"}, 2)
        self.assertEqual([(x.start, x.end) for x in chunks], [(1, 2), (3, 4), (5, 5)])
        self.assertEqual(chunks[-1].text, "e")

    def test_stale_and_missing_evidence(self):
        chosen = build_context("price discount", self.docs)["selected"]
        self.assertEqual(verify_manifest(chosen, self.docs), [])
        changed = dict(self.docs)
        changed["a.py"] += "# edited"
        self.assertEqual(verify_manifest(chosen, changed), ["a.py"])
        self.assertEqual(verify_manifest(chosen, {}), ["a.py", "b.md"])

    def test_large_high_score_chunk_does_not_block_small_one(self):
        docs = {"huge": "price discount " * 500, "tiny": "price"}
        result = build_context("price discount", docs, 250)
        self.assertEqual([x["path"] for x in result["selected"]], ["tiny"])

    def test_invalid_budget_and_chunk_size(self):
        with self.assertRaises(ValueError):
            build_context("price", self.docs, -1)
        with self.assertRaises(ValueError):
            make_chunks(self.docs, 0)


if __name__ == "__main__":
    unittest.main()
