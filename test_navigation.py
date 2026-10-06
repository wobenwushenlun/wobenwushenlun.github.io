import unittest
from datetime import datetime, timezone

from build import post_navigation, reading_order


def post(slug, category, day, **metadata):
    return {
        "slug": slug,
        "category": category,
        "date": datetime(2026, 10, day, tzinfo=timezone.utc),
        **metadata,
    }


class ReadingOrderTests(unittest.TestCase):
    def test_interleaved_publications_keep_chapters_together(self):
        posts = [
            post("basics-01-intro", "Basics", 5),
            post("agent-04-react", "Agent", 7),
            post("agent-02-loop", "Agent", 2),
            post("agent-03-tools", "Agent", 3),
        ]
        ordered = reading_order(posts)
        self.assertEqual(
            [item["slug"] for item in ordered],
            ["agent-02-loop", "agent-03-tools", "agent-04-react", "basics-01-intro"],
        )
        self.assertEqual(posts[0]["slug"], "basics-01-intro")

    def test_category_order_uses_earliest_publication(self):
        posts = [
            post("old-02-next", "Old", 20),
            post("new-01-first", "New", 10),
            post("old-01-first", "Old", 1),
        ]
        self.assertEqual(
            [item["slug"] for item in reading_order(posts)],
            ["old-01-first", "old-02-next", "new-01-first"],
        )

    def test_numeric_chapters_and_explicit_order_override_dates(self):
        posts = [
            post("guide-10-end", "Guide", 1),
            post("guide-2-middle", "Guide", 5),
            post("guide-99-start", "Guide", 9, order=1),
        ]
        self.assertEqual(
            [item["slug"] for item in reading_order(posts)],
            ["guide-99-start", "guide-2-middle", "guide-10-end"],
        )

    def test_unnumbered_notes_follow_chapters_in_date_order(self):
        posts = [
            post("later", "Notes", 6),
            post("earlier", "Notes", 1),
            post("notes-01-chapter", "Notes", 3),
        ]
        self.assertEqual(
            [item["slug"] for item in reading_order(posts)],
            ["notes-01-chapter", "earlier", "later"],
        )

    def test_equal_dates_are_deterministic_and_primary_category_is_used(self):
        posts = [
            post("z-note", "A", 1, categories=["A", "B"]),
            post("b-note", "B", 1),
            post("a-note", "A", 1),
        ]
        self.assertEqual(
            [item["slug"] for item in reading_order(posts)],
            ["a-note", "z-note", "b-note"],
        )

    def test_empty_and_single_post(self):
        self.assertEqual(reading_order([]), [])
        single = post("only", "Notes", 1)
        self.assertEqual(reading_order([single]), [single])

    def test_cross_category_links_always_enter_first_chapter(self):
        posts = [
            post("a-02-later", "A", 1),
            post("a-01-first", "A", 2),
            post("b-01-first", "B", 3),
            post("b-02-later", "B", 4),
            post("c-01-first", "C", 5),
        ]
        nav = post_navigation(posts)
        self.assertEqual(nav["b-01-first"]["previous_post"]["slug"], "a-01-first")
        self.assertEqual(nav["a-02-later"]["next_post"]["slug"], "b-01-first")
        self.assertEqual(nav["b-02-later"]["next_post"]["slug"], "c-01-first")
        self.assertEqual(nav["b-01-first"]["next_post"]["slug"], "b-02-later")
        self.assertEqual(nav["b-02-later"]["previous_post"]["slug"], "b-01-first")
        self.assertEqual(nav["b-02-later"]["chapter_position"], 2)
        self.assertEqual(nav["b-02-later"]["chapter_count"], 2)
        self.assertEqual(
            [chapter["slug"] for chapter in nav["b-02-later"]["chapter_posts"]],
            ["b-01-first", "b-02-later"],
        )
        self.assertIsNone(nav["a-01-first"]["previous_post"])
        self.assertIsNone(nav["c-01-first"]["next_post"])

    def test_empty_and_single_navigation(self):
        self.assertEqual(post_navigation([]), {})
        single = post("only", "Notes", 1)
        nav = post_navigation([single])["only"]
        self.assertEqual(nav, {
            "previous_post": None, "next_post": None,
            "chapter_position": 1, "chapter_count": 1,
            "chapter_posts": [single],
        })


if __name__ == "__main__":
    unittest.main()
