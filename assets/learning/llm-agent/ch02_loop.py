"""Chapter 2: a deterministic policy double, not a real language model."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class AgentState:
    goal: str
    history: list[dict] = field(default_factory=list)
    steps: int = 0
    status: str = "running"
    answer: str | None = None


def environment(action: str) -> dict:
    if action == "inspect_tests":
        return {"ok": True, "test": "test_discount", "expected": 80, "actual": 20}
    if action == "inspect_code":
        return {"ok": True, "source": "return price * discount"}
    return {"ok": False, "error": "Unknown action. Use inspect_tests or inspect_code."}


def scripted_policy(state: AgentState) -> dict:
    seen = {item["action"]["name"] for item in state.history}
    if "inspect_tests" not in seen:
        return {"name": "inspect_tests"}
    if "inspect_code" not in seen:
        return {"name": "inspect_code"}
    return {"name": "finish", "answer": "The code returns the discount amount, not the final price."}


def run(goal: str, policy: Callable[[AgentState], dict] = scripted_policy,
        max_steps: int = 4) -> AgentState:
    if max_steps < 1:
        raise ValueError("max_steps must be positive")
    state = AgentState(goal=goal)
    for _ in range(max_steps):
        state.steps += 1  # Count every decision, including finish and invalid actions.
        action = policy(state)
        if not isinstance(action, dict) or not isinstance(action.get("name"), str):
            state.status = "invalid_action"
            return state
        if action["name"] == "finish":
            answer = action.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                state.status = "invalid_action"
                return state
            state.answer = answer
            state.status = "finished"  # Finished is not the same as independently verified.
            return state
        observation = environment(action["name"])
        state.history.append({"action": action, "observation": observation})
    state.status = "step_limit"
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-steps", type=int, default=4)
    parser.add_argument("--mode", choices=["normal", "repeat", "unknown"], default="normal")
    args = parser.parse_args()
    policies = {
        "normal": scripted_policy,
        "repeat": lambda state: {"name": "inspect_tests"},
        "unknown": lambda state: {"name": "delete_everything"},
    }
    state = run("Explain the discount test failure", policies[args.mode], args.max_steps)
    for event in state.history:
        print(event)
    print(f"status={state.status}; steps={state.steps}; answer={state.answer}")


if __name__ == "__main__":
    main()
