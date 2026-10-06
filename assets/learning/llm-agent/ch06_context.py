"""Chapter 6: evidence selection with an explicit character budget, NOT token counting."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass

from ch03_tools import ALLOWED_FILES, read_allowed


@dataclass(frozen=True)
class Chunk:
    path: str
    start: int
    end: int
    digest: str
    text: str


def terms(text: str) -> set[str]:
    # Teaching baseline for English words and Python identifiers; not a multilingual tokenizer.
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def make_chunks(documents: dict[str, str], lines_per_chunk: int = 4) -> list[Chunk]:
    if lines_per_chunk < 1:
        raise ValueError("lines_per_chunk must be positive")
    chunks = []
    for path, text in sorted(documents.items()):
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        lines = text.splitlines()
        for start in range(0, len(lines), lines_per_chunk):
            section = lines[start:start + lines_per_chunk]
            chunks.append(Chunk(path, start + 1, start + len(section), digest, "\n".join(section)))
    return chunks


def render_chunk(chunk: Chunk) -> str:
    return (f"[untrusted file={chunk.path} lines={chunk.start}-{chunk.end} sha256={chunk.digest}]\n"
            f"{chunk.text}\n[/untrusted]\n")


def build_context(query: str, documents: dict[str, str], evidence_budget: int = 1100,
                  lines_per_chunk: int = 4) -> dict:
    if evidence_budget < 0:
        raise ValueError("evidence_budget must not be negative")
    query_terms = terms(query)
    candidates = make_chunks(documents, lines_per_chunk)
    ranked = sorted(candidates, key=lambda c: (
        -len(query_terms & terms(c.path + " " + c.text)), c.path, c.start))
    selected, dropped, parts = [], [], []
    used = 0
    for chunk in ranked:
        score = len(query_terms & terms(chunk.path + " " + chunk.text))
        label = {"path": chunk.path, "start": chunk.start, "end": chunk.end, "score": score}
        rendered = render_chunk(chunk)
        if not score:
            dropped.append({**label, "reason": "no_term_overlap"})
        elif used + len(rendered) > evidence_budget:
            dropped.append({**label, "reason": "budget"})
        else:
            parts.append(rendered)
            used += len(rendered)
            selected.append({**label, "sha256": chunk.digest})
    return {"query": query, "budget_unit": "python_unicode_characters_not_tokens",
            "evidence_budget": evidence_budget, "used": used, "context": "".join(parts),
            "selected": selected, "dropped": dropped}


def verify_manifest(selected: list[dict], documents: dict[str, str]) -> list[str]:
    stale = set()
    for item in selected:
        text = documents.get(item["path"])
        if text is None or hashlib.sha256(text.encode("utf-8")).hexdigest() != item["sha256"]:
            stale.add(item["path"])
    return sorted(stale)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="discount final_price expected 80")
    parser.add_argument("--budget-chars", type=int, default=1100)
    parser.add_argument("--stale-demo", action="store_true")
    args = parser.parse_args()
    documents = {path: read_allowed(path) for path in ALLOWED_FILES}
    report = build_context(args.query, documents, args.budget_chars)
    if args.stale_demo:
        # Edit only a copy in memory. Nothing is written back to the fixture.
        updated = dict(documents)
        updated["pricing.py"] += "\n# simulated later version\n"
        report["stale_paths_after_simulated_edit"] = verify_manifest(report["selected"], updated)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
