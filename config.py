"""
Configuration constants for the LoLoBun Web Novel Scraper.
All knobs can be customized here or overridden via CLI flags in scraper.py.
"""

import os

# ── Novel Identity ──────────────────────────────────────────────
NOVEL_ID: str = "5320155"
FIRST_CHAPTER_ID: int = 7173977
BASE_URL: str = f"https://www.lolobun.com/n/{NOVEL_ID}"

# ── Scraping Controls ──────────────────────────────────────────
START_CHAPTER: int = 1         # Chapter ordinal to start downloading from
NUM_CHAPTERS: int = 50         # Number of chapters to fetch
REQUEST_DELAY: float = 2.0     # Base seconds to pause between requests
REQUEST_JITTER: float = 0.5    # Random jitter (+/- seconds) to avoid robotic cadence
REQUEST_TIMEOUT: int = 15      # Seconds before request times out
MAX_RETRIES: int = 3          # Maximum retry attempts on transient errors
RETRY_BACKOFF: float = 5.0    # Exponential backoff factor (seconds * attempt)

# ── Output Paths ────────────────────────────────────────────────
OUTPUT_DIR: str = "output"
CHAPTERS_DIR: str = os.path.join(OUTPUT_DIR, "chapters")
EPUB_FILENAME: str = "novel.epub"

# ── Book Metadata (for EPUB generation) ─────────────────────────
BOOK_TITLE: str = "My Web Novel"
BOOK_AUTHOR: str = "Unknown Author"
BOOK_LANGUAGE: str = "en"

# ── HTTP Headers ────────────────────────────────────────────────
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
