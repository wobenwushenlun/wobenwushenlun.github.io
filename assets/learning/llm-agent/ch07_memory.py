"""SQLite memory lifecycle demo. Temporary database, no API calls or model generation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ch03_tools import read_allowed
from ch06_context import terms


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Memory:
    id: str
    scope: str
    key: str
    kind: str
    text: str
    source: str
    revision: str
    expires_at: int
    verified: bool = False


class MemoryStore:
    def __init__(self, path: str | Path):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, key TEXT NOT NULL,
            kind TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL,
            revision TEXT NOT NULL, expires_at INTEGER NOT NULL,
            verified INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1)""")
        self.connection.commit()

    def close(self):
        self.connection.close()

    def put(self, item: Memory):
        values = asdict(item)
        for name in ("id", "scope", "key", "text", "source", "revision"):
            if not isinstance(values[name], str) or not values[name].strip():
                raise ValueError(f"Missing string: {name}")
        if item.kind not in {"semantic", "episodic", "procedural"}:
            raise ValueError("Unknown memory kind")
        if type(item.expires_at) is not int or type(item.verified) is not bool:
            raise ValueError("Invalid expiry or verification flag")
        if len(item.text) > 2000:
            raise ValueError("Memory text exceeds teaching limit")
        with self.connection:
            self.connection.execute("""INSERT INTO memories
                (id, scope, key, kind, text, source, revision, expires_at, verified)
                VALUES (:id, :scope, :key, :kind, :text, :source, :revision, :expires_at, :verified)""", values)

    def deactivate(self, memory_id: str):
        # Explicit invalidation retains an audit record; it is not a privacy erasure API.
        with self.connection:
            self.connection.execute("UPDATE memories SET active=0 WHERE id=?", (memory_id,))

    def retrieve(self, scope: str, query: str, revisions: dict[str, str], now: int,
                 budget_chars: int = 900, top_k: int = 3) -> dict:
        if budget_chars < 0 or top_k < 1:
            raise ValueError("Invalid retrieval budget")
        # Filter scope BEFORE scoring; do not put other scopes in diagnostics either.
        rows = self.connection.execute(
            "SELECT * FROM memories WHERE scope=? AND active=1 ORDER BY id", (scope,)).fetchall()
        eligible, excluded = [], []
        for row in rows:
            reason = ("unverified" if not row["verified"] else
                      "expired" if row["expires_at"] <= now else
                      "stale_source" if revisions.get(row["source"]) != row["revision"] else None)
            if reason:
                excluded.append({"id": row["id"], "reason": reason})
            else:
                eligible.append(dict(row))
        relevant_keys = {r["key"] for r in eligible if terms(query) & terms(r["key"] + " " + r["text"])}
        conflicts = sorted(key for key in relevant_keys
                           if len({r["text"] for r in eligible if r["key"] == key}) > 1)
        ranked = sorted(eligible, key=lambda r: (
            -len(terms(query) & terms(r["key"] + " " + r["text"])), r["id"]))
        selected, parts, used = [], [], 0
        seen = set()
        for row in ranked:
            score = len(terms(query) & terms(row["key"] + " " + row["text"]))
            duplicate_key = (row["key"], row["text"])
            if row["key"] in conflicts:
                reason = "conflicting_claims"
            elif not score:
                reason = "no_term_overlap"
            elif duplicate_key in seen:
                reason = "duplicate"
            elif len(selected) >= top_k:
                reason = "top_k"
            else:
                payload = {k: row[k] for k in ("id", "key", "kind", "text", "source", "revision")}
                part = json.dumps({"untrusted_memory": payload}, ensure_ascii=False) + "\n"
                reason = "budget" if used + len(part) > budget_chars else None
            if reason:
                excluded.append({"id": row["id"], "reason": reason})
            else:
                selected.append(payload)
                parts.append(part)
                used += len(part)
                seen.add(duplicate_key)
        return {"selected": selected, "conflicts": conflicts, "excluded": excluded,
                "context": "".join(parts), "used_chars": used,
                "status": "needs_resolution" if conflicts else "retrieved" if selected else "empty"}


def demo(scenario: str) -> dict:
    revision = digest(read_allowed("README.md"))
    # Time is a reproducible logical clock, not today's wall clock.
    with tempfile.TemporaryDirectory(prefix="agent-memory-lesson-") as directory:
        path = Path(directory) / "memory.sqlite"
        store = MemoryStore(path)
        try:
            items = [
                Memory("fact", "discount-demo", "discount.meaning", "semantic",
                       "discount is the fraction taken off the price", "README.md", revision, 200, True),
                Memory("guess", "discount-demo", "discount.guess", "episodic",
                       "discount always means the amount to pay", "README.md", revision, 200, False),
                Memory("old", "discount-demo", "discount.old", "semantic",
                       "old discount convention", "README.md", "old-revision", 200, True),
                Memory("foreign", "other-project", "discount.meaning", "semantic",
                       "discount means fraction payable", "README.md", revision, 200, True),
            ]
            for item in items:
                store.put(item)
            if scenario == "conflict":
                store.put(Memory("conflict", "discount-demo", "discount.meaning", "semantic",
                                 "discount is the fraction paid", "README.md", revision, 200, True))
        finally:
            store.close()
        # Reopen the same file to demonstrate persistence beyond one connection.
        store = MemoryStore(path)
        try:
            if scenario == "forgotten":
                store.deactivate("fact")
            revisions = {"README.md": "changed" if scenario == "stale" else revision}
            result = store.retrieve("discount-demo", "discount price", revisions,
                                    now=200 if scenario == "expired" else 100)
        finally:
            store.close()
    return {"execution": "offline_retrieval_only", "scenario": scenario,
            "database_reopened": True, "database_retained_after_demo": False, **result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["normal", "conflict", "stale", "expired", "forgotten"], default="normal")
    print(json.dumps(demo(parser.parse_args().scenario), ensure_ascii=False, indent=2))
