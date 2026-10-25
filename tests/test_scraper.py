"""
Unit tests for the scraper orchestration module.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from parser import Chapter
from scraper import (
    compute_chapter_url,
    is_chapter_downloaded,
    parse_arguments,
    scrape_novel,
)


class TestScraper(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_compute_chapter_url(self):
        url1 = compute_chapter_url("5320155", 7173977)
        url2 = compute_chapter_url("5320155", 7173996)

        self.assertEqual(url1, "https://www.lolobun.com/n/5320155/7173977")
        self.assertEqual(url2, "https://www.lolobun.com/n/5320155/7173996")

    def test_is_chapter_downloaded(self):
        self.assertFalse(is_chapter_downloaded(1, self.test_dir))

        filepath = os.path.join(self.test_dir, "chapter_0001.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("<html>content</html>")

        self.assertTrue(is_chapter_downloaded(1, self.test_dir))

    @patch("sys.argv", ["scraper.py", "--start", "5", "--chapters", "10", "--delay", "0.5"])
    def test_parse_arguments(self):
        args = parse_arguments()
        self.assertEqual(args.start, 5)
        self.assertEqual(args.chapters, 10)
        self.assertEqual(args.delay, 0.5)
        self.assertFalse(args.force)

    @patch("scraper.fetch_page")
    @patch("scraper.build_epub")
    def test_scrape_novel_mocked_run(self, mock_build_epub, mock_fetch):
        # Chapter 1 points to non-sequential Chapter 2 endpoint (7173996)
        ch1_html = """
        <html>
            <body>
                <div class="title">Chapter 1: The Quest Begins</div>
                <div class="text-content-box">
                    <p>Leon was trapped in chains.</p>
                </div>
                <div class="btn next" id="bottom-open-next-btn">
                    <a href="/n/5320155/7173996" name="next">Next episode</a>
                    <img class="next-icon" src="/image/reader/icon_next_chapter.png" alt="prev icon" />
                </div>
            </body>
        </html>
        """
        ch2_html = """
        <html>
            <body>
                <div class="title">Chapter 2: The Escape</div>
                <div class="text-content-box">
                    <p>Leon broke free.</p>
                </div>
                <div class="btn next" id="bottom-open-next-btn">
                    <a href="/n/5320155/7174001" name="next">Next episode</a>
                </div>
            </body>
        </html>
        """
        mock_fetch.side_effect = [ch1_html, ch2_html]
        mock_build_epub.return_value = os.path.join(self.test_dir, "novel.epub")

        args = MagicMock()
        args.start = 1
        args.chapters = 2
        args.novel_id = "5320155"
        args.first_chapter_id = 7173977
        args.start_url = None
        args.delay = 0.0
        args.jitter = 0.0
        args.force = False
        args.build_only = False
        args.no_epub = False
        args.output_dir = self.test_dir
        args.epub_filename = "novel.epub"
        args.title = "Novel Title"
        args.author = "Author"
        args.lang = "en"
        args.cover = None
        args.css = None

        scrape_novel(args)

        # Ensure chapter files were saved
        chapters_dir = os.path.join(self.test_dir, "chapters")
        self.assertTrue(os.path.exists(os.path.join(chapters_dir, "chapter_0001.html")))
        self.assertTrue(os.path.exists(os.path.join(chapters_dir, "chapter_0002.html")))

        # Verify fetch was called with the initial URL then the dynamically parsed next link
        mock_fetch.assert_any_call("https://www.lolobun.com/n/5320155/7173977")
        mock_fetch.assert_any_call("https://www.lolobun.com/n/5320155/7173996")
        mock_build_epub.assert_called_once()

    @patch("scraper.fetch_page")
    @patch("scraper.build_epub")
    def test_scrape_novel_stops_when_no_next_link(self, mock_build_epub, mock_fetch):
        # Single chapter with no next episode button
        last_ch_html = """
        <html>
            <body>
                <div class="title">Chapter 1: The Only Chapter</div>
                <div class="text-content-box">
                    <p>The story ends here.</p>
                </div>
            </body>
        </html>
        """
        mock_fetch.return_value = last_ch_html
        mock_build_epub.return_value = os.path.join(self.test_dir, "novel.epub")

        args = MagicMock()
        args.start = 1
        args.chapters = 5  # Requested 5, but should stop after 1
        args.novel_id = "5320155"
        args.first_chapter_id = 7173977
        args.start_url = None
        args.delay = 0.0
        args.jitter = 0.0
        args.force = False
        args.build_only = False
        args.no_epub = False
        args.output_dir = self.test_dir
        args.epub_filename = "novel.epub"
        args.title = "Novel Title"
        args.author = "Author"
        args.lang = "en"
        args.cover = None
        args.css = None

        scrape_novel(args)

        chapters_dir = os.path.join(self.test_dir, "chapters")
        self.assertTrue(os.path.exists(os.path.join(chapters_dir, "chapter_0001.html")))
        self.assertFalse(os.path.exists(os.path.join(chapters_dir, "chapter_0002.html")))
        self.assertEqual(mock_fetch.call_count, 1)
        mock_build_epub.assert_called_once()


if __name__ == "__main__":
    unittest.main()
