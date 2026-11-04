"""
Unit tests for the Fenrirealm HTML parser.
Uses captured fixture HTML — no network or browser needed.
"""

import unittest
from fenrirealm.parser import parse_fenrirealm_chapter, is_end_of_series

SAMPLE_CHAPTER_HTML = """
<html><body>
  <div class="chapter-view">
    <div class="text-center"><h2>Absolute Regression — Chapter 1: The Fall</h2></div>
    <div class="reader-area">
      <p>It was a dark and stormy night.</p>
      <p>The protagonist fell from the sky.</p>
    </div>
  </div>
</body></html>
"""

SAMPLE_404_HTML = """
<html><body>
  <h1>404 - Page Not Found</h1>
  <p>The chapter you are looking for does not exist.</p>
</body></html>
"""


class TestFenrirealmParser(unittest.TestCase):
    def test_parse_chapter_extracts_title(self):
        ch = parse_fenrirealm_chapter(SAMPLE_CHAPTER_HTML, chapter_number=1, url="https://example.com/1")
        self.assertIsNotNone(ch)
        self.assertIn("Fall", ch.display_title)

    def test_parse_chapter_extracts_body(self):
        ch = parse_fenrirealm_chapter(SAMPLE_CHAPTER_HTML, chapter_number=1, url="https://example.com/1")
        self.assertIsNotNone(ch)
        self.assertIn("dark and stormy", ch.body_html)
        self.assertIn("protagonist", ch.body_html)

    def test_parse_chapter_correct_ordinal(self):
        ch = parse_fenrirealm_chapter(SAMPLE_CHAPTER_HTML, chapter_number=42, url="https://example.com/42")
        self.assertIsNotNone(ch)
        self.assertEqual(ch.ordinal, 42)

    def test_parse_chapter_returns_none_for_missing_view(self):
        ch = parse_fenrirealm_chapter(
            "<html><body><p>Nothing here</p></body></html>",
            chapter_number=1,
            url="https://example.com/1",
        )
        self.assertIsNone(ch)

    def test_is_end_of_series_true_on_404(self):
        self.assertTrue(is_end_of_series(SAMPLE_404_HTML))

    def test_is_end_of_series_false_on_valid(self):
        self.assertFalse(is_end_of_series(SAMPLE_CHAPTER_HTML))


if __name__ == "__main__":
    unittest.main()
