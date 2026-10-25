"""
Configuration constants for the Novelight Web Novel Scraper.
Targets: "Shut Up, Malevolent Dragon! I Don't Want to Have Any More Children With You"
All knobs can be customized here or overridden via CLI flags in scraper.py.
"""

import os

# ── Target Novel Identity ─────────────────────────────────────────
BOOK_SLUG: str = "shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you"
BOOK_ID: str = "337"
FIRST_CHAPTER_ID: str = "150473"
BASE_URL: str = "https://novelight.net"

# ── API Endpoints ─────────────────────────────────────────────────
CHAPTER_PAGINATION_URL: str = f"{BASE_URL}/book/ajax/chapter-pagination"
READ_CHAPTER_URL: str = f"{BASE_URL}/book/ajax/read-chapter"
BOOK_URL: str = f"{BASE_URL}/book/{BOOK_SLUG}"

# ── Scraping Controls ─────────────────────────────────────────────
FREE_ONLY: bool = True          # Download only unlocked/free chapters
START_CHAPTER: int = 1          # Ordinal to start downloading from (1-based)
NUM_CHAPTERS: int = 0           # Max chapters to fetch (0 = all available)
REQUEST_DELAY: float = 2.0      # Base seconds to pause between requests
REQUEST_JITTER: float = 0.5     # Random jitter (+/- seconds)
REQUEST_TIMEOUT: int = 15       # Seconds before request times out
MAX_RETRIES: int = 3            # Maximum retry attempts on transient errors
RETRY_BACKOFF: float = 5.0      # Exponential backoff factor (seconds * attempt)

# ── Output Paths ──────────────────────────────────────────────────
OUTPUT_DIR: str = "output"
CHAPTERS_DIR: str = os.path.join(OUTPUT_DIR, "chapters")
EPUB_FILENAME: str = "shut_up_malevolent_dragon.epub"

# ── Book Metadata (for EPUB generation) ───────────────────────────
BOOK_TITLE: str = (
    "Shut Up, Malevolent Dragon! I Don't Want to Have Any More Children With You"
)
BOOK_AUTHOR: str = "Unknown"  # Translation: Ether Reads / Santos
BOOK_LANGUAGE: str = "en"

# ── HTTP Headers ──────────────────────────────────────────────────
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

AJAX_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

# ── Backward Compatibility Aliases ────────────────────────────────
NOVEL_ID: str = BOOK_ID
