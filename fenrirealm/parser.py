"""
HTML parser for Fenrirealm.com chapter pages and series overview pages.
Extracts title, body, and novel metadata using BeautifulSoup.
"""

from __future__ import annotations
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from fenrirealm.config import (
    BASE_URL,
    SELECTOR_CHAPTER_VIEW,
    SELECTOR_TITLE,
    SELECTOR_CONTENT,
)
from parser import Chapter, ChapterMeta, NovelInfo  # reuse existing dataclasses

logger = logging.getLogger(__name__)


def parse_fenrirealm_chapter(
    html: str,
    chapter_number: int,
    url: str,
) -> Optional[Chapter]:
    """
    Parse a rendered Fenrirealm chapter page.
    Returns None if the chapter does not exist (404-equivalent: no chapter-view div).
    """
    soup = BeautifulSoup(html, "html.parser")

    chapter_view = soup.select_one(SELECTOR_CHAPTER_VIEW)
    if not chapter_view:
        logger.info("No chapter-view found — chapter %d does not exist.", chapter_number)
        return None

    # Extract title
    h2 = chapter_view.select_one(SELECTOR_TITLE)
    raw_title = h2.get_text(strip=True) if h2 else f"Chapter {chapter_number}"

    # Extract content
    reader_area = (
        chapter_view.select_one(SELECTOR_CONTENT)
        or chapter_view.select_one("div[role='region'].reader-area")
        or chapter_view.select_one("div.reader-area")
    )
    if not reader_area:
        logger.warning("div.reader-area missing for chapter %d.", chapter_number)
        return None

    # Remove scripts, styles, iframes, ads, and challenge widgets
    for junk in reader_area.select(
        "script, style, noscript, iframe, .ad, .ads, [data-testid='unlock-visible-challenge'], [data-testid='turnstile-widget']"
    ):
        junk.decompose()

    # Collect paragraphs
    paragraphs: list[str] = []
    p_tags = reader_area.find_all("p")
    if p_tags:
        for p in p_tags:
            text = p.get_text(strip=True).replace("\xa0", "")
            if text:
                paragraphs.append(f"<p>{p.decode_contents().strip()}</p>")
    else:
        # Fallback: treat newline-separated lines as paragraphs
        for line in reader_area.get_text().split("\n"):
            line = line.strip().replace("\xa0", "")
            if line:
                paragraphs.append(f"<p>{line}</p>")

    body_html = "\n".join(paragraphs)

    # Build ChapterMeta — Fenrirealm has no volume concept; default to Vol 1
    meta = ChapterMeta(
        chapter_id=str(chapter_number),
        volume=1,
        chapter_number=str(chapter_number),
        title=raw_title,
        raw_title=raw_title,
        url=url,
        is_locked=False,
    )

    display_title = f"Ch. {chapter_number} - {raw_title}" if raw_title else f"Ch. {chapter_number}"

    return Chapter(
        meta=meta,
        body_html=body_html,
        display_title=display_title,
        ordinal=chapter_number,
    )


def is_end_of_series(html: str) -> bool:
    """
    Heuristic: if the page has no div.chapter-view AND contains common
    'not found' / 404 indicators, we have reached the end of the series.
    """
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one(SELECTOR_CHAPTER_VIEW):
        return False
    page_text = soup.get_text(separator=" ", strip=True).lower()
    not_found_signals = ["404", "not found", "chapter not found", "page not found"]
    return any(sig in page_text for sig in not_found_signals)


def _normalize_series_url(url_or_slug: str) -> str:
    """Convert a slug, chapter URL, or series URL into a canonical Fenrirealm series URL."""
    s = url_or_slug.strip().rstrip("/")
    # Extract series slug if URL has /series/<slug>
    m = re.search(r"/series/([a-zA-Z0-9_-]+)", s)
    if m:
        slug = m.group(1).strip()
        return f"{BASE_URL}/series/{slug}"
    if "/" not in s:
        # bare slug
        return f"{BASE_URL}/series/{s}"
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return f"{BASE_URL}{s if s.startswith('/') else '/' + s}"


def parse_fenrirealm_series_info(html: str, url: str) -> NovelInfo:
    """
    Parse a rendered Fenrirealm series overview page and return a ``NovelInfo``
    instance populated with as many fields as the page exposes.

    Selector strategy (graceful fallback for each field):
    - Title:        h1, then .series-title, then og:title meta
    - Description:  .synopsis, .description, article p, then og:description meta
    - Cover URL:    div.lazy-image-wrapper > img.lazy-image-target (data-src / src),
                    then meta[property="og:image"]
    - Genres/Tags:  .genre a, .tag a, .genres a, .tags a
    - Status:       .status badge text, then badge-like spans containing
                    "ongoing"/"completed"/"hiatus"
    - Translators:  .translator a, .team a
    - Chapter count / range: chapter list links or list items
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Title ──────────────────────────────────────────────────────────────
    title = ""
    h1 = soup.select_one("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        st = soup.select_one(".series-title")
        if st:
            title = st.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "").strip()

    # ── Description ────────────────────────────────────────────────────────
    description = ""
    for sel in (".synopsis", ".description", ".summary", "article", ".series-desc"):
        desc_el = soup.select_one(sel)
        if desc_el:
            paras = desc_el.find_all("p")
            if paras:
                description = "\n\n".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
            else:
                description = desc_el.get_text(separator="\n", strip=True)
            if description:
                break
    if not description:
        og_desc = soup.find("meta", attrs={"name": "description"})
        if og_desc:
            description = og_desc.get("content", "").strip()

    # ── Cover Image URL ────────────────────────────────────────────────────
    cover_url = ""
    img_el = soup.select_one("div.lazy-image-wrapper > img.lazy-image-target")
    if img_el:
        cover_url = img_el.get("data-src") or img_el.get("src") or ""
    if not cover_url:
        # Any img inside a lazy-image-wrapper
        wrapper = soup.select_one(".lazy-image-wrapper")
        if wrapper:
            img = wrapper.find("img")
            if img:
                cover_url = img.get("data-src") or img.get("src") or ""
    if not cover_url:
        og_img = soup.find("meta", property="og:image")
        if og_img:
            cover_url = og_img.get("content", "").strip()
    if cover_url:
        cover_url = urljoin(url or BASE_URL, cover_url.strip())

    # ── Author / Translators ───────────────────────────────────────────────
    author = ""
    translators: list[str] = []

    # Try author-specific element first
    for sel in (".author", "[class*='author']", ".novel-author"):
        author_el = soup.select_one(sel)
        if author_el:
            author = author_el.get_text(strip=True)
            break

    # Translators: .translator, .team, etc.
    for sel in (".translator", ".team", ".group", "[class*='translator']", "[class*='team']"):
        for el in soup.select(sel):
            name = el.get_text(strip=True)
            if name and name not in translators:
                translators.append(name)
        if translators:
            break

    # ── Genres / Tags ──────────────────────────────────────────────────────
    genres: list[str] = []
    tags: list[str] = []
    for sel in (".genre a", ".genres a", "[class*='genre'] a"):
        for a in soup.select(sel):
            g = a.get_text(strip=True)
            if g and g not in genres:
                genres.append(g)
        if genres:
            break

    for sel in (".tag a", ".tags a", "[class*='tag'] a"):
        for a in soup.select(sel):
            t = a.get_text(strip=True)
            if t and t not in tags:
                tags.append(t)
        if tags:
            break

    # ── Status ─────────────────────────────────────────────────────────────
    status = ""
    for sel in (".status", "[class*='status']", ".badge", ".label"):
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True).lower()
            if any(kw in text for kw in ("ongoing", "completed", "hiatus", "dropped", "releasing")):
                status = el.get_text(strip=True)
                break

    # ── Chapter list ───────────────────────────────────────────────────────
    # Scan visible chapter links to determine chapter count + first/latest
    chapter_links = soup.select("a[href*='/series/'][href*='/']")
    # Keep only links that look like chapter URLs (end with a number)
    chapter_numbers: list[int] = []
    _ch_num_re = re.compile(r"/series/[^/]+/(\d+)(?:/|$)")
    for a in chapter_links:
        href = a.get("href", "")
        m = _ch_num_re.search(href)
        if m:
            chapter_numbers.append(int(m.group(1)))

    chapter_numbers = sorted(set(chapter_numbers))
    total_chapters = len(chapter_numbers)

    first_chapter_title = ""
    latest_chapter_title = ""
    free_chapter_range = ""

    if chapter_numbers:
        first_chapter_title = f"Ch. {chapter_numbers[0]}"
        latest_chapter_title = f"Ch. {chapter_numbers[-1]}"
        free_chapter_range = (
            f"Ch. {chapter_numbers[0]} - Ch. {chapter_numbers[-1]} "
            f"({total_chapters:,} chapters)"
        )

    # Derive slug from URL for the book_id field (Fenrirealm has no numeric book ID)
    slug = ""
    m_slug = re.search(r"/series/([a-zA-Z0-9_-]+)", url)
    if m_slug:
        slug = m_slug.group(1)

    return NovelInfo(
        url=url,
        book_id=slug,          # repurpose book_id as the series slug identifier
        first_chapter_id="1",  # Fenrirealm chapters start at 1
        title=title or slug or "Unknown",
        author=author,
        description=description,
        cover_url=cover_url,
        genres=genres,
        tags=tags,
        status=status,
        translators=translators,
        total_chapters=total_chapters,
        free_chapters_count=total_chapters,  # all Fenrirealm chapters are free
        locked_chapters_count=0,
        free_chapter_range=free_chapter_range,
        first_chapter_title=first_chapter_title,
        latest_chapter_title=latest_chapter_title,
    )


def fetch_fenrirealm_info(url_or_slug: str) -> NovelInfo:
    """
    Fetch and parse the Fenrirealm series overview page for the given URL or slug.

    Args:
        url_or_slug: Full series URL (``https://fenrirealm.com/series/<slug>``)
                     or bare slug (``absolute-regression``).

    Returns:
        A populated :class:`~parser.NovelInfo` dataclass.
    """
    from fenrirealm.fetcher import fetch_series_page_html

    canonical_url = _normalize_series_url(url_or_slug)
    html = fetch_series_page_html(canonical_url)
    return parse_fenrirealm_series_info(html, url=canonical_url)
