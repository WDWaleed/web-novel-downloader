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
        url1 = compute_chapter_url("5320155", 7173977, 1)
        url2 = compute_chapter_url("5320155", 7173977, 2)
        url3 = compute_chapter_url("5320155", 7173977, 3)

        self.assertEqual(url1, "https://www.lolobun.com/n/5320155/7173977")
        self.assertEqual(url2, "https://www.lolobun.com/n/5320155/7173976")
        self.assertEqual(url3, "https://www.lolobun.com/n/5320155/7173975")

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
        mock_fetch.return_value = """
        <html>
            <body>
                <div class="title">Chapter 1: The Quest Begins</div>
                <div class="text-content-box">
                    <p>Leon was trapped in chains.</p>
                </div>
            </body>
        </html>
        """
        mock_build_epub.return_value = os.path.join(self.test_dir, "novel.epub")

        args = MagicMock()
        args.start = 1
        args.chapters = 2
        args.novel_id = "5320155"
        args.first_chapter_id = 7173977
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
        mock_build_epub.assert_called_once()


if __name__ == "__main__":
    unittest.main()
