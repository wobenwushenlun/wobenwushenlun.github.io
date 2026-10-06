"""Chapter 5: deterministic DAG executor and bounded plan repair; zero API calls."""
from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from typing import Callable

from ch03_tools import execute


@dataclass(frozen=True)
class Task:
    id: str
    tool: str
    args: dict
    deps: tuple[str, ...] = ()


@dataclass
class PlanState:
    status: str = "running"
    attempts: int = 0
    revisions: int = 0
    done: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)


def validate_plan(tasks: list[Task]) -> None:
    if not tasks or len(tasks) > 12:
        raise ValueError("Plan must contain 1..12 tasks")
    ids = [task.id for task in tasks]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Task IDs must be unique non-empty strings")
    for task in tasks:
        if task.tool not in {"read_file", "search_code", "list_files"} or not isinstance(task.args, dict):
            raise ValueError("Invalid tool or arguments")
        if any(dep not in ids for dep in task.deps) or task.id in task.deps:
            raise ValueError("Missing or self dependency")
    visited = set()
    while len(visited) < len(tasks):
        ready = {t.id for t in tasks if t.id not in visited and set(t.deps) <= visited}
        if not ready:
            raise ValueError("Plan contains a dependency cycle")
        visited.update(ready)


def validate_revision(old: list[Task], new: list[Task], done: dict) -> None:
    validate_plan(new)
    previous = {task.id: task for task in old}
    updated = {task.id: task for task in new}
    if previous.keys() != updated.keys():
        raise ValueError("This lesson permits repair, not adding/removing task IDs")
    for task_id in done:
        if previous[task_id] != updated[task_id]:
            raise ValueError("Cannot rewrite already completed tasks")


def initial_plan(fault: bool = False) -> list[Task]:
    return [Task("spec", "read_file", {"path": "README.md"}),
            Task("code", "read_file", {"path": "missing.py" if fault else "pricing.py"}, ("spec",)),
            Task("tests", "read_file", {"path": "test_pricing.py"}, ("spec",))]


def repair_plan(tasks: list[Task], failed: Task, error: str) -> list[Task]:
    # A visible scripted planner stub, NOT an LLM inference about arbitrary failures.
    return [Task(t.id, t.tool, {"path": "pricing.py"}, t.deps)
            if t.id == failed.id == "code" else copy.deepcopy(t) for t in tasks]


def run_plan(tasks: list[Task], repair: Callable | None = repair_plan,
             executor: Callable = execute, max_attempts: int = 6,
             max_revisions: int = 1) -> PlanState:
    if max_attempts < 1 or max_revisions < 0:
        raise ValueError("Invalid budget")
    tasks = copy.deepcopy(tasks)
    validate_plan(tasks)
    state = PlanState()
    while len(state.done) < len(tasks):
        if state.attempts >= max_attempts:
            state.status = "attempt_limit"
            return state
        ready = [t for t in tasks if t.id not in state.done and set(t.deps) <= state.done.keys()]
        task = ready[0]  # Deterministic order; independent tasks are not executed concurrently here.
        state.attempts += 1
        try:
            value = executor(task.tool, copy.deepcopy(task.args))
        except (ValueError, OSError, UnicodeError) as exc:
            state.trace.append({"task": task.id, "event": "failed", "revision": state.revisions,
                                "error_type": type(exc).__name__})
            if repair is None or state.revisions >= max_revisions:
                state.status = "repair_limit"
                return state
            proposal = repair(copy.deepcopy(tasks), copy.deepcopy(task), type(exc).__name__)
            try:
                validate_revision(tasks, proposal, state.done)
            except (ValueError, TypeError, AttributeError):
                state.status = "invalid_revision"
                return state
            tasks = copy.deepcopy(proposal)
            state.revisions += 1
            state.trace.append({"event": "replanned", "revision": state.revisions})
        else:
            state.done[task.id] = value
            state.trace.append({"task": task.id, "event": "done", "revision": state.revisions})
    state.status = "completed"  # All evidence tasks completed; not a verified diagnosis or patch.
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault", action="store_true")
    parser.add_argument("--no-repair", action="store_true")
    args = parser.parse_args()
    state = run_plan(initial_plan(args.fault), repair=None if args.no_repair else repair_plan)
    print(json.dumps({"execution": "scripted_offline", "status": state.status,
                      "attempts": state.attempts, "revisions": state.revisions,
                      "completed_tasks": list(state.done), "trace": state.trace}, indent=2))


if __name__ == "__main__":
    main()
