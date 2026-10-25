"""
HTML parsing and cleaning module for LoLoBun web novel chapters.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Union
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Chapter:
    """Represents a parsed and cleaned novel chapter."""
    number: int           # Ordinal position (1, 2, 3, ...)
    raw_title: str        # The raw title extracted from the web page
    display_title: str    # Cleaned, normalized title for headings and TOC
    body_html: str        # Cleaned HTML content containing paragraphs
    next_url: Optional[str] = None  # URL of the next chapter if present


def normalize_title(raw: str, ordinal: int) -> str:
    """
    Normalize chapter title strings into a consistent sequential format:
      "Chapter 1: After Defeat and Capture, Som"  -> "Chapter 1: After Defeat and Capture, Som"
      "2  You're Awake? You're a Dad Now!"        -> "Chapter 2: You're Awake? You're a Dad Now!"
      "3: The Great Journey"                      -> "Chapter 3: The Great Journey"
      "The Calm Before The Storm"                 -> "Chapter 4: The Calm Before The Storm"
      "1 The Silver Dragon Lady..." (ordinal 196) -> "Chapter 196: The Silver Dragon Lady..."

    Strategy:
      Always enforces sequential chapter numbering using `ordinal` (so resets in source
      volumes or extras do not corrupt chapter numbers), while preserving the subtitle.
    """
    raw_clean = " ".join(raw.strip().split()) if raw else ""
    if not raw_clean:
        return f"Chapter {ordinal}"

    # Strip any leading chapter prefix (e.g. "Chapter 1", "Ch. 1", "1:")
    subtitle = re.sub(
        r'^(?:chapter|ch\.?)?\s*\d+\s*[:\-–—]?\s*',
        '',
        raw_clean,
        flags=re.IGNORECASE,
    ).strip()

    if subtitle:
        return f"Chapter {ordinal}: {subtitle}"
    return f"Chapter {ordinal}"


def extract_next_chapter_url(
    soup_or_html: Union[str, BeautifulSoup],
    base_url: str = "https://www.lolobun.com",
) -> Optional[str]:
    """
    Extract the next chapter URL from the chapter HTML.
    Looks inside `div#bottom-open-next-btn` for an `a[href]`,
    with fallback to `a[name='next'][href]` or `div.btn.next a[href]`.

    Args:
        soup_or_html: Raw HTML string or BeautifulSoup parsed tree.
        base_url: Base URL used to resolve relative URLs.

    Returns:
        Absolute URL of the next chapter, or None if not found/unavailable.
    """
    if isinstance(soup_or_html, str):
        soup = BeautifulSoup(soup_or_html, "html.parser")
    else:
        soup = soup_or_html

    # Look for anchor inside div#bottom-open-next-btn
    next_btn = soup.select_one("div#bottom-open-next-btn a[href]")
    if not next_btn:
        # Fallbacks for flexibility
        next_btn = soup.select_one("a[name='next'][href], div.btn.next a[href]")

    if not next_btn:
        return None

    href = next_btn.get("href", "").strip()
    if not href or href == "#" or href.lower().startswith("javascript:"):
        return None

    return urljoin(base_url, href)


def parse_chapter(
    html: str,
    ordinal: int,
    base_url: str = "https://www.lolobun.com",
) -> Chapter:
    """
    Parse a chapter's HTML, clean junk tags, extract next chapter URL, and return a Chapter instance.

    Args:
        html: Raw HTML string of the chapter page.
        ordinal: 1-based sequential chapter number.
        base_url: Base URL used to resolve relative links.

    Returns:
        A Chapter dataclass instance.

    Raises:
        ValueError: If the main chapter content container cannot be found.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Next Chapter URL Extraction ──────────────────────────────
    next_url = extract_next_chapter_url(soup, base_url=base_url)

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
        next_url=next_url,
    )
