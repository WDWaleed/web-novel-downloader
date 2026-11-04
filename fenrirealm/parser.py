"""
HTML parser for Fenrirealm.com chapter pages.
Extracts title and body from div.chapter-view using BeautifulSoup.
"""

from __future__ import annotations
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from fenrirealm.config import (
    SELECTOR_CHAPTER_VIEW,
    SELECTOR_TITLE,
    SELECTOR_CONTENT,
)
from parser import Chapter, ChapterMeta  # reuse existing dataclasses

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
