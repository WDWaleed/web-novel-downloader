"""
Unit tests for the parser module.
"""

import unittest

from parser import Chapter, normalize_title, parse_chapter


class TestParser(unittest.TestCase):
    def test_normalize_title_standard(self):
        self.assertEqual(
            normalize_title("Chapter 1: After Defeat and Capture, Som", 1),
            "Chapter 1: After Defeat and Capture, Som",
        )

    def test_normalize_title_bare_number(self):
        self.assertEqual(
            normalize_title("2  You're Awake? You're a Dad Now!", 2),
            "Chapter 2: You're Awake? You're a Dad Now!",
        )

    def test_normalize_title_with_colon_number(self):
        self.assertEqual(
            normalize_title("3: The Mysterious Encounter", 3),
            "Chapter 3: The Mysterious Encounter",
        )

    def test_normalize_title_abbreviation_and_dash(self):
        self.assertEqual(
            normalize_title("Ch. 4 - Shadows Fall", 4),
            "Chapter 4: Shadows Fall",
        )

    def test_normalize_title_number_only(self):
        self.assertEqual(normalize_title("5", 5), "Chapter 5")

    def test_normalize_title_no_number(self):
        self.assertEqual(
            normalize_title("Prologue to the Adventure", 1),
            "Chapter 1: Prologue to the Adventure",
        )

    def test_normalize_title_empty(self):
        self.assertEqual(normalize_title("", 7), "Chapter 7")
        self.assertEqual(normalize_title("   ", 8), "Chapter 8")

    def test_parse_chapter_full_flow(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Web Novel Chapter</title></head>
        <body>
            <div class="title">Chapter 1: The Beginning</div>
            <div class="text-content-box">
                <script>var tracker = 1;</script>
                <style>.hide { display: none; }</style>
                <div class="ads">Ad Banner Here</div>
                <p>First paragraph of the story.</p>
                <p> </p>
                <p>Second paragraph with <em>emphasis</em>.</p>
                <div class="footer">Page footer</div>
            </div>
        </body>
        </html>
        """
        chapter = parse_chapter(html, ordinal=1)
        self.assertIsInstance(chapter, Chapter)
        self.assertEqual(chapter.number, 1)
        self.assertEqual(chapter.raw_title, "Chapter 1: The Beginning")
        self.assertEqual(chapter.display_title, "Chapter 1: The Beginning")
        self.assertIn("<p>First paragraph of the story.</p>", chapter.body_html)
        self.assertIn("<p>Second paragraph with <em>emphasis</em>.</p>", chapter.body_html)
        # Ensure junk was removed
        self.assertNotIn("tracker", chapter.body_html)
        self.assertNotIn("Ad Banner Here", chapter.body_html)
        self.assertNotIn("Page footer", chapter.body_html)

    def test_parse_chapter_missing_content_box(self):
        html = "<html><body><div class='title'>Chapter 1</div></body></html>"
        with self.assertRaises(ValueError):
            parse_chapter(html, ordinal=1)

    def test_parse_chapter_br_fallback(self):
        html = """
        <html>
        <body>
            <div class="title">2 A New Path</div>
            <div class="text-content-box">
                Line 1 of novel<br>
                Line 2 of novel<br>
            </div>
        </body>
        </html>
        """
        chapter = parse_chapter(html, ordinal=2)
        self.assertEqual(chapter.display_title, "Chapter 2: A New Path")
        self.assertIn("<p>Line 1 of novel</p>", chapter.body_html)
        self.assertIn("<p>Line 2 of novel</p>", chapter.body_html)


if __name__ == "__main__":
    unittest.main()
