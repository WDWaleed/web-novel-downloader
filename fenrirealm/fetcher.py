"""
Playwright-based fetcher for Fenrirealm.com.
Handles Cloudflare Turnstile challenges automatically.
"""

from __future__ import annotations
import logging
import time
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Playwright
from playwright_stealth import Stealth

from fenrirealm.config import (
    HEADLESS,
    BROWSER_TIMEOUT,
    CF_WAIT_SELECTOR,
    REQUEST_DELAY,
    REQUEST_JITTER,
)

logger = logging.getLogger(__name__)

_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_stealth: Stealth = Stealth()
_is_headless: bool = HEADLESS


def _get_context() -> BrowserContext:
    """Return a persistent browser context, launching one if needed."""
    global _playwright, _browser, _context, _is_headless
    if _context is None:
        if _playwright is None:
            _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=_is_headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        _context = _browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        # Apply stealth to the context so all pages inherit it
        _stealth.apply_stealth_sync(_context)
    return _context


def fetch_chapter_html(url: str) -> str:
    """
    Navigate to a Fenrirealm chapter URL and return fully rendered HTML.
    Waits for Cloudflare to resolve and content to appear.
    Raises RuntimeError if content never appears within BROWSER_TIMEOUT ms.
    """
    ctx = _get_context()
    page: Page = ctx.new_page()
    try:
        logger.debug("Navigating to %s", url)
        page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)

        # Wait for content to become visible (indicates CF challenge has passed)
        try:
            page.wait_for_selector(CF_WAIT_SELECTOR, timeout=BROWSER_TIMEOUT)
        except Exception:
            # If challenge is interactive and we were headless, switch to headed mode and prompt user
            if _is_headless:
                logger.warning(
                    "Cloudflare challenge did not auto-clear at %s. "
                    "Opening visible browser to solve checkpoint...",
                    url,
                )
                _relaunch_headed()
                return fetch_chapter_html(url)
            else:
                logger.error(
                    "Timeout waiting for content selector '%s' at %s in headed mode.",
                    CF_WAIT_SELECTOR,
                    url,
                )
                raise RuntimeError(
                    f"Timeout waiting for content selector '{CF_WAIT_SELECTOR}' at {url}"
                )

        html = page.content()
        logger.debug("Fetched %d bytes from %s", len(html), url)
        return html
    finally:
        page.close()


def _relaunch_headed() -> None:
    """Tear down the current headless context and relaunch in headed mode."""
    global _is_headless
    close_browser()
    _is_headless = False
    _get_context()


def close_browser() -> None:
    """Tear down the Playwright browser and context (call at program exit)."""
    global _playwright, _browser, _context
    if _context:
        try:
            _context.close()
        except Exception:
            pass
        _context = None
    if _browser:
        try:
            _browser.close()
        except Exception:
            pass
        _browser = None
    if _playwright:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None
