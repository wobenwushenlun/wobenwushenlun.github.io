"""Offline memory, feedback and role-protocol tests; no LLM or shell execution."""
from dataclasses import replace
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ch07_memory import Memory, MemoryStore, demo
from ch08_reflection import PUBLIC_CASES, audit_frozen, evaluate, run_revision
from ch09_multi_agent import Coordinator, Report, TASK, run_team


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(":memory:")
        self.addCleanup(self.store.close)
        self.fact = Memory("fact", "project", "discount.meaning", "semantic",
                           "discount means fraction off", "spec", "v1", 20, True)

    def query(self, **kwargs):
        return self.store.retrieve("project", "discount", kwargs.pop("revisions", {"spec": "v1"}),
                                   kwargs.pop("now", 10), **kwargs)

    def test_persists_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite"
            first = MemoryStore(path)
            try:
                first.put(self.fact)
            finally:
                first.close()
            second = MemoryStore(path)
            try:
                result = second.retrieve("project", "discount", {"spec": "v1"}, 10)
                self.assertEqual(result["selected"][0]["id"], "fact")
            finally:
                second.close()

    def test_scope_filter_has_no_foreign_diagnostics(self):
        self.store.put(replace(self.fact, id="foreign", scope="other"))
        self.assertEqual(self.query()["selected"], [])
        self.assertEqual(self.query()["excluded"], [])

    def test_parameterized_scope(self):
        self.store.put(self.fact)
        result = self.store.retrieve("' OR 1=1 --", "discount", {"spec": "v1"}, 10)
        self.assertEqual(result["selected"], [])

    def test_unverified_expired_and_stale(self):
        cases = [(replace(self.fact, verified=False), "unverified"),
                 (replace(self.fact, expires_at=10), "expired"),
                 (replace(self.fact, revision="v0"), "stale_source")]
        for i, (record, reason) in enumerate(cases):
            self.store.put(replace(record, id=str(i)))
        self.assertEqual({r["reason"] for r in self.query()["excluded"]},
                         {"unverified", "expired", "stale_source"})

    def test_missing_source_is_not_valid(self):
        self.store.put(self.fact)
        self.assertEqual(self.query(revisions={})["status"], "empty")

    def test_conflicting_key_is_quarantined(self):
        self.store.put(self.fact)
        self.store.put(replace(self.fact, id="other", text="discount means fraction payable"))
        result = self.query()
        self.assertEqual(result["status"], "needs_resolution")
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["conflicts"], ["discount.meaning"])

    def test_duplicate_text_is_not_extra_evidence(self):
        self.store.put(self.fact)
        self.store.put(replace(self.fact, id="same"))
        result = self.query()
        self.assertEqual(len(result["selected"]), 1)
        self.assertEqual(result["conflicts"], [])
        self.assertIn("duplicate", [r["reason"] for r in result["excluded"]])

    def test_deactivate_preserves_row_but_excludes_retrieval(self):
        self.store.put(self.fact)
        self.store.deactivate("fact")
        self.assertEqual(self.query()["status"], "empty")
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 1)

    def test_budget_counts_full_serialized_memory(self):
        self.store.put(self.fact)
        for budget in (0, 10, 900):
            result = self.query(budget_chars=budget)
            self.assertEqual(result["used_chars"], len(result["context"]))
            self.assertLessEqual(result["used_chars"], budget)

    def test_top_k_and_empty_query(self):
        self.store.put(self.fact)
        self.store.put(replace(self.fact, id="second", key="discount.other"))
        self.assertEqual(len(self.query(top_k=1)["selected"]), 1)
        self.assertEqual(self.store.retrieve("project", "", {"spec": "v1"}, 10)["selected"], [])

    def test_duplicate_id_and_invalid_record(self):
        self.store.put(self.fact)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.put(self.fact)
        for record in (replace(self.fact, id=""), replace(self.fact, verified="yes"),
                       replace(self.fact, kind="unknown"), replace(self.fact, text="x" * 2001)):
            with self.assertRaises(ValueError):
                self.store.put(record)

    def test_demo_scenarios(self):
        expected = {"normal": "retrieved", "conflict": "needs_resolution", "expired": "empty",
                    "stale": "empty", "forgotten": "empty"}
        for scenario, status in expected.items():
            with self.subTest(scenario=scenario):
                self.assertEqual(demo(scenario)["status"], status)


class ReflectionTests(unittest.TestCase):
    def test_repair(self):
        result = run_revision()
        self.assertEqual((result["status"], result["proposals"], result["evaluations"]), ("public_passed", 2, 2))
        self.assertFalse(result["reflections"][0]["verified"])
        self.assertEqual(audit_frozen(result)["status"], "passed")

    def test_stagnation_counts_proposal(self):
        result = run_revision(lambda attempt, memories: "saved_amount")
        self.assertEqual((result["status"], result["proposals"], result["evaluations"]), ("stalled", 2, 1))

    def test_one_attempt_cannot_be_reset_by_reflection(self):
        result = run_revision(max_attempts=1)
        self.assertEqual(result["status"], "attempt_limit")
        self.assertEqual(result["reflections"], [])
        self.assertEqual(audit_frozen(result)["status"], "not_run")

    def test_overfit_public_pass_does_not_imply_audit_pass(self):
        result = run_revision(lambda attempt, memories: "constant_80", cases=PUBLIC_CASES[:1])
        before = repr(result)
        audit = audit_frozen(result)
        self.assertEqual(result["status"], "public_passed")
        self.assertEqual(audit["status"], "failed")
        self.assertFalse(audit["returned_to_actor"])
        self.assertEqual(repr(result), before)

    def test_empty_suite_and_unknown_candidate_rejected(self):
        with self.assertRaises(ValueError):
            evaluate("payable", ())
        with self.assertRaises(ValueError):
            evaluate("__import__('os')")
        self.assertEqual(run_revision(lambda attempt, memories: ["payable"])["status"], "invalid_candidate")

    def test_actor_cannot_mutate_stored_feedback(self):
        def actor(attempt, memories):
            if memories:
                memories[0]["evidence"].clear()
                return "payable"
            return "saved_amount"
        self.assertTrue(run_revision(actor)["reflections"][0]["evidence"])

    def test_decimal_and_extreme_discounts(self):
        self.assertTrue(evaluate("payable", (("0.10", "0.2", "0.08"), ("10", "1", "0")))["passed"])
        self.assertFalse(evaluate("saved_amount")["passed"])


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.versions = {"README.md": "s", "pricing.py": "c", "test_pricing.py": "t"}
        self.report = Report(TASK, 1, "spec_reader", {"README.md": "s"}, "payable")

    def test_normal_and_failure_scenarios(self):
        for scenario, expected in (("normal", "verified_proposal"), ("conflict", "needs_resolution"),
                                   ("stale", "incomplete"), ("missing", "incomplete"),
                                   ("unanimous_wrong", "verification_failed")):
            with self.subTest(scenario=scenario):
                self.assertEqual(run_team(scenario)["status"], expected)

    def test_task_and_revision(self):
        for bad in (replace(self.report, task_id="other"), replace(self.report, revision=0)):
            coordinator = Coordinator(self.versions)
            self.assertEqual(coordinator.submit("spec_reader", bad), "wrong_task_or_revision")

    def test_actual_sender_checked(self):
        coordinator = Coordinator(self.versions)
        self.assertEqual(coordinator.submit("coder", self.report), "wrong_sender")
        self.assertEqual(coordinator.submit("outsider", self.report), "wrong_sender")

    def test_duplicate_not_a_vote_and_counts_toward_budget(self):
        coordinator = Coordinator(self.versions, max_messages=2)
        self.assertEqual(coordinator.submit("spec_reader", self.report), "accepted")
        self.assertEqual(coordinator.submit("spec_reader", self.report), "duplicate")
        self.assertEqual(coordinator.submit("spec_reader", self.report), "message_limit")
        self.assertEqual(coordinator.received, 2)
        self.assertEqual(len(coordinator.reports), 1)

    def test_wrong_evidence_scope_and_stale_version(self):
        cases = [({"pricing.py": "c"}, "invalid_evidence_scope"),
                 ({"README.md": "old"}, "stale_evidence"), ({}, "invalid_evidence_scope")]
        for evidence, expected in cases:
            coordinator = Coordinator(self.versions)
            self.assertEqual(coordinator.submit("spec_reader", replace(self.report, evidence=evidence)), expected)

    def test_report_copied_after_acceptance(self):
        coordinator = Coordinator(self.versions)
        coordinator.submit("spec_reader", self.report)
        self.report.evidence["README.md"] = "changed"
        self.assertEqual(coordinator.reports["spec_reader"].evidence["README.md"], "s")

    def test_packet_scope_and_budget(self):
        result = run_team(max_messages=2)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["missing"], ["reviewer"])
        self.assertEqual([p["source_names"] for p in result["packets"]],
                         [["README.md"], ["pricing.py"], ["test_pricing.py"]])

    def test_unregistered_candidate_cannot_be_accepted(self):
        coordinator = Coordinator(self.versions)
        self.assertEqual(coordinator.submit("spec_reader", replace(self.report, candidate="run_shell")), "invalid_candidate")


if __name__ == "__main__":
    unittest.main()
