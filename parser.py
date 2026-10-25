"""
HTML and JSON parsing module for Novelight.net web novel chapters.
Extracts chapter metadata from the pagination API and cleans chapter body HTML.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Sequence, Union
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Matches "{vol} vol. {ch} chapter - {title}" or variants like "12 vol. 78 chapter -Gag"
TITLE_PATTERN = re.compile(
    r"^\s*(\d+)\s*vol\.?\s*([\d.]+)\s*chapter\s*[-–—:]?\s*(.*?)\s*$",
    re.IGNORECASE,
)


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


def clean_chapter_content(content_html: str) -> str:
    """
    Clean the HTML content returned by the read-chapter API:
    - Removes inline advertisement blocks (`div.advertisment`, `.ad`, etc.).
    - Removes scripts, styles, iframes.
    - Extracts paragraph blocks and wraps in clean <p>...</p> tags.
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
    paragraphs: list[str] = []

    # Novelight wraps paragraphs in top-level <div> tags inside div.chapter-text
    child_divs = container.find_all("div", recursive=False)
    if child_divs:
        for div in child_divs:
            # Check for non-empty text, ignoring &nbsp;
            text = div.get_text(strip=True).replace("\xa0", "").strip()
            if text:
                inner_html = div.decode_contents().strip()
                paragraphs.append(f"<p>{inner_html}</p>")
    else:
        # Fallback to <p> tags if present
        p_tags = container.find_all("p")
        if p_tags:
            for p in p_tags:
                text = p.get_text(strip=True).replace("\xa0", "").strip()
                if text:
                    paragraphs.append(f"<p>{p.decode_contents().strip()}</p>")
        else:
            # Fallback to newline separation
            for line in container.get_text().split("\n"):
                cleaned = line.strip().replace("\xa0", "").strip()
                if cleaned:
                    paragraphs.append(f"<p>{cleaned}</p>")

    return "\n".join(paragraphs)


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
    body_html = clean_chapter_content(content_html)
    return Chapter(
        meta=meta,
        body_html=body_html,
        display_title=meta.display_title,
        ordinal=ordinal,
        next_url=next_url,
    )
