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
        self.assertIsNone(args.title)
        self.assertIsNone(args.author)
        self.assertIsNone(args.epub_filename)

    def test_parse_arguments_metadata_explicit(self):
        args = parse_arguments([
            "--title", "Custom Title",
            "--author", "Custom Author",
            "--epub-filename", "custom.epub",
        ])
        self.assertEqual(args.title, "Custom Title")
        self.assertEqual(args.author, "Custom Author")
        self.assertEqual(args.epub_filename, "custom.epub")

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
        ch2 = ChapterMeta("150474", 2, "2", "Second Chapter", "2 vol. 2 chapter - Second Chapter", "", is_locked=False)
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
        vol2_dir = os.path.join(chapters_dir, "vol_02")
        self.assertTrue(os.path.exists(os.path.join(vol1_dir, "chapter_0001.html")))
        self.assertTrue(os.path.exists(os.path.join(vol2_dir, "chapter_0002.html")))
        mock_build_epub.assert_called_once()
        self.assertTrue(mock_build_epub.call_args[1].get("use_volumes"))

    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_json")
    @patch("scraper.build_epub")
    def test_scrape_novel_flat_chapters_run(self, mock_build_epub, mock_fetch_json, mock_fetch_index):
        # Novel with single volume or no multi-volume structure should save flat chapters without vol_XX directories
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
        # Ensure flat chapter files exist directly under chapters_dir
        self.assertTrue(os.path.exists(os.path.join(chapters_dir, "chapter_0001.html")))
        self.assertTrue(os.path.exists(os.path.join(chapters_dir, "chapter_0002.html")))
        # Ensure no artificial vol_01 directory was created
        self.assertFalse(os.path.exists(os.path.join(chapters_dir, "vol_01")))
        mock_build_epub.assert_called_once()
        self.assertFalse(mock_build_epub.call_args[1].get("use_volumes"))

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

    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_page")
    def test_fetch_novel_details_flat_novel(self, mock_fetch_page, mock_fetch_index):
        """Issue 6: Flat novels with only 1 volume report volumes_count = 0 and flat chapter titles."""
        from scraper import fetch_novel_details
        sample_html = """
        <html>
        <body>
            <h1 class="clamp">Flat Book Title</h1>
            <a href="/book/chapter/6001" class="read-btn">Start Reading</a>
            <script>const BOOK_ID = "456";</script>
        </body>
        </html>
        """
        mock_fetch_page.return_value = sample_html

        ch1 = ChapterMeta("6001", 1, "1", "Flat One", "1 vol. 1 chapter - Flat One", "", is_locked=False)
        ch2 = ChapterMeta("6002", 1, "2", "Flat Two", "1 vol. 2 chapter - Flat Two", "", is_locked=False)
        mock_fetch_index.return_value = [ch1, ch2]

        info, chapters = fetch_novel_details("https://novelight.net/book/flat-book")
        self.assertEqual(info.title, "Flat Book Title")
        self.assertEqual(info.total_chapters, 2)
        # volumes_count must be 0 for flat novels (no artificial volume)
        self.assertEqual(info.volumes_count, 0)
        # Chapters must be normalized to volume 0
        self.assertEqual(chapters[0].volume, 0)
        self.assertEqual(chapters[1].volume, 0)
        self.assertEqual(info.first_chapter_title, "Ch. 1 - Flat One")
        self.assertEqual(info.latest_chapter_title, "Ch. 2 - Flat Two")

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
        # Fenrir Realm URL
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
        # Fenrir Realm URLs
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

    @patch("fenrirealm.parser.fetch_fenrirealm_info")
    def test_display_novel_info_flow_dispatches_to_fenrirealm(self, mock_fetch_info):
        """display_novel_info_flow() calls fetch_fenrirealm_info for fenrirealm.com URLs."""
        from scraper import display_novel_info_flow
        from parser import NovelInfo
        mock_info = NovelInfo(
            url="https://fenrirealm.com/series/absolute-regression",
            book_id="absolute-regression",
            title="Absolute Regression",
            first_chapter_id="1",
        )
        mock_fetch_info.return_value = mock_info

        # Should not raise; just verify the right function was called
        with patch("scraper.display_novel_info"):
            display_novel_info_flow("https://fenrirealm.com/series/absolute-regression")
        mock_fetch_info.assert_called_once_with("https://fenrirealm.com/series/absolute-regression")

    @patch("scraper.fetch_novel_details")
    def test_display_novel_info_flow_uses_novelight_for_novelight_urls(self, mock_fetch_details):
        """display_novel_info_flow() calls fetch_novel_details for novelight.net URLs."""
        from scraper import display_novel_info_flow
        from parser import NovelInfo
        mock_info = NovelInfo(
            url="https://novelight.net/book/ghost-story",
            book_id="123",
            title="Ghost Story",
            first_chapter_id="456",
        )
        mock_fetch_details.return_value = (mock_info, [])

        with patch("scraper.display_novel_info"):
            display_novel_info_flow("https://novelight.net/book/ghost-story")
        mock_fetch_details.assert_called_once()

    @patch("fenrirealm.parser.fetch_fenrirealm_info")
    @patch("scraper.display_novel_info")
    def test_scrape_novel_info_fenrirealm_dispatch(self, mock_display_info, mock_fetch_info):
        from parser import NovelInfo
        mock_info = NovelInfo(
            url="https://fenrirealm.com/series/absolute-regression",
            book_id="absolute-regression",
            title="Absolute Regression",
            first_chapter_id="1",
        )
        mock_fetch_info.return_value = mock_info

        # 1. Positional / flag URL auto-detected
        args = parse_arguments(["--info", "https://fenrirealm.com/series/absolute-regression"])
        scrape_novel(args)
        mock_fetch_info.assert_called_with("https://fenrirealm.com/series/absolute-regression")

        # 2. --source fenrirealm with bare slug
        mock_fetch_info.reset_mock()
        args = parse_arguments(["--source", "fenrirealm", "--info", "absolute-regression"])
        scrape_novel(args)
        mock_fetch_info.assert_called_with("https://fenrirealm.com/series/absolute-regression")

        # 3. --source fenrirealm with bare --info
        mock_fetch_info.reset_mock()
        args = parse_arguments(["--source", "fenrirealm", "--info"])
        scrape_novel(args)
        mock_fetch_info.assert_called_once()
        self.assertIn("fenrirealm.com", mock_fetch_info.call_args[0][0])

    @patch("scraper.fetch_novel_details")
    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_json")
    @patch("scraper.build_epub")
    def test_scrape_novel_dynamic_metadata_from_fetched_info(
        self, mock_build_epub, mock_fetch_json, mock_fetch_index, mock_fetch_details
    ):
        from parser import NovelInfo
        info = NovelInfo(
            url="https://novelight.net/book/solo-leveling",
            book_id="999",
            title="Solo Leveling",
            author="Chugong",
            first_chapter_id="1001",
            description="A hunter awakens to become the shadow monarch.",
        )
        ch1 = ChapterMeta("1001", 1, "1", "Prologue", "1 vol. 1 chapter - Prologue", "", is_locked=False)
        mock_fetch_details.return_value = (info, [ch1])
        mock_fetch_index.return_value = [ch1]
        mock_fetch_json.return_value = {"content": "<div>Awakening</div>"}
        mock_build_epub.return_value = "solo-leveling.epub"

        args = parse_arguments([
            "--url", "https://novelight.net/book/solo-leveling",
            "--output-dir", self.test_dir,
            "--max-chapters", "1",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])
        scrape_novel(args)

        self.assertEqual(args.title, "Solo Leveling")
        self.assertEqual(args.author, "Chugong")
        self.assertEqual(args.epub_filename, "solo-leveling.epub")

        mock_build_epub.assert_called_once()
        call_kwargs = mock_build_epub.call_args.kwargs
        self.assertEqual(call_kwargs["book_title"], "Solo Leveling")
        self.assertEqual(call_kwargs["book_author"], "Chugong")
        self.assertEqual(call_kwargs["epub_filename"], "solo-leveling.epub")
        self.assertEqual(call_kwargs["book_description"], "A hunter awakens to become the shadow monarch.")

    @patch("scraper.fetch_novel_details")
    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_json")
    @patch("scraper.build_epub")
    def test_scrape_novel_explicit_metadata_overrides_fetched_info(
        self, mock_build_epub, mock_fetch_json, mock_fetch_index, mock_fetch_details
    ):
        from parser import NovelInfo
        info = NovelInfo(
            url="https://novelight.net/book/solo-leveling",
            book_id="999",
            title="Solo Leveling",
            author="Chugong",
            first_chapter_id="1001",
        )
        ch1 = ChapterMeta("1001", 1, "1", "Prologue", "1 vol. 1 chapter - Prologue", "", is_locked=False)
        mock_fetch_details.return_value = (info, [ch1])
        mock_fetch_index.return_value = [ch1]
        mock_fetch_json.return_value = {"content": "<div>Awakening</div>"}
        mock_build_epub.return_value = "custom.epub"

        args = parse_arguments([
            "--url", "https://novelight.net/book/solo-leveling",
            "--output-dir", self.test_dir,
            "--title", "Custom Title",
            "--author", "Custom Author",
            "--epub-filename", "custom.epub",
            "--max-chapters", "1",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])
        scrape_novel(args)

        self.assertEqual(args.title, "Custom Title")
        self.assertEqual(args.author, "Custom Author")
        self.assertEqual(args.epub_filename, "custom.epub")

        mock_build_epub.assert_called_once()
        call_kwargs = mock_build_epub.call_args.kwargs
        self.assertEqual(call_kwargs["book_title"], "Custom Title")
        self.assertEqual(call_kwargs["book_author"], "Custom Author")
        self.assertEqual(call_kwargs["epub_filename"], "custom.epub")

    @patch("fenrirealm.scraper.fetch_chapter_html")
    @patch("fenrirealm.scraper.build_epub")
    def test_scrape_fenrirealm_dynamic_metadata(self, mock_build_epub, mock_fetch_html):
        from fenrirealm.scraper import scrape_fenrirealm
        mock_fetch_html.return_value = (
            "<html><body><div class='chapter-view'>"
            "<div class='text-center'><h2>Absolute Regression - Ch 1</h2></div>"
            "<div class='reader-area touch-manipulation'><p>Paragraph 1</p></div>"
            "</div></body></html>"
        )
        mock_build_epub.return_value = "absolute-regression.epub"

        args = parse_arguments([
            "--source", "fenrirealm",
            "--output-dir", self.test_dir,
            "--max-chapters", "1",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])
        scrape_fenrirealm(args)

        self.assertEqual(args.title, "Absolute Regression")
        self.assertEqual(args.author, "Unknown")
        self.assertEqual(args.epub_filename, "absolute-regression.epub")

        mock_build_epub.assert_called_once()
        call_kwargs = mock_build_epub.call_args.kwargs
        self.assertEqual(call_kwargs["book_title"], "Absolute Regression")
        self.assertEqual(call_kwargs["epub_filename"], "absolute-regression.epub")

    @patch("scraper.download_cover_image")
    @patch("scraper.fetch_novel_details")
    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_json")
    @patch("scraper.build_epub")
    def test_scrape_novel_auto_downloads_and_embeds_cover(
        self, mock_build_epub, mock_fetch_json, mock_fetch_index, mock_fetch_details, mock_download_cover
    ):
        from parser import NovelInfo
        info = NovelInfo(
            url="https://novelight.net/book/solo-leveling",
            book_id="999",
            title="Solo Leveling",
            author="Chugong",
            first_chapter_id="1001",
            cover_url="https://novelight.net/media/book/poster/solo.jpg",
        )
        ch1 = ChapterMeta("1001", 1, "1", "Prologue", "1 vol. 1 chapter - Prologue", "", is_locked=False)
        mock_fetch_details.return_value = (info, [ch1])
        mock_fetch_index.return_value = [ch1]
        mock_fetch_json.return_value = {"content": "<div>Awakening</div>"}
        mock_build_epub.return_value = "solo-leveling.epub"

        expected_cover_path = os.path.join(self.test_dir, "solo-leveling", "cover.jpg")
        mock_download_cover.return_value = expected_cover_path

        args = parse_arguments([
            "--url", "https://novelight.net/book/solo-leveling",
            "--output-dir", self.test_dir,
            "--max-chapters", "1",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])
        scrape_novel(args)

        mock_download_cover.assert_called_once()
        call_kwargs = mock_download_cover.call_args.kwargs
        self.assertEqual(call_kwargs["cover_url"], "https://novelight.net/media/book/poster/solo.jpg")

        mock_build_epub.assert_called_once()
        epub_kwargs = mock_build_epub.call_args.kwargs
        self.assertEqual(epub_kwargs["cover_image"], expected_cover_path)

    @patch("scraper.download_cover_image")
    @patch("scraper.fetch_novel_details")
    @patch("scraper.fetch_chapter_index")
    @patch("scraper.fetch_json")
    @patch("scraper.build_epub")
    def test_scrape_novel_explicit_cover_bypasses_auto_download(
        self, mock_build_epub, mock_fetch_json, mock_fetch_index, mock_fetch_details, mock_download_cover
    ):
        from parser import NovelInfo
        info = NovelInfo(
            url="https://novelight.net/book/solo-leveling",
            book_id="999",
            title="Solo Leveling",
            author="Chugong",
            first_chapter_id="1001",
            cover_url="https://novelight.net/media/book/poster/solo.jpg",
        )
        ch1 = ChapterMeta("1001", 1, "1", "Prologue", "1 vol. 1 chapter - Prologue", "", is_locked=False)
        mock_fetch_details.return_value = (info, [ch1])
        mock_fetch_index.return_value = [ch1]
        mock_fetch_json.return_value = {"content": "<div>Awakening</div>"}
        mock_build_epub.return_value = "solo-leveling.epub"

        args = parse_arguments([
            "--url", "https://novelight.net/book/solo-leveling",
            "--output-dir", self.test_dir,
            "--cover", "custom_cover.png",
            "--max-chapters", "1",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])
        scrape_novel(args)

        mock_download_cover.assert_not_called()
        mock_build_epub.assert_called_once()
        epub_kwargs = mock_build_epub.call_args.kwargs
        self.assertEqual(epub_kwargs["cover_image"], "custom_cover.png")

    @patch("fenrirealm.scraper.download_cover_image")
    @patch("fenrirealm.parser.fetch_fenrirealm_info")
    @patch("fenrirealm.scraper.fetch_chapter_html")
    @patch("fenrirealm.scraper.build_epub")
    def test_scrape_fenrirealm_auto_downloads_and_embeds_cover(
        self, mock_build_epub, mock_fetch_html, mock_fetch_info, mock_download_cover
    ):
        from parser import NovelInfo
        from fenrirealm.scraper import scrape_fenrirealm

        mock_fetch_info.return_value = NovelInfo(
            url="https://fenrirealm.com/series/absolute-regression",
            book_id="absolute-regression",
            title="Absolute Regression",
            author="Author Name",
            first_chapter_id="1",
            cover_url="https://fenrirealm.com/media/covers/regression.jpg",
        )
        mock_fetch_html.return_value = (
            "<html><body><div class='chapter-view'>"
            "<div class='text-center'><h2>Absolute Regression - Ch 1</h2></div>"
            "<div class='reader-area touch-manipulation'><p>Paragraph 1</p></div>"
            "</div></body></html>"
        )
        expected_cover_path = os.path.join(self.test_dir, "absolute-regression", "cover.jpg")
        mock_download_cover.return_value = expected_cover_path
        mock_build_epub.return_value = "absolute-regression.epub"

        args = parse_arguments([
            "https://fenrirealm.com/series/absolute-regression",
            "--output-dir", self.test_dir,
            "--max-chapters", "1",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])
        scrape_fenrirealm(args)

        mock_download_cover.assert_called_once()
        self.assertEqual(
            mock_download_cover.call_args.kwargs["cover_url"],
            "https://fenrirealm.com/media/covers/regression.jpg",
        )
        mock_build_epub.assert_called_once()
        epub_kwargs = mock_build_epub.call_args.kwargs
        self.assertEqual(epub_kwargs["cover_image"], expected_cover_path)

    @patch("fenrirealm.scraper.fetch_chapter_html")
    @patch("fenrirealm.scraper.build_epub")
    def test_scrape_fenrirealm_detects_existing_cover_file(
        self, mock_build_epub, mock_fetch_html
    ):
        from fenrirealm.scraper import scrape_fenrirealm

        cover_path = os.path.join(self.test_dir, "cover.jpg")
        with open(cover_path, "wb") as f:
            f.write(b"existing-cover-bytes")

        mock_fetch_html.return_value = (
            "<html><body><div class='chapter-view'>"
            "<div class='text-center'><h2>Absolute Regression - Ch 1</h2></div>"
            "<div class='reader-area touch-manipulation'><p>Paragraph 1</p></div>"
            "</div></body></html>"
        )
        mock_build_epub.return_value = "absolute-regression.epub"

        args = parse_arguments([
            "--source", "fenrirealm",
            "--output-dir", self.test_dir,
            "--max-chapters", "1",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])
        scrape_fenrirealm(args)

        mock_build_epub.assert_called_once()
        epub_kwargs = mock_build_epub.call_args.kwargs
        self.assertEqual(epub_kwargs["cover_image"], cover_path)

    @patch("fenrirealm.scraper.fetch_chapter_html")
    @patch("fenrirealm.scraper.build_epub")
    def test_scrape_fenrirealm_explicit_cover_overrides(
        self, mock_build_epub, mock_fetch_html
    ):
        from fenrirealm.scraper import scrape_fenrirealm

        mock_fetch_html.return_value = (
            "<html><body><div class='chapter-view'>"
            "<div class='text-center'><h2>Absolute Regression - Ch 1</h2></div>"
            "<div class='reader-area touch-manipulation'><p>Paragraph 1</p></div>"
            "</div></body></html>"
        )
        mock_build_epub.return_value = "absolute-regression.epub"

        args = parse_arguments([
            "--source", "fenrirealm",
            "--output-dir", self.test_dir,
            "--cover", "my_custom_cover.jpg",
            "--max-chapters", "1",
            "--delay", "0.0",
            "--jitter", "0.0",
        ])
        scrape_fenrirealm(args)

        mock_build_epub.assert_called_once()
        epub_kwargs = mock_build_epub.call_args.kwargs
        self.assertEqual(epub_kwargs["cover_image"], "my_custom_cover.jpg")


if __name__ == "__main__":
    unittest.main()

