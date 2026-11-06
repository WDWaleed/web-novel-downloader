"""
Unit tests for the Novelight scraper orchestration module.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from parser import ChapterMeta
from scraper import (
    filter_chapters,
    is_chapter_downloaded,
    parse_arguments,
    scrape_novel,
)
from utils import detect_source, extract_novel_slug, resolve_output_dir, slugify


class TestScraper(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_filter_chapters_free_only(self):
        ch1 = ChapterMeta("1", 1, "1", "One", "1 vol. 1 chapter - One", "", is_locked=False)
        ch2 = ChapterMeta("2", 1, "2", "Two", "1 vol. 2 chapter - Two", "", is_locked=True)
        ch3 = ChapterMeta("3", 2, "1", "Three", "2 vol. 1 chapter - Three", "", is_locked=False)

        filtered = filter_chapters([ch1, ch2, ch3], free_only=True)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0].chapter_id, "1")
        self.assertEqual(filtered[1].chapter_id, "3")

    def test_filter_chapters_volumes(self):
        ch1 = ChapterMeta("1", 1, "1", "One", "", "", is_locked=False)
        ch2 = ChapterMeta("2", 2, "1", "Two", "", "", is_locked=False)
        ch3 = ChapterMeta("3", 3, "1", "Three", "", "", is_locked=False)

        filtered = filter_chapters([ch1, ch2, ch3], free_only=False, volumes={1, 3})
        self.assertEqual(len(filtered), 2)
        self.assertEqual([c.volume for c in filtered], [1, 3])

    def test_filter_chapters_start_and_max(self):
        chapters = [
            ChapterMeta(str(i), 1, str(i), f"Title {i}", "", "", is_locked=False)
            for i in range(1, 11)
        ]

        # Start at chapter 3, max 4 chapters -> chapters 3, 4, 5, 6
        filtered = filter_chapters(chapters, start_chapter=3, max_chapters=4)
        self.assertEqual(len(filtered), 4)
        self.assertEqual(filtered[0].chapter_id, "3")
        self.assertEqual(filtered[-1].chapter_id, "6")

    def test_is_chapter_downloaded(self):
        meta = ChapterMeta("101", 1, "1", "One", "1 vol. 1 chapter - One", "", is_locked=False)
        self.assertFalse(is_chapter_downloaded(meta, 1, self.test_dir))

        vol_dir = os.path.join(self.test_dir, "vol_01")
        os.makedirs(vol_dir, exist_ok=True)
        filepath = os.path.join(vol_dir, "chapter_0001.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("<html>content</html>")

        self.assertTrue(is_chapter_downloaded(meta, 1, self.test_dir))

    @patch("sys.argv", ["scraper.py", "--start", "5", "--chapters", "10", "--delay", "0.5"])
    def test_parse_arguments(self):
        args = parse_arguments()
        self.assertEqual(args.start_chapter, 5)
        self.assertEqual(args.max_chapters, 10)
        self.assertEqual(args.start, 5)
        self.assertEqual(args.chapters, 10)
        self.assertEqual(args.delay, 0.5)
        self.assertFalse(args.force)

    def test_parse_arguments_defaults(self):
        args = parse_arguments([])
        self.assertEqual(args.delay, 0.5)
        self.assertEqual(args.jitter, 0.2)
        self.assertFalse(args.fast)

    def test_parse_arguments_fast_mode(self):
        args = parse_arguments(["--fast"])
        self.assertTrue(args.fast)
        self.assertEqual(args.delay, 0.1)
        self.assertEqual(args.jitter, 0.05)

    def test_parse_arguments_fast_mode_override(self):
        args = parse_arguments(["--fast", "--delay", "0.0"])
        self.assertTrue(args.fast)
        self.assertEqual(args.delay, 0.0)
        self.assertEqual(args.jitter, 0.05)

    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_json")
    @patch("scraper.build_epub")
    def test_scrape_novel_mocked_run(self, mock_build_epub, mock_fetch_json, mock_fetch_index):
        ch1 = ChapterMeta("150473", 1, "1", "First Chapter", "1 vol. 1 chapter - First Chapter", "", is_locked=False)
        ch2 = ChapterMeta("150474", 1, "2", "Second Chapter", "1 vol. 2 chapter - Second Chapter", "", is_locked=False)
        mock_fetch_index.return_value = [ch1, ch2]

        content_1 = {"content": '<div class="chapter-text"><div>Paragraph in ch1</div></div>'}
        content_2 = {"content": '<div class="chapter-text"><div>Paragraph in ch2</div></div>'}
        mock_fetch_json.side_effect = [content_1, content_2]
        mock_build_epub.return_value = os.path.join(self.test_dir, "novel.epub")

        args = parse_arguments([
            "--output-dir", self.test_dir,
            "--max-chapters", "2",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])

        scrape_novel(args)

        chapters_dir = os.path.join(self.test_dir, "chapters")
        vol1_dir = os.path.join(chapters_dir, "vol_01")
        self.assertTrue(os.path.exists(os.path.join(vol1_dir, "chapter_0001.html")))
        self.assertTrue(os.path.exists(os.path.join(vol1_dir, "chapter_0002.html")))
        mock_build_epub.assert_called_once()

    @patch("scraper.fetch_chapter_index")
    @patch("scraper.build_epub")
    def test_scrape_novel_list_only(self, mock_build_epub, mock_fetch_index):
        ch1 = ChapterMeta("150473", 1, "1", "Ch 1", "1 vol. 1 chapter - Ch 1", "", is_locked=False)
        mock_fetch_index.return_value = [ch1]

        args = parse_arguments([
            "--output-dir", self.test_dir,
            "--list-only",
        ])

        scrape_novel(args)
        # Should not build EPUB or create chapter files in list-only mode
        mock_build_epub.assert_not_called()

    def test_normalize_novel_url(self):
        from scraper import normalize_novel_url
        self.assertEqual(
            normalize_novel_url("https://novelight.net/book/my-novel"),
            "https://novelight.net/book/my-novel",
        )
        self.assertEqual(
            normalize_novel_url("/book/my-novel"),
            "https://novelight.net/book/my-novel",
        )
        self.assertEqual(
            normalize_novel_url("my-novel"),
            "https://novelight.net/book/my-novel",
        )
        self.assertEqual(
            normalize_novel_url(""),
            "https://novelight.net/book/shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you",
        )

    def test_parse_arguments_info(self):
        # 1. Flag without argument
        args1 = parse_arguments(["--info"])
        self.assertTrue(args1.fetch_info)

        # 2. Flag with URL value
        args2 = parse_arguments(["--info", "https://novelight.net/book/test-novel"])
        self.assertEqual(args2.fetch_info, "https://novelight.net/book/test-novel")

        # 3. --url and --fetch-info alias
        args3 = parse_arguments(["--url", "https://novelight.net/book/test-novel", "--fetch-info"])
        self.assertEqual(args3.url, "https://novelight.net/book/test-novel")
        self.assertTrue(args3.fetch_info)

    def test_parse_arguments_positional_url(self):
        # 1. Plain positional URL
        args1 = parse_arguments(["https://novelight.net/book/ghost-story"])
        self.assertEqual(args1.url, "https://novelight.net/book/ghost-story")

        # 2. Positional URL with --fast
        args2 = parse_arguments(["https://novelight.net/book/ghost-story", "--fast"])
        self.assertEqual(args2.url, "https://novelight.net/book/ghost-story")
        self.assertTrue(args2.fast)

        # 3. Flag before positional URL
        args3 = parse_arguments(["--fast", "https://novelight.net/book/ghost-story"])
        self.assertEqual(args3.url, "https://novelight.net/book/ghost-story")
        self.assertTrue(args3.fast)

        # 4. Positional URL with --info
        args4 = parse_arguments(["https://novelight.net/book/ghost-story", "--info"])
        self.assertEqual(args4.url, "https://novelight.net/book/ghost-story")
        self.assertTrue(args4.fetch_info)

    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_page")
    def test_fetch_novel_details(self, mock_fetch_page, mock_fetch_index):
        from scraper import fetch_novel_details
        sample_html = """
        <html>
        <head><title>Test Book - Read Online Free · Novelight</title></head>
        <body>
            <h1 class="clamp">Test Book Title</h1>
            <a href="/book/chapter/5001" class="read-btn">Start Reading</a>
            <script>const BOOK_ID = "123";</script>
        </body>
        </html>
        """
        mock_fetch_page.return_value = sample_html

        ch1 = ChapterMeta("5001", 1, "1", "Intro", "", "", is_locked=False)
        ch2 = ChapterMeta("5002", 1, "2", "Middle", "", "", is_locked=False)
        ch3 = ChapterMeta("5003", 2, "3", "Locked End", "", "", is_locked=True)
        mock_fetch_index.return_value = [ch1, ch2, ch3]

        info, chapters = fetch_novel_details("https://novelight.net/book/test-book")
        self.assertEqual(info.title, "Test Book Title")
        self.assertEqual(info.book_id, "123")
        self.assertEqual(info.first_chapter_id, "5001")
        self.assertEqual(info.total_chapters, 3)
        self.assertEqual(info.free_chapters_count, 2)
        self.assertEqual(info.locked_chapters_count, 1)
        self.assertEqual(info.volumes_count, 2)
        self.assertAlmostEqual(info.free_percentage, 66.66666666666667)
        self.assertIn("Ch. 1 - Ch. 2", info.free_chapter_range)
        self.assertIn("Ch. 3 - Ch. 3", info.locked_chapter_range)

    @patch("scraper.display_novel_info_flow")
    def test_scrape_novel_info_flow_called(self, mock_display_flow):
        args = parse_arguments(["--info", "https://novelight.net/book/my-slug"])
        scrape_novel(args)
        mock_display_flow.assert_called_once_with("https://novelight.net/book/my-slug")

    def test_slugify(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")
        self.assertEqual(slugify("Shut Up, Malevolent Dragon!"), "shut-up-malevolent-dragon")
        self.assertEqual(slugify("  Special @#% Characters & Spaces  "), "special-characters-spaces")
        self.assertEqual(slugify(""), "novel")
        self.assertEqual(slugify(None), "novel")

    def test_extract_novel_slug(self):
        # Novelight URL
        self.assertEqual(
            extract_novel_slug(url="https://novelight.net/book/ghost-story"),
            "ghost-story",
        )
        self.assertEqual(
            extract_novel_slug(url="https://novelight.net/book/ghost-story/"),
            "ghost-story",
        )
        self.assertEqual(
            extract_novel_slug(url="https://novelight.net/book/ghost-story?tab=ch"),
            "ghost-story",
        )
        # Fenrirealm URL
        self.assertEqual(
            extract_novel_slug(url="https://fenrirealm.com/series/absolute-regression/1"),
            "absolute-regression",
        )
        self.assertEqual(
            extract_novel_slug(url="https://fenrirealm.com/series/my-cool-series"),
            "my-cool-series",
        )
        # Fallback to default_slug
        self.assertEqual(
            extract_novel_slug(default_slug="my-default-series"),
            "my-default-series",
        )
        # Fallback to title
        self.assertEqual(
            extract_novel_slug(title="Solo Leveling Ragnarok"),
            "solo-leveling-ragnarok",
        )
        # Empty fallback
        self.assertEqual(extract_novel_slug(), "novel")

    def test_resolve_output_dir(self):
        # Default output dir nests under <base_default>/<slug>
        self.assertEqual(
            resolve_output_dir("output", "my-slug", base_default="output"),
            os.path.join("output", "my-slug"),
        )
        self.assertEqual(
            resolve_output_dir(None, "my-slug", base_default="output"),
            os.path.join("output", "my-slug"),
        )
        # Custom output dir preserved
        custom = os.path.join(self.test_dir, "custom_novel")
        self.assertEqual(
            resolve_output_dir(custom, "my-slug", base_default="output"),
            custom,
        )

    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_json")
    @patch("scraper.build_epub")
    def test_scrape_novel_default_output_dir_nested(self, mock_build_epub, mock_fetch_json, mock_fetch_index):
        import config
        ch1 = ChapterMeta("150473", 1, "1", "First Chapter", "1 vol. 1 chapter - First Chapter", "", is_locked=False)
        mock_fetch_index.return_value = [ch1]
        mock_fetch_json.return_value = {"content": '<div class="chapter-text"><div>Paragraph</div></div>'}
        mock_build_epub.return_value = "dummy.epub"

        with patch("config.OUTPUT_DIR", self.test_dir):
            args = parse_arguments([
                "--output-dir", self.test_dir,
                "--max-chapters", "1",
                "--delay", "0.0",
                "--jitter", "0.0",
            ])
            scrape_novel(args)
            expected_dir = os.path.join(self.test_dir, config.BOOK_SLUG)
            self.assertEqual(args.output_dir, expected_dir)
            self.assertTrue(os.path.exists(os.path.join(expected_dir, "chapters")))

    def test_detect_source(self):
        # Fenrirealm URLs
        self.assertEqual(
            detect_source("https://fenrirealm.com/series/absolute-regression"),
            "fenrirealm",
        )
        self.assertEqual(
            detect_source("https://fenrirealm.com/series/absolute-regression/1"),
            "fenrirealm",
        )
        self.assertEqual(
            detect_source("HTTPS://WWW.FENRIREALM.COM/SERIES/TEST"),
            "fenrirealm",
        )
        # Novelight URLs
        self.assertEqual(
            detect_source("https://novelight.net/book/ghost-story"),
            "novelight",
        )
        self.assertEqual(
            detect_source("https://novelight.net/book/337"),
            "novelight",
        )
        self.assertEqual(
            detect_source("HTTPS://NOVELIGHT.NET/BOOK/TEST"),
            "novelight",
        )
        # Unknown domain / non-URL fallback to default
        self.assertEqual(detect_source("https://example.com/some-novel"), "novelight")
        self.assertEqual(detect_source("337"), "novelight")
        self.assertEqual(detect_source(""), "novelight")
        self.assertEqual(detect_source(None), "novelight")
        self.assertEqual(detect_source("https://example.com", default="custom"), "custom")

    def test_parse_arguments_source_auto_detection(self):
        # Default with no args falls back to novelight
        args = parse_arguments([])
        self.assertEqual(args.source, "novelight")

        # Positional URLs
        args = parse_arguments(["https://fenrirealm.com/series/absolute-regression"])
        self.assertEqual(args.source, "fenrirealm")

        args = parse_arguments(["https://novelight.net/book/ghost-story"])
        self.assertEqual(args.source, "novelight")

        # --url flag
        args = parse_arguments(["--url", "https://fenrirealm.com/series/absolute-regression"])
        self.assertEqual(args.source, "fenrirealm")

        args = parse_arguments(["--url", "https://novelight.net/book/ghost-story"])
        self.assertEqual(args.source, "novelight")

        # Explicit --source auto
        args = parse_arguments(["--source", "auto", "https://fenrirealm.com/series/test"])
        self.assertEqual(args.source, "fenrirealm")

        args = parse_arguments(["--source", "auto", "https://novelight.net/book/test"])
        self.assertEqual(args.source, "novelight")

        args = parse_arguments(["--source", "auto"])
        self.assertEqual(args.source, "novelight")

        # Explicit override takes precedence over URL
        args = parse_arguments(["--source", "fenrirealm", "https://novelight.net/book/test"])
        self.assertEqual(args.source, "fenrirealm")

        args = parse_arguments(["--source", "novelight", "https://fenrirealm.com/series/test"])
        self.assertEqual(args.source, "novelight")

        # --info with fenrirealm URL
        args = parse_arguments(["--info", "https://fenrirealm.com/series/test"])
        self.assertEqual(args.source, "fenrirealm")

    @patch("fenrirealm.scraper.scrape_fenrirealm")
    def test_scrape_novel_dispatches_fenrirealm_with_auto_source(self, mock_scrape_fenrirealm):
        args = parse_arguments(["https://fenrirealm.com/series/absolute-regression", "--max-chapters", "1"])
        self.assertEqual(args.source, "fenrirealm")
        scrape_novel(args)
        mock_scrape_fenrirealm.assert_called_once_with(args)

    @patch("fenrirealm.scraper.fetch_chapter_html")
    @patch("fenrirealm.scraper.build_epub")
    def test_scrape_fenrirealm_default_output_dir_nested(self, mock_build_epub, mock_fetch_html):
        from fenrirealm.scraper import scrape_fenrirealm
        mock_fetch_html.return_value = (
            "<html><body><div class='chapter-view'>"
            "<div class='text-center'><h2>Absolute Regression - Ch 1</h2></div>"
            "<div class='reader-area touch-manipulation'><p>Paragraph 1</p></div>"
            "</div></body></html>"
        )
        mock_build_epub.return_value = "dummy.epub"

        with patch("config.OUTPUT_DIR", self.test_dir):
            args = parse_arguments([
                "--source", "fenrirealm",
                "--output-dir", self.test_dir,
                "--max-chapters", "1",
                "--delay", "0.0",
                "--jitter", "0.0",
            ])
            scrape_fenrirealm(args)
            expected_dir = os.path.join(self.test_dir, "absolute-regression")
            self.assertEqual(args.output_dir, expected_dir)
            self.assertTrue(os.path.exists(os.path.join(expected_dir, "chapters")))


if __name__ == "__main__":
    unittest.main()

