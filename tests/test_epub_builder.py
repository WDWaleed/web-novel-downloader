"""
Unit tests for the epub_builder module.
"""

import os
import shutil
import tempfile
import unittest
import zipfile

from epub_builder import (
    build_epub,
    extract_next_url_from_file,
    get_saved_chapter_files,
    save_chapter_file,
)
from parser import Chapter


class TestEpubBuilder(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_chapter_file(self):
        chapter = Chapter(
            number=1,
            raw_title="1 Intro",
            display_title="Chapter 1: Intro",
            body_html="<p>Story begins here.</p>",
            next_url="https://www.lolobun.com/n/5320155/7173976",
        )
        saved_path = save_chapter_file(chapter, output_dir=self.test_dir)
        self.assertTrue(os.path.exists(saved_path))
        with open(saved_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("<h1>Chapter 1: Intro</h1>", content)
        self.assertIn("<p>Story begins here.</p>", content)
        self.assertIn('name="next-chapter-url"', content)

        # Test extract_next_url_from_file
        extracted_url = extract_next_url_from_file(saved_path)
        self.assertEqual(extracted_url, "https://www.lolobun.com/n/5320155/7173976")

    def test_get_saved_chapter_files_sorting(self):
        for num in [10, 2, 1, 20]:
            ch = Chapter(
                number=num,
                raw_title=f"Ch {num}",
                display_title=f"Chapter {num}",
                body_html=f"<p>Chapter {num} text</p>",
            )
            save_chapter_file(ch, output_dir=self.test_dir)

        files = get_saved_chapter_files(self.test_dir)
        expected_order = [
            f"chapter_{num:04d}.html" for num in [1, 2, 10, 20]
        ]
        actual_order = [os.path.basename(f) for f in files]
        self.assertEqual(actual_order, expected_order)

    def test_build_epub_creation(self):
        ch1 = Chapter(1, "1 Start", "Chapter 1: Start", "<p>Paragraph one.</p>")
        ch2 = Chapter(2, "2 Climax", "Chapter 2: Climax", "<p>Paragraph two.</p>")

        epub_path = build_epub(
            chapters=[ch1, ch2],
            output_dir=self.test_dir,
            epub_filename="test_novel.epub",
            book_title="Test Title",
            book_author="Test Author",
            book_language="en",
            css_file=None,
        )

        self.assertTrue(os.path.exists(epub_path))
        self.assertGreater(os.path.getsize(epub_path), 0)

        # EPUB is a ZIP archive containing mimetype and META-INF
        with zipfile.ZipFile(epub_path, "r") as z:
            namelist = z.namelist()
            self.assertIn("mimetype", namelist)
            self.assertIn("META-INF/container.xml", namelist)

    def test_build_epub_empty_raises(self):
        empty_dir = os.path.join(self.test_dir, "empty")
        os.makedirs(empty_dir, exist_ok=True)
        with self.assertRaises(ValueError):
            build_epub(
                chapters=[],
                chapter_files=[],
                output_dir=empty_dir,
            )


if __name__ == "__main__":
    unittest.main()
