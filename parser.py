"""
HTML parsing and cleaning module for LoLoBun web novel chapters.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Chapter:
    """Represents a parsed and cleaned novel chapter."""
    number: int           # Ordinal position (1, 2, 3, ...)
    raw_title: str        # The raw title extracted from the web page
    display_title: str    # Cleaned, normalized title for headings and TOC
    body_html: str        # Cleaned HTML content containing paragraphs


def normalize_title(raw: str, ordinal: int) -> str:
    """
    Normalize inconsistent chapter title strings into a consistent format:
      "Chapter 1: After Defeat and Capture, Som"  -> "Chapter 1: After Defeat and Capture, Som"
      "2  You're Awake? You're a Dad Now!"        -> "Chapter 2: You're Awake? You're a Dad Now!"
      "3: The Great Journey"                      -> "Chapter 3: The Great Journey"
      "The Calm Before The Storm"                 -> "Chapter 4: The Calm Before The Storm"

    Strategy:
      1. If title starts with 'Chapter <N>' (case-insensitive), normalize prefix and preserve subtitle.
      2. If title starts with a bare number, reformat to 'Chapter <N>: <subtitle>'.
      3. Otherwise, prefix with 'Chapter <ordinal>: <raw>'.
    """
    raw_clean = " ".join(raw.strip().split()) if raw else ""
    if not raw_clean:
        return f"Chapter {ordinal}"

    # Case 1: Already starts with "Chapter <N>" or "Ch. <N>" or "Ch <N>"
    match_chapter = re.match(r'^(?:chapter|ch\.?)\s*(\d+)(.*)$', raw_clean, re.IGNORECASE)
    if match_chapter:
        num = match_chapter.group(1)
        rest = match_chapter.group(2).strip()
        # Clean any leading separators like ':' or '-'
        rest = re.sub(r'^[:\-–—]\s*', '', rest).strip()
        return f"Chapter {num}: {rest}" if rest else f"Chapter {num}"

    # Case 2: Starts with a bare number (e.g., "2 You're Awake..." or "2: You're Awake...")
    match_num = re.match(r'^(\d+)\s*(.*)$', raw_clean)
    if match_num:
        num = match_num.group(1)
        rest = match_num.group(2).strip()
        rest = re.sub(r'^[:\-–—]\s*', '', rest).strip()
        return f"Chapter {num}: {rest}" if rest else f"Chapter {num}"

    # Case 3: No number detected — use ordinal
    logger.info("Title '%s' did not have an explicit chapter number. Assigning ordinal %d.", raw_clean, ordinal)
    return f"Chapter {ordinal}: {raw_clean}"


def parse_chapter(html: str, ordinal: int) -> Chapter:
    """
    Parse a chapter's HTML, clean junk tags, and return a Chapter instance.

    Args:
        html: Raw HTML string of the chapter page.
        ordinal: 1-based sequential chapter number.

    Returns:
        A Chapter dataclass instance.

    Raises:
        ValueError: If the main chapter content container cannot be found.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── 1. Title Extraction ──────────────────────────────────────
    title_el = soup.select_one("div.title")
    if not title_el:
        # Fallback to h1, h2, or page title if div.title is absent
        title_el = soup.select_one("h1, h2, .chapter-title")

    raw_title = title_el.get_text(strip=True) if title_el else f"Chapter {ordinal}"
    display_title = normalize_title(raw_title, ordinal)

    # ── 2. Content Extraction ────────────────────────────────────
    content_el = soup.select_one("div.text-content-box")
    if not content_el:
        # Fallback to general content container if class name differed
        content_el = soup.select_one("div.content, div.chapter-content, article")

    if not content_el:
        raise ValueError(
            f"Chapter {ordinal}: could not locate chapter text container (div.text-content-box)"
        )

    # ── 3. Junk Element Removal ──────────────────────────────────
    for junk in content_el.select(
        "script, style, noscript, iframe, .ads, .ad-banner, .advertisement, nav, footer, header"
    ):
        junk.decompose()

    # ── 4. Paragraph Extraction & Cleaning ───────────────────────
    paragraphs = content_el.find_all("p")

    cleaned_paragraphs = []
    if paragraphs:
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Only include non-empty paragraphs
            if text:
                # Strip classes or inline styles from p tag for clean EPUB markup
                p.attrs = {}
                cleaned_paragraphs.append(str(p))
    else:
        # Fallback for pages that use <br> instead of <p> tags
        text_chunks = [line.strip() for line in content_el.get_text().split("\n") if line.strip()]
        for chunk in text_chunks:
            cleaned_paragraphs.append(f"<p>{chunk}</p>")

    body_html = "\n".join(cleaned_paragraphs)

    return Chapter(
        number=ordinal,
        raw_title=raw_title,
        display_title=display_title,
        body_html=body_html,
    )
