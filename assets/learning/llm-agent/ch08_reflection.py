"""Bounded revision with deterministic actors and trusted arithmetic; no generated code execution."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from typing import Callable


# Trusted, finite candidate catalogue. Never eval()/exec() model-generated expressions.
CANDIDATES = {
    "saved_amount": lambda price, discount: price * discount,
    "constant_80": lambda price, discount: Decimal("80"),
    "payable": lambda price, discount: price * (Decimal("1") - discount),
}
PUBLIC_CASES = (("100", "0.2", "80"), ("100", "0", "100"), ("100", "1", "0"))
# Public in this teaching source, so NOT a secret benchmark or contamination-free holdout.
AUDIT_CASES = (("250", "0.1", "225"), ("0", "0.2", "0"), ("50", "0.5", "25"))


def evaluate(candidate: str, cases=PUBLIC_CASES) -> dict:
    if candidate not in CANDIDATES:
        raise ValueError("Candidate is outside the trusted catalogue")
    if not cases:
        raise ValueError("An empty test suite cannot certify a candidate")
    failures = []
    for price, discount, expected in cases:
        actual = CANDIDATES[candidate](Decimal(price), Decimal(discount))
        if actual != Decimal(expected):
            failures.append({"price": price, "discount": discount,
                             "expected": expected, "actual": str(actual)})
    return {"passed": not failures, "checked": len(cases), "failures": failures}


def reflect(candidate: str, feedback: dict) -> dict:
    # This is a scripted rule, not a language model-generated diagnosis.
    return {"failed_candidate": candidate, "evidence": feedback["failures"],
            "hypothesis": "The task asks for payable price, not savings or a memorized amount.",
            "next_check": "Check no discount, full discount, and a different original price.",
            "scope": "discount is a fraction taken off; 0 <= discount <= 1",
            "verified": False}


def scripted_actor(attempt: int, memories: list[dict]) -> str:
    return "saved_amount" if not memories else "payable"


def run_revision(actor: Callable = scripted_actor, max_attempts: int = 3,
                 cases=PUBLIC_CASES) -> dict:
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    memories, trace, seen = [], [], set()
    status, accepted, proposals = "attempt_limit", None, 0
    for attempt in range(1, max_attempts + 1):
        proposals += 1
        # Copies prevent the actor from mutating the verifier's stored feedback.
        candidate = actor(attempt, json.loads(json.dumps(memories)))
        if not isinstance(candidate, str) or candidate not in CANDIDATES:
            status = "invalid_candidate"
            break
        if candidate in seen:
            # Valid only because evaluation is deterministic and environment unchanged.
            status = "stalled"
            break
        seen.add(candidate)
        feedback = evaluate(candidate, cases)
        trace.append({"attempt": attempt, "candidate": candidate, "feedback": feedback})
        if feedback["passed"]:
            accepted, status = candidate, "public_passed"
            break
        if attempt < max_attempts:
            memories.append(reflect(candidate, feedback))
    return {"execution": "scripted_offline", "status": status, "candidate": accepted,
            "proposals": proposals, "evaluations": len(trace), "reflections": memories, "trace": trace}


def audit_frozen(result: dict) -> dict:
    if result["candidate"] is None:
        return {"status": "not_run", "reason": "No accepted candidate"}
    report = evaluate(result["candidate"], AUDIT_CASES)
    return {"status": "passed" if report["passed"] else "failed", **report,
            "returned_to_actor": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["repair", "repeat", "overfit"], default="repair")
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    actors = {"repair": scripted_actor, "repeat": lambda attempt, memories: "saved_amount",
              "overfit": lambda attempt, memories: "constant_80"}
    result = run_revision(actors[args.mode], args.max_attempts,
                          cases=PUBLIC_CASES[:1] if args.mode == "overfit" else PUBLIC_CASES)
    result["audit"] = audit_frozen(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
