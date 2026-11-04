"""
Playwright-based fetcher for Fenrirealm.com.
Uses a persistent browser profile to store verification state and cookies.
"""

from __future__ import annotations
import logging
import os
import time
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext, Playwright

from fenrirealm.config import (
    HEADLESS,
    BROWSER_TIMEOUT,
    CF_WAIT_SELECTOR,
    SELECTOR_CONTENT,
    USER_DATA_DIR,
    REQUEST_DELAY,
    REQUEST_JITTER,
)

logger = logging.getLogger(__name__)

_playwright: Optional[Playwright] = None
_context: Optional[BrowserContext] = None
_is_headless: bool = HEADLESS


def _get_context() -> BrowserContext:
    """Return a persistent browser context, launching one if needed."""
    global _playwright, _context, _is_headless
    if _context is None:
        if _playwright is None:
            _playwright = sync_playwright().start()

        os.makedirs(USER_DATA_DIR, exist_ok=True)

        launch_kwargs = {
            "user_data_dir": USER_DATA_DIR,
            "headless": _is_headless,
            "viewport": {"width": 1280, "height": 900},
            "args": ["--disable-blink-features=AutomationControlled"],
            "ignore_default_args": ["--enable-automation"],
        }

        # Prefer real installed Google Chrome if available, otherwise bundled Chromium
        try:
            _context = _playwright.chromium.launch_persistent_context(
                channel="chrome", **launch_kwargs
            )
            logger.debug("Launched persistent context using Chrome channel.")
        except Exception:
            _context = _playwright.chromium.launch_persistent_context(**launch_kwargs)
            logger.debug("Launched persistent context using default Chromium.")

    return _context


def fetch_chapter_html(url: str, timeout: int = 60_000) -> str:
    """
    Navigate to a Fenrirealm chapter URL and return fully rendered HTML.
    Waits for Cloudflare Turnstile to resolve and content to appear.
    """
    ctx = _get_context()
    page: Page = ctx.new_page()
    try:
        logger.debug("Navigating to %s", url)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        # Scroll to reader area to trigger hydration / Turnstile widget
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")

        start_time = time.time()
        timeout_sec = timeout / 1000.0
        prompted = False

        while time.time() - start_time < timeout_sec:
            has_challenge = page.locator("[data-testid='unlock-visible-challenge']").count() > 0
            has_content_el = page.locator(SELECTOR_CONTENT).count() > 0
            p_count = page.locator(f"{SELECTOR_CONTENT} p").count() if has_content_el else 0

            # Content is ready when reader-area has novel paragraphs and no active challenge box
            if has_content_el and not has_challenge and p_count > 0:
                logger.debug("Chapter unlocked with %d paragraphs.", p_count)
                break

            if has_challenge and not prompted:
                print(
                    "\n>>> [Action Required] Cloudflare Turnstile challenge displayed in browser window.\n"
                    ">>> Please click the 'Confirm you are human' checkbox in the open browser...\n"
                )
                prompted = True

            time.sleep(1)
        else:
            logger.warning(
                "Timed out waiting for chapter challenge to unlock at %s. Proceeding with page content.",
                url,
            )

        html = page.content()
        logger.debug("Fetched %d bytes from %s", len(html), url)
        return html
    finally:
        page.close()


def close_browser() -> None:
    """Tear down the persistent Playwright context (call at program exit)."""
    global _playwright, _context
    if _context:
        try:
            _context.close()
        except Exception:
            pass
        _context = None
    if _playwright:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None
