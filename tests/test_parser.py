"""
Unit tests for the Novelight parser module.
"""

import unittest

from parser import (
    Chapter,
    ChapterMeta,
    clean_chapter_content,
    is_chapter_content_empty,
    normalize_title,
    parse_chapter,
    parse_chapter_list,
    parse_chapter_title,
)


class TestParser(unittest.TestCase):
    def test_parse_chapter_title_standard(self):
        vol, ch, title = parse_chapter_title(
            "1 vol. 1 chapter - After defeat and capture, someone is pregnant"
        )
        self.assertEqual(vol, 1)
        self.assertEqual(ch, "1")
        self.assertEqual(title, "After defeat and capture, someone is pregnant")

    def test_parse_chapter_title_no_space_dash(self):
        vol, ch, title = parse_chapter_title("12 vol. 78 chapter -Gag")
        self.assertEqual(vol, 12)
        self.assertEqual(ch, "78")
        self.assertEqual(title, "Gag")

    def test_parse_chapter_title_sub_chapter(self):
        vol, ch, title = parse_chapter_title(
            "12 vol. 68.1 chapter - Silver Radiance of the Night (17)"
        )
        self.assertEqual(vol, 12)
        self.assertEqual(ch, "68.1")
        self.assertEqual(title, "Silver Radiance of the Night (17)")

    def test_parse_chapter_title_no_subtitle(self):
        vol, ch, title = parse_chapter_title("5 vol. 10 chapter")
        self.assertEqual(vol, 5)
        self.assertEqual(ch, "10")
        self.assertEqual(title, "")

    def test_parse_chapter_title_colon_separator(self):
        vol, ch, title = parse_chapter_title("3 vol. 5 chapter: The Grand Arrival")
        self.assertEqual(vol, 3)
        self.assertEqual(ch, "5")
        self.assertEqual(title, "The Grand Arrival")

    def test_parse_chapter_title_fallback(self):
        vol, ch, title = parse_chapter_title("Special Side Story: The Festival")
        self.assertEqual(vol, 1)
        self.assertEqual(ch, "1")
        self.assertEqual(title, "Special Side Story: The Festival")

    def test_chapter_meta_display_title(self):
        meta_with_sub = ChapterMeta(
            chapter_id="150473",
            volume=9,
            chapter_number="78",
            title="Dragon Heroic Spirit (6)",
            raw_title="9 vol. 78 chapter - Dragon Heroic Spirit (6)",
            url="https://novelight.net/book/chapter/150473",
            is_locked=False,
        )
        self.assertEqual(meta_with_sub.display_title, "Vol. 9 Ch. 78 - Dragon Heroic Spirit (6)")

        meta_no_sub = ChapterMeta(
            chapter_id="150474",
            volume=1,
            chapter_number="2",
            title="",
            raw_title="1 vol. 2 chapter",
            url="https://novelight.net/book/chapter/150474",
            is_locked=False,
        )
        self.assertEqual(meta_no_sub.display_title, "Vol. 1 Ch. 2")

    def test_parse_chapter_list(self):
        html = """
        <div class="chapters">
            <a href="/book/chapter/345262" class="chapter ">
                <div class="title">12 vol. 78 chapter - <span>Gag</span></div>
                <div class="chapter-info">
                    <span class="cost"><i class="fa fa-lock"></i></span>
                    <span class="author"><i class="fa fa-user"></i> Santos</span>
                    <span class="date">25.10.2026</span>
                </div>
            </a>
            <a href="/book/chapter/150473" class="chapter ">
                <div class="title">1 vol. 1 chapter - <span>After defeat and capture</span></div>
                <div class="chapter-info">
                    <span class="author"><i class="fa fa-user"></i> Santos</span>
                    <span class="date">20.08.2024</span>
                </div>
            </a>
        </div>
        """
        chapters = parse_chapter_list(html)
        self.assertEqual(len(chapters), 2)

        # Chapter 1 (locked)
        self.assertEqual(chapters[0].chapter_id, "345262")
        self.assertEqual(chapters[0].volume, 12)
        self.assertEqual(chapters[0].chapter_number, "78")
        self.assertEqual(chapters[0].title, "Gag")
        self.assertTrue(chapters[0].is_locked)
        self.assertEqual(chapters[0].translator, "Santos")
        self.assertEqual(chapters[0].date, "25.10.2026")

        # Chapter 2 (unlocked)
        self.assertEqual(chapters[1].chapter_id, "150473")
        self.assertEqual(chapters[1].volume, 1)
        self.assertEqual(chapters[1].chapter_number, "1")
        self.assertEqual(chapters[1].title, "After defeat and capture")
        self.assertFalse(chapters[1].is_locked)
        self.assertEqual(chapters[1].url, "https://novelight.net/book/chapter/150473")

    def test_clean_chapter_content(self):
        content_html = """
        <div class="chapter-text randomclass">
            <div><strong>*Volume 1*</strong></div>
            <div class="advertisment">
                <script>var x = 1;</script>
                <span>Ad content</span>
            </div>
            <div>In the damp and shadowy dungeon, Leon was bound.</div>
            <div></div>
            <div>   </div>
            <div class="ad-banner">Banner</div>
            <div>His shattered armor barely clung to his body.</div>
        </div>
        """
        cleaned = clean_chapter_content(content_html)
        self.assertIn("<p><strong>*Volume 1*</strong></p>", cleaned)
        self.assertIn("<p>In the damp and shadowy dungeon, Leon was bound.</p>", cleaned)
        self.assertIn("<p>His shattered armor barely clung to his body.</p>", cleaned)
        self.assertNotIn("advertisment", cleaned)
        self.assertNotIn("Ad content", cleaned)
        self.assertNotIn("Banner", cleaned)
        self.assertNotIn("var x = 1", cleaned)

    def test_is_chapter_content_empty(self):
        self.assertTrue(is_chapter_content_empty(""))
        self.assertTrue(is_chapter_content_empty('<div class="chapter-text abc"></div>'))
        self.assertTrue(
            is_chapter_content_empty(
                '<div class="chapter-text"><div class="advertisment"><script>1</script></div></div>'
            )
        )
        self.assertFalse(
            is_chapter_content_empty('<div class="chapter-text"><div>Some actual text</div></div>')
        )

    def test_parse_chapter_full(self):
        meta = ChapterMeta(
            chapter_id="150473",
            volume=1,
            chapter_number="1",
            title="After defeat",
            raw_title="1 vol. 1 chapter - After defeat",
            url="https://novelight.net/book/chapter/150473",
            is_locked=False,
        )
        content_html = '<div class="chapter-text"><div>The heroic warrior fell.</div></div>'
        chapter = parse_chapter(content_html, meta=meta, ordinal=1)

        self.assertIsInstance(chapter, Chapter)
        self.assertEqual(chapter.ordinal, 1)
        self.assertEqual(chapter.number, 1)
        self.assertEqual(chapter.volume, 1)
        self.assertEqual(chapter.chapter_number, "1")
        self.assertEqual(chapter.display_title, "Vol. 1 Ch. 1 - After defeat")
        self.assertEqual(chapter.body_html, "<p>The heroic warrior fell.</p>")


if __name__ == "__main__":
    unittest.main()
