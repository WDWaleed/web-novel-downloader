"""
Unit tests for the Novelight parser module.
"""

import unittest

from parser import (
    Chapter,
    ChapterMeta,
    clean_chapter_content,
    is_redundant_header_paragraph,
    is_chapter_content_empty,
    normalize_title,
    parse_chapter,
    parse_chapter_list,
    parse_chapter_title,
    strip_watermarks,
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

        # Flat chapter (volume == 0) — Issue 6
        flat_with_sub = ChapterMeta(
            chapter_id="150475",
            volume=0,
            chapter_number="3",
            title="The Beginning of the Journey",
            raw_title="Ch. 3",
            url="https://novelight.net/book/chapter/150475",
            is_locked=False,
        )
        self.assertEqual(flat_with_sub.display_title, "Ch. 3 - The Beginning of the Journey")

        flat_no_sub = ChapterMeta(
            chapter_id="150476",
            volume=0,
            chapter_number="4",
            title="",
            raw_title="Ch. 4",
            url="https://novelight.net/book/chapter/150476",
            is_locked=False,
        )
        self.assertEqual(flat_no_sub.display_title, "Ch. 4")

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
        # Redundant volume header should be stripped
        self.assertNotIn("*Volume 1*", cleaned)
        self.assertNotIn("Volume 1", cleaned)
        self.assertIn("<p>In the damp and shadowy dungeon, Leon was bound.</p>", cleaned)
        self.assertIn("<p>His shattered armor barely clung to his body.</p>", cleaned)
        self.assertNotIn("advertisment", cleaned)
        self.assertNotIn("Ad content", cleaned)
        self.assertNotIn("Banner", cleaned)
        self.assertNotIn("var x = 1", cleaned)

    def test_clean_chapter_content_removes_redundant_chapter_title(self):
        # Chapter 3 scenario: Content starts with "Chapter 3: Now, I’m going to retaliate in kind."
        meta = ChapterMeta(
            chapter_id="150475",
            volume=1,
            chapter_number="3",
            title="Now, I’m going to retaliate in kind.",
            raw_title="1 vol. 3 chapter - Now, I’m going to retaliate in kind.",
            url="https://novelight.net/book/chapter/150475",
            is_locked=False,
        )
        content_html = """
        <div class="chapter-text">
            <div><strong>Chapter 3: Now, I’m going to retaliate in kind.</strong></div>
            <div>Leon was unsure what expression to use when facing this little girl.</div>
        </div>
        """
        cleaned = clean_chapter_content(content_html, meta=meta)
        self.assertNotIn("Chapter 3: Now, I’m going to retaliate in kind.", cleaned)
        self.assertEqual(
            cleaned,
            "<p>Leon was unsure what expression to use when facing this little girl.</p>",
        )

    def test_clean_chapter_content_removes_chapter_4_style_duplicate(self):
        # Chapter 4 scenario
        meta = ChapterMeta(
            chapter_id="150499",
            volume=1,
            chapter_number="4",
            title="Carve my mark on you.",
            raw_title="1 vol. 4 chapter - Carve my mark on you.",
            url="https://novelight.net/book/chapter/150499",
            is_locked=False,
        )
        content_html = """
        <div class="chapter-text">
            <div><strong>Chapter 4: Carve my mark on you.</strong></div>
            <div>The dragon race’s concept of “revenge” had always puzzled human scholars.</div>
        </div>
        """
        cleaned = clean_chapter_content(content_html, meta=meta)
        self.assertNotIn("Chapter 4: Carve my mark on you.", cleaned)
        self.assertIn("The dragon race’s concept of “revenge” had always puzzled human scholars.", cleaned)

    def test_clean_chapter_content_removes_exact_title_duplicate(self):
        # Chapter 207 scenario: exact duplicate of title without "Chapter X:"
        meta = ChapterMeta(
            chapter_id="150607",
            volume=2,
            chapter_number="12",
            title="A Mark Is a Mark, No Need to Reason With You",
            raw_title="2 vol. 12 chapter - A Mark Is a Mark, No Need to Reason With You",
            url="https://novelight.net/book/chapter/150607",
            is_locked=False,
        )
        content_html = """
        <div class="chapter-text">
            <div>A Mark Is a Mark, No Need to Reason With You</div>
            <div>Leon lay on the bed, staring blankly at the hotel ceiling.</div>
        </div>
        """
        cleaned = clean_chapter_content(content_html, meta=meta)
        self.assertEqual(cleaned, "<p>Leon lay on the bed, staring blankly at the hotel ceiling.</p>")

    def test_clean_chapter_content_preserves_legitimate_prose(self):
        # Chapter 2 scenario: content starts directly with prose
        meta = ChapterMeta(
            chapter_id="150474",
            volume=1,
            chapter_number="2",
            title="You’re awake? Now you’re already a dad!",
            raw_title="1 vol. 2 chapter - You’re awake? Now you’re already a dad!",
            url="https://novelight.net/book/chapter/150474",
            is_locked=False,
        )
        content_html = """
        <div class="chapter-text">
            <div>Reflecting on the life of Leon Casmode, it was indeed a brief journey.</div>
            <div>Leon bare-handedly vanquished a neighbour's ferocious dog.</div>
        </div>
        """
        cleaned = clean_chapter_content(content_html, meta=meta)
        self.assertIn("<p>Reflecting on the life of Leon Casmode, it was indeed a brief journey.</p>", cleaned)
        self.assertIn("<p>Leon bare-handedly vanquished a neighbour's ferocious dog.</p>", cleaned)

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

    def test_strip_watermarks_real_world_examples(self):
        cases = [
            ("Her words struck [N O V E L I G H T] deliberately", "Her words struck deliberately"),
            ("Her cheeks had a hint ~Nоvеl𝕚ght~ of baby fat, and the features already hinted at her potential beauty.",
             "Her cheeks had a hint of baby fat, and the features already hinted at her potential beauty."),
            ("“You’re talking ➤ NоvеⅠight ➤ (Read more on our source) nonsense! Where is it standing? I don’t feel—”",
             "“You’re talking nonsense! Where is it standing? I don’t feel—”"),
            ("“It engraved on your body represents shame, represents you becoming my captive, represents that for the rest of your life, you can only be bound to me, unable to go °• N 𝑜 v 𝑒 l i g h t •° anywhere.”",
             "“It engraved on your body represents shame, represents you becoming my captive, represents that for the rest of your life, you can only be bound to me, unable to go anywhere.”"),
            ("With his strength depleted, Leon arrived at ❀ Nоvеlігht ❀ (Don’t copy, read here) a riverbank late at night to replenish his energy.",
             "With his strength depleted, Leon arrived at a riverbank late at night to replenish his energy."),
            ("When Rosvitha ❖ Nоvеl𝚒ght ❖ (Exclusive on Nоvеl𝚒ght) was deeply immersed in her emotions, she always seemed a bit out of control",
             "When Rosvitha was deeply immersed in her emotions, she always seemed a bit out of control"),
            ("Leon glared at her ◆ Nоvеlіgһt ◆ (Only on Nоvеlіgһt) but didn’t say anything, tacitly admitting.",
             "Leon glared at her but didn’t say anything, tacitly admitting."),
            ("He was a bit taller than Rosvitha, so when Rosvitha helped him adjust the collar, he lowered his head, and his lips /N_o_v_e_l_i_g_h_t/ would inadvertently touch Rosvitha’s fingers.",
             "He was a bit taller than Rosvitha, so when Rosvitha helped him adjust the collar, he lowered his head, and his lips would inadvertently touch Rosvitha’s fingers."),
            ("Hesitating for a moment, Leon still waved, “Muen, ➤ NоvеⅠight ➤ (Read more on our source) sorry to keep you waiting.",
             "Hesitating for a moment, Leon still waved, “Muen, sorry to keep you waiting."),
            ("Making Leon take care of the kid was one thing, ❖ Nоvеl𝚒ght ❖ (Exclusive on Nоvеl𝚒ght) but making him drag his emptied-out body to accompany Muen in playing games was another.",
             "Making Leon take care of the kid was one thing, but making him drag his emptied-out body to accompany Muen in playing games was another."),
        ]
        for raw, expected in cases:
            cleaned = strip_watermarks(raw)
            self.assertEqual(cleaned, expected)

    def test_clean_chapter_content_removes_standalone_watermark_paragraph(self):
        content_html = """
        <div class="chapter-text">
            <div>Valid first paragraph.</div>
            <div>❀ Nоvеlігht ❀ (Don’t copy, read here)</div>
            <div>Valid second paragraph.</div>
        </div>
        """
        cleaned = clean_chapter_content(content_html)
        self.assertIn("<p>Valid first paragraph.</p>", cleaned)
        self.assertIn("<p>Valid second paragraph.</p>", cleaned)
        self.assertNotIn("Novelight", cleaned)
        self.assertNotIn("Don’t copy", cleaned)
        # Standalone paragraph should be removed completely
        paras = [p for p in cleaned.split("\n") if p.strip()]
        self.assertEqual(len(paras), 2)

    def test_strip_watermarks_preserves_typography_and_clean_prose(self):
        clean_prose = [
            "“First-class honors… first-class honors… so many first-class honors!” Leon muttered in a daze.",
            "Two seconds later —",
            "<strong>Chapter 40: Fire a shot first.</strong>",
            "<em>Saying such things as a defeated captive is truly shameless!</em>",
            "And it just so happened that all bookworms shared a common trait — they were both stubborn and loved to argue about trivial details.",
            "Rosvitha widened her eyes slightly, “Leon…”",
            "“Pfft~ Sister, you’re really something. Then, I’ll make a heart sign with Sister~.”",
        ]
        for prose in clean_prose:
            self.assertEqual(strip_watermarks(prose), prose)


if __name__ == "__main__":
    unittest.main()

