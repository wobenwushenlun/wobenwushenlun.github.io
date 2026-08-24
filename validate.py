from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
SITE = ROOT / "_site"


class PageAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.h1_count = 0
        self.title_count = 0
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h1":
            self.h1_count += 1
        if tag == "title":
            self.title_count += 1
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.references.append(values["href"] or "")
        if tag in {"img", "script", "link"}:
            reference = values.get("src") or values.get("href")
            if reference:
                self.references.append(reference)


def local_target(reference: str) -> Path | None:
    parsed = urlparse(reference)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    path = unquote(parsed.path)
    if path == "/":
        return SITE / "index.html"
    target = SITE / path.lstrip("/")
    if path.endswith("/"):
        target /= "index.html"
    return target


def main() -> None:
    if not SITE.exists():
        raise SystemExit("_site does not exist; run build.py first")

    errors: list[str] = []
    html_files = sorted(SITE.rglob("*.html"))
    for path in html_files:
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SITE)
        for token in ("{{", "{%", 'markdown="1"'):
            if token in source:
                errors.append(f"{relative}: unrendered token {token}")
        audit = PageAudit()
        audit.feed(source)
        if audit.title_count != 1:
            errors.append(f"{relative}: expected one title, found {audit.title_count}")
        if audit.h1_count != 1:
            errors.append(f"{relative}: expected one h1, found {audit.h1_count}")
        for reference in audit.references:
            target = local_target(reference)
            if target is not None and not target.exists():
                errors.append(f"{relative}: broken reference {reference}")

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print(f"Validated {len(html_files)} HTML page(s); internal references are intact.")


if __name__ == "__main__":
    main()

