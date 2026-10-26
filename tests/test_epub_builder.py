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
    write_pandoc_defaults,
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

    def test_volume_hierarchy_saving_and_compilation(self):
        from parser import ChapterMeta

        meta1 = ChapterMeta(
            chapter_id="101",
            volume=1,
            chapter_number="1",
            title="Beginning",
            raw_title="1 vol. 1 chapter - Beginning",
            url="",
            is_locked=False,
        )
        meta2 = ChapterMeta(
            chapter_id="102",
            volume=2,
            chapter_number="1",
            title="New World",
            raw_title="2 vol. 1 chapter - New World",
            url="",
            is_locked=False,
        )

        ch1 = Chapter(meta=meta1, body_html="<p>Vol 1 Ch 1</p>", display_title="Vol. 1 Ch. 1 - Beginning", ordinal=1)
        ch2 = Chapter(meta=meta2, body_html="<p>Vol 2 Ch 1</p>", display_title="Vol. 2 Ch. 1 - New World", ordinal=2)

        p1 = save_chapter_file(ch1, output_dir=self.test_dir)
        p2 = save_chapter_file(ch2, output_dir=self.test_dir)

        self.assertIn("vol_01", p1)
        self.assertIn("vol_02", p2)
        with open(p1, "r", encoding="utf-8") as f:
            self.assertIn("<h2>Vol. 1 Ch. 1 - Beginning</h2>", f.read())

        files = get_saved_chapter_files(self.test_dir)
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0], p1)
        self.assertEqual(files[1], p2)

        # Build EPUB with volume hierarchy
        epub_path = build_epub(
            chapters=[ch1, ch2],
            output_dir=self.test_dir,
            epub_filename="volume_test.epub",
            book_title="Volume Test Novel",
            css_file=None,
        )
        self.assertTrue(os.path.exists(epub_path))
        self.assertGreater(os.path.getsize(epub_path), 0)

        # Verify pandoc_defaults.yaml was written in output directory
        defaults_file = os.path.join(self.test_dir, "pandoc_defaults.yaml")
        self.assertTrue(os.path.exists(defaults_file))

    def test_write_pandoc_defaults(self):
        defaults_path = os.path.join(self.test_dir, "test_defaults.yaml")
        out_epub = os.path.join(self.test_dir, "test.epub")
        files = ["ch1.html", "ch2.html"]
        written = write_pandoc_defaults(
            filepath=defaults_path,
            output_file=out_epub,
            input_files=files,
            toc_depth=2,
            split_level=2,
            book_title="Test Book",
            book_author="Author X",
            book_language="en",
        )
        self.assertTrue(os.path.exists(written))
        with open(written, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("to: epub3", content)
        self.assertIn("toc-depth: 2", content)
        self.assertIn("title: \"Test Book\"", content)
        self.assertIn("input-files:", content)
        self.assertIn("ch1.html", content)


if __name__ == "__main__":
    unittest.main()

