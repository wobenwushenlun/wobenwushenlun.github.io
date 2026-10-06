"""Sequential role-protocol simulator. No LLM agents, concurrency or repository writes."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

from ch03_tools import ALLOWED_FILES, read_allowed
from ch07_memory import digest
from ch08_reflection import evaluate


ROLES = ("spec_reader", "coder", "reviewer")
ROLE_SOURCES = {"spec_reader": ("README.md",), "coder": ("pricing.py",),
                "reviewer": ("test_pricing.py",)}
TASK = "discount-diagnosis"


@dataclass(frozen=True)
class Report:
    task_id: str
    revision: int
    role: str
    evidence: dict[str, str]
    candidate: str


class Coordinator:
    def __init__(self, versions: dict[str, str], max_messages: int = 3, revision: int = 1):
        if max_messages < 1:
            raise ValueError("Message budget must be positive")
        self.versions = dict(versions)
        self.max_messages = max_messages
        self.revision = revision
        self.received = 0
        self.reports = {}
        self.events = []

    def submit(self, sender: str, report: Report) -> str:
        if self.received >= self.max_messages:
            return "message_limit"
        self.received += 1  # Rejected/duplicate attempts also consume the same budget.
        if report.task_id != TASK or report.revision != self.revision:
            verdict = "wrong_task_or_revision"
        elif sender not in ROLES or report.role != sender:
            verdict = "wrong_sender"
        elif sender in self.reports:
            verdict = "duplicate"
        elif not isinstance(report.candidate, str) or report.candidate not in {"payable", "saved_amount", "constant_80"}:
            verdict = "invalid_candidate"
        elif not isinstance(report.evidence, dict) or set(report.evidence) != set(ROLE_SOURCES[sender]):
            verdict = "invalid_evidence_scope"
        elif any(self.versions.get(path) != version for path, version in report.evidence.items()):
            verdict = "stale_evidence"
        else:
            self.reports[sender] = Report(report.task_id, report.revision, sender,
                                          dict(report.evidence), report.candidate)
            verdict = "accepted"
        self.events.append({"sender": sender, "verdict": verdict})
        return verdict

    def finalize(self) -> dict:
        base = {"received": self.received, "events": list(self.events),
                "reports": [asdict(self.reports[role]) for role in ROLES if role in self.reports]}
        missing = sorted(set(ROLES) - self.reports.keys())
        if missing:
            return {**base, "status": "incomplete", "missing": missing}
        candidates = {r.candidate for r in self.reports.values()}
        if len(candidates) != 1:
            return {**base, "status": "needs_resolution", "conflicting_candidates": sorted(candidates)}
        candidate = next(iter(candidates))
        # Consensus alone does not authorize acceptance; independent arithmetic verification.
        verification = evaluate(candidate)
        return {**base, "status": "verified_proposal" if verification["passed"] else "verification_failed",
                "candidate": candidate, "verification": verification, "files_modified": False}


def run_team(scenario: str = "normal", max_messages: int = 3) -> dict:
    documents = {path: read_allowed(path) for path in ALLOWED_FILES}
    versions = {path: digest(text) for path, text in documents.items()}
    coordinator = Coordinator(versions, max_messages)
    packets = []
    for role in ROLES:
        # Host chooses identity and source set. These functions are scripted stand-ins.
        packet = {"task_id": TASK, "revision": 1, "role": role,
                  "sources": {path: documents[path] for path in ROLE_SOURCES[role]}}
        packets.append({"role": role, "source_names": list(packet["sources"]),
                        "input_chars": len(json.dumps(packet))})
        if scenario == "missing" and role == "reviewer":
            continue
        candidate = "saved_amount" if scenario == "unanimous_wrong" or (scenario == "conflict" and role == "reviewer") else "payable"
        evidence = {path: versions[path] for path in ROLE_SOURCES[role]}
        if scenario == "stale" and role == "coder":
            evidence["pricing.py"] = "old-version"
        coordinator.submit(role, Report(TASK, 1, role, evidence, candidate))
    return {"execution": "scripted_sequential_roles", "scenario": scenario,
            "packets": packets, **coordinator.finalize()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["normal", "conflict", "stale", "missing", "unanimous_wrong"], default="normal")
    parser.add_argument("--max-messages", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(run_team(args.scenario, args.max_messages), ensure_ascii=False, indent=2))
