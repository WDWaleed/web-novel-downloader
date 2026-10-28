"""
HTML and JSON parsing module for Novelight.net web novel chapters.
Extracts chapter metadata from the pagination API and cleans chapter body HTML.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional, Sequence, Union
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Matches "{vol} vol. {ch} chapter - {title}" or variants like "12 vol. 78 chapter -Gag"
TITLE_PATTERN = re.compile(
    r"^\s*(\d+)\s*vol\.?\s*([\d.]+)\s*chapter\s*[-–—:]?\s*(.*?)\s*$",
    re.IGNORECASE,
)

# ── Universal Watermark Cleaning Definitions ────────────────────────
HOMOGLYPHS = str.maketrans({
    # Cyrillic lookalikes
    "а": "a", "А": "A", "с": "c", "С": "C", "е": "e", "Е": "E",
    "о": "o", "О": "O", "р": "p", "Р": "P", "х": "x", "Х": "X",
    "у": "y", "У": "Y", "і": "i", "І": "I", "г": "g", "Г": "G",
    "һ": "h", "Һ": "H", "т": "t", "Т": "T", "п": "n", "П": "N",
    # Greek lookalikes
    "ο": "o", "Ο": "O", "ν": "v", "Ν": "N", "ε": "e", "ι": "i",
})

# Any non-letter noise between characters: spaces, underscores, symbols, punctuation
_SEP = r"(?:[^\w\s]|_|\s)*"

_NOVELIGHT_CORE = (
    rf"[nN]{_SEP}"
    rf"[oO0]{_SEP}"
    rf"[vV]{_SEP}"
    rf"[eE3]{_SEP}"
    rf"[lL1|I]{_SEP}"
    rf"[iI1|!]{_SEP}"
    rf"[gG9]{_SEP}"
    rf"[hH]{_SEP}"
    rf"[tT7]"
    rf"(?:{_SEP}(?:net|com|org))?"
)

_ORNAMENT = r"(?:[^\w\s\(\)\[\]\"“'”\n]|_)"

WATERMARK_PATTERN = re.compile(
    rf"""(?i)
    # Optional leading symbols/ornaments/brackets
    (?:{_ORNAMENT}{{1,8}}\s*|[\[\(/\~]\s*)?
    # The core word novelight in any permutation
    (?:{_NOVELIGHT_CORE})
    # Optional trailing symbols/ornaments/brackets
    (?:\s*{_ORNAMENT}{{1,8}}|\s*[\/\~\]\)])?
    # Optional trailing parenthetical promo notice (any parenthetical directly attached to watermark)
    (?:\s*\([^\)\n]{{1,80}}\))?
    """,
    re.VERBOSE,
)


def normalize_watermark_char(c: str) -> str:
    """Normalize a single character for watermark matching while preserving prose typography."""
    if c in "…“”‘’—–":
        return c
    norm = unicodedata.normalize("NFKD", c)
    if len(norm) == 1:
        c = norm
    return c.translate(HOMOGLYPHS)


def strip_watermarks(text: str) -> str:
    """
    Remove all obfuscated Novelight watermarks and attached promotional notes.
    Handles mathematical unicode, cross-script homoglyphs, zero-width characters,
    decorative symbols, and attached promotional parentheticals.

    Preserves 100% of surrounding prose, HTML formatting tags, and typography
    (such as horizontal ellipses '…', em-dashes '—', and smart quotes).
    """
    if not text:
        return ""
    # Build 1-to-1 character normalized string for exact index matching
    norm = "".join(normalize_watermark_char(c) for c in text)
    matches = list(WATERMARK_PATTERN.finditer(norm))
    if not matches:
        return text.strip()

    # Excise each match from right to left to preserve offsets
    result = text
    for m in reversed(matches):
        start, end = m.span()
        result = result[:start] + result[end:]

    # Clean up redundant spaces and trailing punctuation spacing left by excised watermark
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"[ \t]+([,.:;?!])", r"\1", result)
    return result.strip()



@dataclass
class ChapterMeta:
    """Metadata for a chapter from the pagination index or book page."""
    chapter_id: str
    volume: int
    chapter_number: str
    title: str
    raw_title: str
    url: str
    is_locked: bool
    translator: str = ""
    date: str = ""

    @property
    def display_title(self) -> str:
        """Formatted title for EPUB headings and table of contents."""
        if self.title:
            return f"Vol. {self.volume} Ch. {self.chapter_number} - {self.title}"
        return f"Vol. {self.volume} Ch. {self.chapter_number}"


@dataclass
class NovelInfo:
    """Metadata and chapter statistics for a novel on Novelight."""
    url: str
    book_id: str
    title: str
    first_chapter_id: str
    author: str = ""
    alternative_title: str = ""
    status: str = ""
    translation_status: str = ""
    novel_type: str = ""
    country: str = ""
    release_year: str = ""
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    rating: str = ""
    rating_count: str = ""
    description: str = ""
    cover_url: str = ""
    translators: list[str] = field(default_factory=list)
    loaded_chapters: int = 0
    # Dynamic chapter statistics (populated when chapter index is fetched)
    total_chapters: int = 0
    free_chapters_count: int = 0
    locked_chapters_count: int = 0
    free_chapter_range: str = ""
    locked_chapter_range: str = ""
    volumes_count: int = 0
    first_chapter_title: str = ""
    latest_chapter_title: str = ""

    @property
    def free_percentage(self) -> float:
        """Percentage of total chapters that are currently free/unlocked."""
        if self.total_chapters == 0:
            return 0.0
        return (self.free_chapters_count / self.total_chapters) * 100.0


@dataclass
class Chapter:
    """A downloaded and parsed novel chapter ready for EPUB compilation."""
    meta: ChapterMeta
    body_html: str
    display_title: str
    ordinal: int
    next_url: Optional[str] = None

    def __init__(
        self,
        *args,
        meta: Optional[ChapterMeta] = None,
        body_html: str = "",
        display_title: str = "",
        ordinal: int = 1,
        number: Optional[int] = None,
        raw_title: str = "",
        next_url: Optional[str] = None,
    ):
        if args:
            # Handle positional arguments: (number, raw_title, display_title, body_html, [next_url])
            ord_val = args[0] if len(args) > 0 else 1
            raw_t = args[1] if len(args) > 1 else ""
            disp_t = args[2] if len(args) > 2 else ""
            body = args[3] if len(args) > 3 else ""
            nxt = args[4] if len(args) > 4 else next_url
            vol, ch_num, title_clean = parse_chapter_title(raw_t)
            self.meta = meta or ChapterMeta(
                chapter_id=str(ord_val),
                volume=vol,
                chapter_number=ch_num,
                title=title_clean,
                raw_title=raw_t,
                url="",
                is_locked=False,
            )
            self.body_html = body
            self.display_title = disp_t or self.meta.display_title
            self.ordinal = ord_val
            self.next_url = nxt
        elif meta is not None:
            self.meta = meta
            self.body_html = body_html
            self.display_title = display_title or meta.display_title
            self.ordinal = ordinal if ordinal is not None else (number if number is not None else 1)
            self.next_url = next_url
        else:
            ord_val = number if number is not None else ordinal
            vol, ch_num, title_clean = parse_chapter_title(raw_title)
            self.meta = ChapterMeta(
                chapter_id=str(ord_val),
                volume=vol,
                chapter_number=ch_num,
                title=title_clean,
                raw_title=raw_title,
                url="",
                is_locked=False,
            )
            self.body_html = body_html
            self.display_title = display_title or self.meta.display_title
            self.ordinal = ord_val
            self.next_url = next_url

    @property
    def number(self) -> int:
        """Ordinal position number (backward compatibility with epub_builder)."""
        return self.ordinal

    @property
    def raw_title(self) -> str:
        return self.meta.raw_title

    @property
    def volume(self) -> int:
        return self.meta.volume

    @property
    def chapter_number(self) -> str:
        return self.meta.chapter_number



def parse_chapter_title(raw_title: str) -> tuple[int, str, str]:
    """
    Parse a raw title string into (volume_num, chapter_num, title_text).

    Examples:
        "1 vol. 1 chapter - After defeat..." -> (1, "1", "After defeat...")
        "12 vol. 78 chapter -Gag"             -> (12, "78", "Gag")
        "12 vol. 68.1 chapter - Silver..."    -> (12, "68.1", "Silver...")
        "5 vol. 10 chapter"                   -> (5, "10", "")
    """
    clean_raw = " ".join(raw_title.strip().split()) if raw_title else ""
    match = TITLE_PATTERN.match(clean_raw)
    if match:
        vol = int(match.group(1))
        ch_num = match.group(2)
        title_text = match.group(3).strip()
        return vol, ch_num, title_text

    # Fallback if pattern doesn't match standard format
    return 1, "1", clean_raw


def normalize_title(raw: str, ordinal: int) -> str:
    """
    Normalize title preserving subtitle and ordinal number.
    Maintained for backward compatibility.
    """
    vol, ch_num, title_text = parse_chapter_title(raw)
    if title_text:
        return f"Vol. {vol} Ch. {ch_num} - {title_text}"
    return f"Vol. {vol} Ch. {ch_num}" if vol else f"Chapter {ordinal}"


def parse_chapter_list(
    html: str,
    base_url: str = "https://novelight.net",
) -> list[ChapterMeta]:
    """
    Parse the HTML from the chapter pagination API or novel overview page.
    Returns a list of ChapterMeta objects in the order returned by the page
    (typically newest first).
    """
    soup = BeautifulSoup(html, "html.parser")
    chapters: list[ChapterMeta] = []

    for a in soup.select("a.chapter"):
        href = a.get("href", "").strip()
        ch_id_match = re.search(r"/book/chapter/(\d+)", href)
        if not ch_id_match:
            continue
        chapter_id = ch_id_match.group(1)

        title_el = a.select_one("div.title")
        raw_title = title_el.get_text(separator=" ", strip=True) if title_el else ""
        vol, ch_num, title_text = parse_chapter_title(raw_title)

        # Locked chapters have <span class="cost"><i class="fa fa-lock"></i></span>
        cost_el = a.select_one("span.cost")
        is_locked = bool(cost_el and (cost_el.find("i", class_="fa-lock") or cost_el.get_text(strip=True)))

        author_el = a.select_one("span.author")
        translator = author_el.get_text(strip=True) if author_el else ""

        date_el = a.select_one("span.date")
        date_str = date_el.get_text(strip=True) if date_el else ""

        full_url = urljoin(base_url, href)

        chapters.append(
            ChapterMeta(
                chapter_id=chapter_id,
                volume=vol,
                chapter_number=ch_num,
                title=title_text,
                raw_title=raw_title,
                url=full_url,
                is_locked=is_locked,
                translator=translator,
                date=date_str,
            )
        )

    return chapters


def parse_novel_info(
    html: str,
    url: str = "",
    base_url: str = "https://novelight.net",
) -> NovelInfo:
    """
    Parse a novel overview page HTML from Novelight.
    Extracts book identity (id, first chapter id), metadata (title, author, genres, tags, description, etc.),
    and summary info.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Title extraction
    title = ""
    h1 = soup.select_one("h1.clamp") or soup.find("h1")
    if h1:
        title = h1.get_text(separator=" ", strip=True)
    if not title:
        m_title = re.search(r'const\s+BOOK_TITLE\s*=\s*[\'"]([^\'"]+)[\'"]', html)
        if m_title:
            title = m_title.group(1).strip()
    if not title:
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
    if not title and soup.title:
        title_str = soup.title.get_text(strip=True)
        title_str = re.sub(r"^[^\w\s]+\s*", "", title_str)
        title_str = re.sub(r"\s*-\s*Read Online Free.*$", "", title_str, flags=re.I)
        title_str = re.sub(r"\s*·\s*Novelight.*$", "", title_str, flags=re.I)
        title = title_str.strip()

    # 2. Book ID extraction
    book_id = ""
    m_bid = re.search(r'const\s+BOOK_ID\s*=\s*[\'"](\d+)[\'"]', html)
    if m_bid:
        book_id = m_bid.group(1)
    if not book_id:
        m_ob = re.search(r'const\s+OBJECT_BY_COMMENT\s*=\s*(\d+)', html)
        if m_ob:
            book_id = m_ob.group(1)
    if not book_id:
        m_rate = re.search(r'/book/ajax/rate-book/(\d+)', html)
        if m_rate:
            book_id = m_rate.group(1)

    # 3. First Chapter ID extraction (for pagination query and initial reading)
    first_chapter_id = ""
    read_btn = soup.select_one("a.read-btn")
    if read_btn and read_btn.get("href"):
        m_ch = re.search(r"/book/chapter/(\d+)", read_btn["href"])
        if m_ch:
            first_chapter_id = m_ch.group(1)
    if not first_chapter_id:
        for a in soup.select("a[href*='/book/chapter/']"):
            m_ch = re.search(r"/book/chapter/(\d+)", a.get("href", ""))
            if m_ch:
                first_chapter_id = m_ch.group(1)
                break

    # 4. Cover URL
    cover_url = ""
    poster_img = soup.select_one(".poster img")
    if poster_img:
        cover_url = poster_img.get("src") or poster_img.get("data-src") or ""
    if not cover_url:
        page_panel = soup.select_one(".page-panel")
        if page_panel and page_panel.get("style"):
            m_bg = re.search(r'url\((.*?)\)', page_panel["style"])
            if m_bg:
                cover_url = m_bg.group(1).strip("\"' ")
    if not cover_url:
        og_img = soup.select_one('meta[property="og:image"]')
        if og_img and og_img.get("content"):
            cover_url = og_img["content"].strip()
    if cover_url:
        cover_url = urljoin(base_url, cover_url)

    # 5. Rating & Rating count
    rating = ""
    rating_count = ""
    appr = soup.select_one(".block.appreciate")
    if appr:
        txt_el = appr.select_one(".text")
        cnt_el = appr.select_one("span")
        if txt_el:
            rating = txt_el.get_text(separator=" ", strip=True)
            rating = re.sub(r"^\s*", "", rating).strip()
        if cnt_el:
            rating_count = cnt_el.get_text(strip=True).strip("()")

    # 6. Mini-info attributes
    author = ""
    alt_title = ""
    status = ""
    trans_status = ""
    novel_type = ""
    country = ""
    year = ""
    genres: list[str] = []
    loaded_ch = 0

    for item in soup.select(".mini-info .item"):
        sub = item.select_one(".sub-header")
        info = item.select_one(".info")
        if not sub or not info:
            continue
        sub_txt = sub.get_text(strip=True).lower()
        info_txt = info.get_text(" ", strip=True)
        if "status" in sub_txt:
            status = info_txt
        elif "translation" in sub_txt:
            trans_status = info_txt
        elif "type" in sub_txt:
            novel_type = info_txt
        elif "country" in sub_txt:
            country = info_txt
        elif "year" in sub_txt:
            year = info_txt
        elif "author" in sub_txt:
            author = info_txt
        elif "alternative" in sub_txt:
            alt_title = info_txt
        elif "loaded chapters" in sub_txt:
            digits = re.sub(r"\D", "", info_txt)
            if digits:
                loaded_ch = int(digits)
        elif "genres" in sub_txt:
            genres = [a.get_text(strip=True) for a in info.find_all("a")]

    # 7. Tags
    tags = [a.get_text(strip=True) for a in soup.select("section.tags a")]

    # 8. Translators / Teams
    translators = [t.get_text(strip=True) for t in soup.select(".translators .translator .name")]

    # 9. Description / Synopsis
    desc_paragraphs: list[str] = []
    info_sec = soup.select_one("#information section.text-info")
    if info_sec:
        for p in info_sec.find_all("p"):
            t = p.get_text(strip=True)
            if t:
                desc_paragraphs.append(t)
    description = "\n\n".join(desc_paragraphs)

    return NovelInfo(
        url=url,
        book_id=book_id,
        title=title,
        first_chapter_id=first_chapter_id,
        author=author,
        alternative_title=alt_title,
        status=status,
        translation_status=trans_status,
        novel_type=novel_type,
        country=country,
        release_year=year,
        genres=genres,
        tags=tags,
        rating=rating,
        rating_count=rating_count,
        description=description,
        cover_url=cover_url,
        translators=translators,
        loaded_chapters=loaded_ch,
    )


def _normalize_header_str(s: str) -> str:
    """Normalize string for comparing titles and headers."""
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"[\s\-_–—:.,!?*~#]+", " ", s)
    return s.strip().lower()


def is_redundant_header_paragraph(
    text: str,
    meta: Optional[ChapterMeta] = None,
) -> bool:
    """
    Determine if a paragraph at the beginning of a chapter is redundant metadata
    (e.g., "*Volume 1*", "Chapter 3: Now, I’m going to retaliate in kind.", or duplicate title)
    that repeats the chapter title or volume already presented in headings/TOC.
    """
    clean = text.strip().replace("\xa0", "").strip()
    if not clean:
        return False

    # Remove outer markdown/styling symbols like *...*, **...**, _..._, #...
    stripped = re.sub(r"^[*_~#\s]+|[*_~#\s]+$", "", clean).strip()
    if not stripped:
        return False

    # 1. Standalone volume header: e.g. "Volume 1", "*Volume 1*", "Vol. 1", "Vol 1"
    if re.match(r"^vol(?:ume|\.)?\s*\d+$", stripped, re.I):
        return True

    # Extract metadata properties if available
    title = meta.title if meta else ""
    chapter_number = str(meta.chapter_number) if meta else ""
    display_title = meta.display_title if meta else ""
    raw_title = meta.raw_title if meta else ""

    # 2. Standalone chapter header with or without title:
    # e.g. "Chapter 3: Now, I'm going to retaliate in kind.", "Chap 176: Decision", "Chapter 4"
    # Matches patterns like "Chapter 3", "Chap 176:", "Ch. 5 - Title", "1 vol. 1 chapter - Title"
    m_ch = re.match(
        r"^(?:vol(?:ume|\.)?\s*\d+[\s,.:\-–—]+)?(?:ch(?:apter|ap|\.)?\s*([\d.]+)|(\d+)\s*vol\.?\s*([\d.]+)\s*chapter)\s*(?:[:\-–—]\s*(.*)|$)",
        stripped,
        re.I,
    )
    if m_ch:
        ch_num = m_ch.group(1) or m_ch.group(3) or ""
        rest_title = (m_ch.group(4) or "").strip()

        # If no subtitle following chapter number (e.g. "Chapter 3" or "Chapter 3:"), it's definitely a chapter header
        if not rest_title:
            return True

        # If chapter number in text matches meta
        if chapter_number and ch_num == chapter_number:
            return True

        # If rest_title matches chapter title
        if title:
            norm_rest = _normalize_header_str(rest_title)
            norm_title = _normalize_header_str(title)
            if norm_rest == norm_title or norm_title.endswith(norm_rest) or norm_rest.endswith(norm_title):
                return True

        # Heuristic for single-line header without meta:
        # Short string (<150 chars) with a colon or dash after chapter designation, or not a full sentence
        if len(clean) < 150 and not rest_title.endswith((".", "!", "?")):
            return True
        if len(clean) < 150 and any(sep in clean[:25] for sep in (":", "-", "–", "—")):
            return True

    # 3. Exact match with chapter title, display title, or raw title
    norm_clean = _normalize_header_str(stripped)
    if title and norm_clean == _normalize_header_str(title):
        return True
    if display_title and norm_clean == _normalize_header_str(display_title):
        return True
    if raw_title and norm_clean == _normalize_header_str(raw_title):
        return True

    return False


def clean_chapter_content(
    content_html: str,
    meta: Optional[ChapterMeta] = None,
) -> str:
    """
    Clean the HTML content returned by the read-chapter API:
    - Removes inline advertisement blocks (`div.advertisment`, `.ad`, etc.).
    - Removes scripts, styles, iframes.
    - Extracts paragraph blocks and wraps in clean <p>...</p> tags.
    - Removes redundant volume and chapter title paragraphs at the start of the chapter.
    """
    if not content_html:
        return ""

    soup = BeautifulSoup(content_html, "html.parser")

    # 1. Remove all ads, scripts, and styling
    for junk in soup.select(
        "script, style, noscript, iframe, .advertisment, .advertisement, .ad, .ads, .ad-banner"
    ):
        junk.decompose()

    # Locate content container
    container = soup.select_one("div.chapter-text") or soup

    # 2. Extract paragraph blocks
    raw_paragraphs: list[tuple[str, str]] = []

    # Novelight wraps paragraphs in top-level <div> tags inside div.chapter-text
    child_divs = container.find_all("div", recursive=False)
    if child_divs:
        for div in child_divs:
            # Check for non-empty text, ignoring &nbsp;
            text = div.get_text(strip=True).replace("\xa0", "").strip()
            if text:
                inner_html = div.decode_contents().strip()
                cleaned_html = strip_watermarks(inner_html)
                if cleaned_html:
                    clean_soup = BeautifulSoup(cleaned_html, "html.parser")
                    clean_text = clean_soup.get_text(strip=True).replace("\xa0", "").strip()
                    if clean_text:
                        raw_paragraphs.append((clean_text, cleaned_html))
    else:
        # Fallback to <p> tags if present
        p_tags = container.find_all("p")
        if p_tags:
            for p in p_tags:
                text = p.get_text(strip=True).replace("\xa0", "").strip()
                if text:
                    inner_html = p.decode_contents().strip()
                    cleaned_html = strip_watermarks(inner_html)
                    if cleaned_html:
                        clean_soup = BeautifulSoup(cleaned_html, "html.parser")
                        clean_text = clean_soup.get_text(strip=True).replace("\xa0", "").strip()
                        if clean_text:
                            raw_paragraphs.append((clean_text, cleaned_html))
        else:
            # Fallback to newline separation
            for line in container.get_text().split("\n"):
                cleaned = line.strip().replace("\xa0", "").strip()
                if cleaned:
                    cleaned_text = strip_watermarks(cleaned)
                    if cleaned_text:
                        raw_paragraphs.append((cleaned_text, cleaned_text))

    # 3. Strip redundant leading volume and chapter title paragraphs
    while raw_paragraphs:
        plain_text, _ = raw_paragraphs[0]
        if is_redundant_header_paragraph(plain_text, meta=meta):
            raw_paragraphs.pop(0)
        else:
            break

    return "\n".join(f"<p>{html}</p>" for _, html in raw_paragraphs)


def is_chapter_content_empty(content_html: str) -> bool:
    """
    Determine if the returned chapter content is empty (e.g. locked chapter).
    """
    if not content_html:
        return True
    soup = BeautifulSoup(content_html, "html.parser")
    for junk in soup.select(".advertisment, script, style"):
        junk.decompose()
    text = soup.get_text(strip=True).replace("\xa0", "").strip()
    return len(text) == 0


def parse_chapter(
    content_html: str,
    meta: ChapterMeta,
    ordinal: int,
    next_url: Optional[str] = None,
) -> Chapter:
    """
    Parse chapter content HTML and construct a Chapter instance.
    """
    body_html = clean_chapter_content(content_html, meta=meta)
    return Chapter(
        meta=meta,
        body_html=body_html,
        display_title=meta.display_title,
        ordinal=ordinal,
        next_url=next_url,
    )
