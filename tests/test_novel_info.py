"""
Unit tests for NovelInfo parsing and metadata extraction.
"""

import unittest

from parser import NovelInfo, parse_novel_info


SAMPLE_BOOK_HTML = """
<!doctype html>
<html lang="en">
<head>
    <title>📚 Shut Up, Malevolent Dragon! I Don’t Want to Have Any More Children With You - Read Online Free · Novelight</title>
    <meta name="description" content="After being defeated and captured...">
    <meta property="og:title" content="Shut Up, Malevolent Dragon! I Don’t Want to Have Any More Children With You">
    <meta property="og:image" content="/media/book/poster/dragon.jpg">
</head>
<body>
    <div class="page-panel" style="background-image: url(/media/book/background/dragon_bg.jpg);"></div>
    <header class="header-manga">
        <h1 class="clamp clamp-2">Shut Up, Malevolent Dragon! I Don’t Want to Have Any More Children With You</h1>
    </header>
    <main class="main block">
        <div id="information" class="main-section">
            <section class="text-info section">
                <p>After being defeated and captured, the dragon-slaying hero Leon became a captive.</p>
                <p>With a resolve for certain death, Leon turned the tables.</p>
            </section>
            <section class="tags section">
                <a href="/catalog/?tags=21">Male Protagonist</a>
                <a href="/catalog/?tags=119">Dragons</a>
                <a href="/catalog/?tags=104">Marriage</a>
            </section>
            <section class="section text-info">
                <h2>Last 10 chapters</h2>
            </section>
            <div class="translators">
                <h2>Teams: </h2>
                <div class="items">
                    <a href="/team/ether-reads" class="translator">
                        <div class="name">Ether Reads</div>
                    </a>
                    <a href="/team/novellight-team" class="translator">
                        <div class="name">NoveLight ™</div>
                    </a>
                </div>
            </div>
        </div>
    </main>
    <div class="second-information">
        <div class="poster">
            <img src="/media/book/poster/dragon.jpg" alt="Cover poster">
        </div>
        <a href="/book/chapter/150473" class="btn btn-primary read-btn">Start Reading</a>
        <div class="block appreciate">
            <div class="text"><i class="fa fa-star"></i> 4.3/5</div>
            <span>(2140)</span>
        </div>
        <div class="block mini-info">
            <div class="item">
                <div class="sub-header">Status</div>
                <div class="info">Releasing</div>
            </div>
            <div class="item">
                <div class="sub-header">Translation</div>
                <div class="info">Ongoing</div>
            </div>
            <div class="item">
                <div class="sub-header">Type</div>
                <div class="info">Web Novel</div>
            </div>
            <div class="item">
                <div class="sub-header">Country</div>
                <div class="info">China</div>
            </div>
            <div class="item">
                <div class="sub-header">Year of Realese</div>
                <div class="info">2023</div>
            </div>
            <div class="item">
                <div class="sub-header">Author</div>
                <div class="info">奶昔尾尾酱</div>
            </div>
            <div class="item">
                <div class="sub-header">Alternative</div>
                <div class="info">闭嘴恶龙我不想再跟你生孩子了</div>
            </div>
            <div class="item">
                <div class="sub-header">Loaded Chapters</div>
                <div class="info">1338</div>
            </div>
            <div class="item">
                <div class="sub-header">Genres</div>
                <div class="info">
                    <a href="/catalog/?genres=2">Supernatural</a>
                    <a href="/catalog/?genres=6">Romance</a>
                    <a href="/catalog/?genres=11">Fantasy</a>
                </div>
            </div>
        </div>
    </div>
    <script>
        const BOOK_ID = "337";
        const BOOK_TITLE = 'Shut Up, Malevolent Dragon! I Don’t Want to Have Any More Children With You';
    </script>
</body>
</html>
"""


class TestNovelInfo(unittest.TestCase):
    def test_parse_novel_info_complete(self):
        url = "https://novelight.net/book/shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you"
        info = parse_novel_info(SAMPLE_BOOK_HTML, url=url)

        self.assertEqual(info.title, "Shut Up, Malevolent Dragon! I Don’t Want to Have Any More Children With You")
        self.assertEqual(info.book_id, "337")
        self.assertEqual(info.first_chapter_id, "150473")
        self.assertEqual(info.author, "奶昔尾尾酱")
        self.assertEqual(info.alternative_title, "闭嘴恶龙我不想再跟你生孩子了")
        self.assertEqual(info.status, "Releasing")
        self.assertEqual(info.translation_status, "Ongoing")
        self.assertEqual(info.novel_type, "Web Novel")
        self.assertEqual(info.country, "China")
        self.assertEqual(info.release_year, "2023")
        self.assertEqual(info.genres, ["Supernatural", "Romance", "Fantasy"])
        self.assertEqual(info.tags, ["Male Protagonist", "Dragons", "Marriage"])
        self.assertIn("4.3/5", info.rating)
        self.assertEqual(info.rating_count, "2140")
        self.assertEqual(info.cover_url, "https://novelight.net/media/book/poster/dragon.jpg")
        self.assertEqual(info.translators, ["Ether Reads", "NoveLight ™"])
        self.assertEqual(info.loaded_chapters, 1338)
        self.assertIn("After being defeated and captured", info.description)

    def test_parse_novel_info_minimal_fallback(self):
        minimal_html = """
        <html>
        <head><title>Simple Story - Read Online Free · Novelight</title></head>
        <body>
            <script>
                const OBJECT_BY_COMMENT = 999;
            </script>
            <a href="/book/chapter/88888">Read Chapter 1</a>
        </body>
        </html>
        """
        info = parse_novel_info(minimal_html, url="https://novelight.net/book/simple-story")
        self.assertEqual(info.title, "Simple Story")
        self.assertEqual(info.book_id, "999")
        self.assertEqual(info.first_chapter_id, "88888")
        self.assertEqual(info.free_percentage, 0.0)

    def test_novel_info_free_percentage(self):
        info = NovelInfo(
            url="https://novelight.net/book/test",
            book_id="1",
            title="Test",
            first_chapter_id="10",
            total_chapters=100,
            free_chapters_count=80,
            locked_chapters_count=20,
        )
        self.assertAlmostEqual(info.free_percentage, 80.0)


if __name__ == "__main__":
    unittest.main()
