"""
Unit tests for the Fenrir Realm HTML parser.
Uses captured fixture HTML — no network or browser needed.
"""

import unittest
from fenrirealm.parser import (
    parse_fenrirealm_chapter,
    parse_fenrirealm_series_info,
    is_end_of_series,
)

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

# Realistic-ish series overview fixture
SAMPLE_SERIES_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta property="og:title" content="Absolute Regression">
  <meta property="og:image" content="https://fenrirealm.com/media/covers/absolute-regression.jpg">
  <meta name="description" content="A warrior regresses in time to fix past mistakes.">
</head>
<body>
  <h1>Absolute Regression</h1>
  <div class="synopsis">
    <p>After dying in battle, the greatest warrior regresses 20 years.</p>
    <p>Now he must use his knowledge to prevent a catastrophe.</p>
  </div>
  <div class="lazy-image-wrapper">
    <img class="lazy-image-target" data-src="https://fenrirealm.com/media/covers/absolute-regression.jpg" src="">
  </div>
  <div class="genres">
    <a href="/genre/action">Action</a>
    <a href="/genre/fantasy">Fantasy</a>
  </div>
  <div class="tags">
    <a href="/tag/regression">Regression</a>
    <a href="/tag/op-mc">OP MC</a>
  </div>
  <div class="status">Ongoing</div>
  <div class="translator"><a href="/team/xyz">XYZ Scans</a></div>
  <div class="chapter-list">
    <a href="/series/absolute-regression/1">Chapter 1</a>
    <a href="/series/absolute-regression/2">Chapter 2</a>
    <a href="/series/absolute-regression/3">Chapter 3</a>
    <a href="/series/absolute-regression/50">Chapter 50</a>
  </div>
</body>
</html>
"""

SERIES_URL = "https://fenrirealm.com/series/absolute-regression"


class TestFenrir RealmParser(unittest.TestCase):
    def test_parse_chapter_extracts_title(self):
        ch = parse_fenrirealm_chapter(SAMPLE_CHAPTER_HTML, chapter_number=1, url="https://example.com/1")
        self.assertIsNotNone(ch)
        self.assertIn("Fall", ch.display_title)
        # Issue 6: Fenrir Realm has no volume concept — flat chapter with volume=0
        self.assertEqual(ch.meta.volume, 0)
        self.assertEqual(ch.volume, 0)
        self.assertNotIn("Vol.", ch.display_title)
        self.assertTrue(ch.display_title.startswith("Ch. 1 -"))

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


class TestFenrir RealmSeriesInfo(unittest.TestCase):
    def setUp(self):
        self.info = parse_fenrirealm_series_info(SAMPLE_SERIES_HTML, url=SERIES_URL)

    def test_title_extracted(self):
        self.assertEqual(self.info.title, "Absolute Regression")

    def test_url_stored(self):
        self.assertEqual(self.info.url, SERIES_URL)

    def test_book_id_is_slug(self):
        self.assertEqual(self.info.book_id, "absolute-regression")

    def test_first_chapter_id_is_one(self):
        self.assertEqual(self.info.first_chapter_id, "1")

    def test_description_extracted(self):
        self.assertIn("regresses", self.info.description)
        self.assertIn("catastrophe", self.info.description)

    def test_cover_url_from_data_src(self):
        self.assertEqual(
            self.info.cover_url,
            "https://fenrirealm.com/media/covers/absolute-regression.jpg",
        )

    def test_genres_extracted(self):
        self.assertIn("Action", self.info.genres)
        self.assertIn("Fantasy", self.info.genres)

    def test_tags_extracted(self):
        self.assertIn("Regression", self.info.tags)
        self.assertIn("OP MC", self.info.tags)

    def test_status_extracted(self):
        self.assertIn("Ongoing", self.info.status)

    def test_translators_extracted(self):
        self.assertIn("XYZ Scans", self.info.translators)

    def test_chapter_count_from_links(self):
        # Links: ch 1, 2, 3, 50 → 4 unique chapters detected
        self.assertEqual(self.info.total_chapters, 4)
        self.assertEqual(self.info.free_chapters_count, 4)
        self.assertEqual(self.info.locked_chapters_count, 0)

    def test_first_and_latest_chapter_titles(self):
        self.assertEqual(self.info.first_chapter_title, "Ch. 1")
        self.assertEqual(self.info.latest_chapter_title, "Ch. 50")

    def test_free_chapter_range(self):
        self.assertIn("Ch. 1", self.info.free_chapter_range)
        self.assertIn("Ch. 50", self.info.free_chapter_range)

    def test_fallback_cover_from_og_image(self):
        """When no lazy-image-wrapper, og:image meta is used."""
        minimal_html = """
        <html>
        <head><meta property="og:image" content="https://example.com/cover.png"></head>
        <body><h1>Test Novel</h1></body>
        </html>
        """
        info = parse_fenrirealm_series_info(minimal_html, url="https://fenrirealm.com/series/test-novel")
        self.assertEqual(info.cover_url, "https://example.com/cover.png")

    def test_fallback_title_from_og_meta(self):
        """When no h1, title comes from og:title meta."""
        minimal_html = """
        <html>
        <head><meta property="og:title" content="Meta Title Novel"></head>
        <body></body>
        </html>
        """
        info = parse_fenrirealm_series_info(minimal_html, url="https://fenrirealm.com/series/meta-title-novel")
        self.assertEqual(info.title, "Meta Title Novel")

    def test_empty_page_fallback(self):
        """Completely empty page doesn't crash; returns slug as title."""
        empty_html = "<html><body></body></html>"
        info = parse_fenrirealm_series_info(empty_html, url="https://fenrirealm.com/series/my-series")
        self.assertEqual(info.book_id, "my-series")
        self.assertEqual(info.title, "my-series")
        self.assertEqual(info.total_chapters, 0)
        self.assertEqual(info.genres, [])
        self.assertEqual(info.cover_url, "")


class TestFenrir RealmNormalizeURL(unittest.TestCase):
    def test_full_url_passthrough(self):
        from fenrirealm.parser import _normalize_series_url
        url = "https://fenrirealm.com/series/absolute-regression"
        self.assertEqual(_normalize_series_url(url), url)

    def test_bare_slug_converted(self):
        from fenrirealm.parser import _normalize_series_url
        self.assertEqual(
            _normalize_series_url("absolute-regression"),
            "https://fenrirealm.com/series/absolute-regression",
        )

    def test_series_path_converted(self):
        from fenrirealm.parser import _normalize_series_url
        self.assertEqual(
            _normalize_series_url("/series/absolute-regression"),
            "https://fenrirealm.com/series/absolute-regression",
        )

    def test_chapter_url_normalized_to_series_url(self):
        from fenrirealm.parser import _normalize_series_url
        self.assertEqual(
            _normalize_series_url("https://fenrirealm.com/series/absolute-regression/1"),
            "https://fenrirealm.com/series/absolute-regression",
        )
        self.assertEqual(
            _normalize_series_url("https://fenrirealm.com/series/absolute-regression/15/"),
            "https://fenrirealm.com/series/absolute-regression",
        )


if __name__ == "__main__":
    unittest.main()
