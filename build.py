from __future__ import annotations

import argparse
import html
import math
import re
import shutil
import threading
import time
from datetime import date, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "_site"
TEMPLATES = ROOT / "templates"
IGNORED_WATCH_DIRS = {".conda", ".jekyll-conda", ".git", "_site", "__pycache__"}


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def parse_front_matter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid front matter: {path}")
    return yaml.safe_load(parts[1]) or {}, parts[2].lstrip()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value, flags=re.UNICODE)
    return value.strip("-") or "note"


def coerce_datetime(value: Any, filename: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if value:
        raw = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                pass
    match = re.match(r"(\d{4}-\d{2}-\d{2})", filename)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d")
    return datetime.now()


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def reading_minutes(text: str) -> int:
    units = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", strip_html(text))
    return max(1, math.ceil(len(units) / 400))


def write_text(relative_path: str, content: str) -> None:
    target = OUTPUT / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def load_posts() -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    for path in sorted((ROOT / "_posts").glob("*.md")):
        meta, source = parse_front_matter(path)
        rendered = markdown.markdown(
            source,
            extensions=["extra", "sane_lists", "smarty"],
            output_format="html5",
        )
        published = coerce_datetime(meta.get("date"), path.name)
        slug = slugify(path.stem[11:] if re.match(r"\d{4}-\d{2}-\d{2}-", path.stem) else path.stem)
        categories = meta.get("categories") or ["随笔"]
        if isinstance(categories, str):
            categories = [categories]
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        excerpt = str(meta.get("excerpt") or strip_html(rendered)[:160])
        posts.append(
            {
                **meta,
                "title": meta.get("title") or path.stem,
                "date": published,
                "date_display": published.strftime("%Y.%m.%d"),
                "date_iso": published.isoformat(),
                "categories": categories,
                "category": categories[0],
                "tags": tags,
                "excerpt": excerpt,
                "content": rendered,
                "minutes": reading_minutes(rendered),
                "slug": slug,
                "url": f"/notes/{slug}/",
                "source_path": str(path.relative_to(ROOT)),
            }
        )
    return sorted(posts, key=lambda item: item["date"], reverse=True)


def category_index(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for post in posts:
        for name in post["categories"]:
            grouped.setdefault(str(name), []).append(post)
    return [
        {"name": name, "slug": slugify(name), "posts": items, "count": len(items)}
        for name, items in grouped.items()
    ]


def reading_order(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for post in posts:
        grouped.setdefault(post["category"], []).append(post)

    def chapter_key(post: dict[str, Any]) -> tuple[float, datetime, str]:
        number = post.get("order")
        if number is None:
            match = re.search(r"-(\d+)(?:-|$)", post["slug"])
            number = int(match.group(1)) if match else math.inf
        return float(number), post["date"], post["slug"]

    # Keep categories contiguous; later chapters must not move a whole category.
    categories = sorted(
        grouped,
        key=lambda name: (min(post["date"] for post in grouped[name]), name),
    )
    return [
        post
        for name in categories
        for post in sorted(grouped[name], key=chapter_key)
    ]


def render_feed(site: dict[str, Any], posts: list[dict[str, Any]]) -> str:
    updated = posts[0]["date_iso"] if posts else datetime.now().isoformat()
    entries = []
    for post in posts[:20]:
        url = f"{site['url']}{post['url']}"
        entries.append(
            "\n".join(
                [
                    "  <entry>",
                    f"    <title>{xml_escape(str(post['title']))}</title>",
                    f"    <link href=\"{xml_escape(url)}\"/>",
                    f"    <id>{xml_escape(url)}</id>",
                    f"    <updated>{post['date_iso']}</updated>",
                    f"    <summary>{xml_escape(post['excerpt'])}</summary>",
                    "  </entry>",
                ]
            )
        )
    return "\n".join(
        [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom">',
            f"  <title>{xml_escape(site['title'])}</title>",
            f"  <link href=\"{site['url']}/feed.xml\" rel=\"self\"/>",
            f"  <link href=\"{site['url']}/\"/>",
            f"  <id>{site['url']}/</id>",
            f"  <updated>{updated}</updated>",
            *entries,
            "</feed>",
            "",
        ]
    )


def render_sitemap(site: dict[str, Any], posts: list[dict[str, Any]]) -> str:
    urls = ["/", "/ai-infra/", "/categories/", "/works/", "/about/"] + [post["url"] for post in posts]
    rows = [f"  <url><loc>{xml_escape(site['url'] + url)}</loc></url>" for url in urls]
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *rows,
            "</urlset>",
            "",
        ]
    )


def build() -> None:
    site = load_yaml(ROOT / "_config.yml")
    site["navigation"] = load_yaml(ROOT / "_data" / "navigation.yml")
    site["works"] = load_yaml(ROOT / "_data" / "works.yml")
    site["ai_infra"] = load_yaml(ROOT / "_data" / "ai_infra.yml")
    posts = load_posts()
    categories = category_index(posts)
    ai_infra_category = next((item for item in categories if item["name"] == "AI Infra"), None)
    if ai_infra_category is None:
        ai_infra_category = {"name": "AI Infra", "slug": "ai-infra", "posts": [], "count": 0}
    else:
        categories.remove(ai_infra_category)
    ai_infra_category["pages"] = [{"title": "大模型 AI Infra 学习地图", "url": "/ai-infra/"}]
    ai_infra_category["count"] += 1
    categories.insert(0, ai_infra_category)

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["slugify"] = slugify

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    shutil.copytree(ROOT / "assets", OUTPUT / "assets")

    common = {"site": site, "posts": posts, "categories": categories}
    latest = posts[0] if posts else None
    write_text(
        "index.html",
        env.get_template("index.html").render(
            **common,
            latest=latest,
            page_title=None,
            page_description=site["description"],
            page_url="/",
            body_class="home",
        ),
    )
    write_text(
        "ai-infra/index.html",
        env.get_template("ai_infra.html").render(
            **common,
            page_title="AI Infra 学习地图",
            page_description="从模型成本、GPU 与通信、分布式训练到推理运行时和服务化的学习路线与实践清单。",
            page_url="/ai-infra/",
            body_class="infra-page",
        ),
    )
    write_text(
        "categories/index.html",
        env.get_template("categories.html").render(
            **common,
            page_title="分类",
            page_description="从不同主题进入，同一段学习旅程。",
            page_url="/categories/",
            body_class="page",
        ),
    )
    write_text(
        "works/index.html",
        env.get_template("works.html").render(
            **common,
            page_title="作品",
            page_description="一些正在发生的练习、项目与长期记录。",
            page_url="/works/",
            body_class="page",
        ),
    )

    about_meta, about_source = parse_front_matter(ROOT / "about.md")
    about_content = markdown.markdown(about_source, extensions=["extra", "sane_lists", "smarty"])
    write_text(
        "about/index.html",
        env.get_template("about.html").render(
            **common,
            about=about_meta,
            about_content=about_content,
            page_title=about_meta.get("title", "关于"),
            page_description=about_meta.get("description", site["description"]),
            page_url="/about/",
            body_class="page",
        ),
    )

    ordered_posts = reading_order(posts)
    for index, post in enumerate(ordered_posts):
        previous_post = ordered_posts[index - 1] if index > 0 else None
        next_post = ordered_posts[index + 1] if index + 1 < len(ordered_posts) else None
        write_text(
            f"notes/{post['slug']}/index.html",
            env.get_template("post.html").render(
                **common,
                post=post,
                previous_post=previous_post,
                next_post=next_post,
                page_title=post["title"],
                page_description=post["excerpt"],
                page_url=post["url"],
                body_class="post-page",
            ),
        )

    write_text(
        "404.html",
        env.get_template("404.html").render(
            **common,
            page_title="页面走丢了",
            page_description="这个样本不在训练集中。",
            page_url="/404.html",
            body_class="page",
        ),
    )
    write_text("feed.xml", render_feed(site, posts))
    write_text("sitemap.xml", render_sitemap(site, posts))
    write_text("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site['url']}/sitemap.xml\n")
    print(f"Built {len(posts)} post(s) into {OUTPUT}")


def source_snapshot() -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for path in ROOT.rglob("*"):
        is_ignored = any(
            part in IGNORED_WATCH_DIRS or part.startswith(".edge-preview")
            for part in path.parts
        )
        if not path.is_file() or is_ignored or path.name.startswith("preview-"):
            continue
        snapshot[str(path)] = path.stat().st_mtime
    return snapshot


def watch_sources() -> None:
    previous = source_snapshot()
    while True:
        time.sleep(1)
        current = source_snapshot()
        if current == previous:
            continue
        try:
            build()
            previous = current
            print("Source changed; site rebuilt.")
        except Exception as exc:  # keep the preview server alive while editing
            print(f"Build failed: {exc}")


class PreviewHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        print(f"[preview] {format % args}")


def serve(host: str, port: int) -> None:
    build()
    threading.Thread(target=watch_sources, daemon=True).start()
    handler = partial(PreviewHandler, directory=str(OUTPUT))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Preview: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPreview stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the 人生=模型 static blog")
    parser.add_argument("--serve", action="store_true", help="build, watch, and serve locally")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=4000, type=int)
    args = parser.parse_args()
    if args.serve:
        serve(args.host, args.port)
    else:
        build()
