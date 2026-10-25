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


if __name__ == "__main__":
    unittest.main()
