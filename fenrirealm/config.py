"""
Configuration for Fenrirealm.com scraper.
Series: Absolute Regression
"""

BASE_URL: str = "https://fenrirealm.com"
SERIES_SLUG: str = "absolute-regression"
FIRST_CHAPTER: int = 1

# URL template: format with chapter number
CHAPTER_URL_TEMPLATE: str = f"{BASE_URL}/series/{SERIES_SLUG}/{{chapter_number}}"

# CSS selectors
SELECTOR_CHAPTER_VIEW: str = "div.chapter-view"
SELECTOR_TITLE: str = "div.text-center > h2"
SELECTOR_CONTENT: str = "div.reader-area"

# Playwright / browser settings
HEADLESS: bool = True           # Set False to show browser window
BROWSER_TIMEOUT: int = 30_000  # ms — time for page load + CF challenge
CF_WAIT_SELECTOR: str = SELECTOR_CONTENT  # wait until this appears post-challenge

# Scraping controls (overrideable via CLI)
REQUEST_DELAY: float = 1.5      # seconds between chapter fetches (be gentle)
REQUEST_JITTER: float = 0.5

# Output
SERIES_TITLE: str = "Absolute Regression"
SERIES_AUTHOR: str = "Unknown"
EPUB_FILENAME: str = "absolute_regression.epub"

