"""
HTTP fetching module with retry logic, exponential backoff, and rate limiting.
Supports both standard HTML page fetching and AJAX JSON fetching.
"""

import logging
import os
import random
import time
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests

from config import (
    AJAX_HEADERS,
    BASE_URL,
    DEFAULT_HEADERS,
    MAX_RETRIES,
    REQUEST_DELAY,
    REQUEST_JITTER,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

_default_session: Optional[requests.Session] = None


def get_default_session() -> requests.Session:
    """Return a shared requests.Session configured with default headers."""
    global _default_session
    if _default_session is None:
        _default_session = requests.Session()
        _default_session.headers.update(DEFAULT_HEADERS)
    return _default_session


def sleep_with_jitter(base_delay: float = REQUEST_DELAY, jitter: float = REQUEST_JITTER) -> float:
    """
    Pause execution for base_delay seconds with random jitter (+/- jitter).
    Ensures non-negative sleep duration. Returns actual sleep duration.
    """
    if base_delay <= 0:
        return 0.0

    actual_delay = max(0.0, base_delay + random.uniform(-jitter, jitter))
    time.sleep(actual_delay)
    return actual_delay


def _get_with_retry(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    timeout: int = REQUEST_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    retry_backoff: float = RETRY_BACKOFF,
) -> requests.Response:
    """
    Execute GET request with retries on transient errors (429, 5xx) and network drops.
    """
    client = session or get_default_session()

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug("GET %s (attempt %d/%d)", url, attempt, max_retries)
            resp = client.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None

            # 404 indicates missing chapter or end of available chapters
            if status == 404:
                logger.warning("Chapter URL returned 404 Not Found: %s", url)
                raise

            # Retry on rate limiting (429) or server errors (5xx)
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait_time = retry_backoff * attempt
                logger.warning(
                    "HTTP %s for %s. Retrying in %.1fs (attempt %d/%d)...",
                    status,
                    url,
                    wait_time,
                    attempt,
                    max_retries,
                )
                time.sleep(wait_time)
            else:
                raise

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            if attempt < max_retries:
                wait_time = retry_backoff * attempt
                logger.warning(
                    "Network error (%s) fetching %s. Retrying in %.1fs (attempt %d/%d)...",
                    exc.__class__.__name__,
                    url,
                    wait_time,
                    attempt,
                    max_retries,
                )
                time.sleep(wait_time)
            else:
                raise RuntimeError(
                    f"Failed to fetch {url} after {max_retries} attempts due to network errors."
                ) from exc

    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts.")


def fetch_page(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    timeout: int = REQUEST_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    retry_backoff: float = RETRY_BACKOFF,
) -> str:
    """
    Fetch a single URL, returning the page HTML as text.
    """
    resp = _get_with_retry(
        url=url,
        params=params,
        headers=headers,
        session=session,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )
    return resp.text


def fetch_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    timeout: int = REQUEST_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    retry_backoff: float = RETRY_BACKOFF,
) -> dict[str, Any]:
    """
    Fetch a URL expecting a JSON response.
    Includes AJAX headers (X-Requested-With: XMLHttpRequest) by default.
    """
    req_headers = dict(AJAX_HEADERS)
    if headers:
        req_headers.update(headers)

    resp = _get_with_retry(
        url=url,
        params=params,
        headers=req_headers,
        session=session,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )
    return resp.json()


def download_cover_image(
    cover_url: str,
    dest_dir: str,
    session: Optional[requests.Session] = None,
    timeout: int = REQUEST_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    retry_backoff: float = RETRY_BACKOFF,
    force: bool = False,
) -> Optional[str]:
    """
    Download novel cover image and save it into dest_dir (e.g. output/<slug>/cover.jpg).

    Checks existing cached cover files in dest_dir first.
    Fetches using requests with retry logic, falling back to Playwright persistent
    browser context if available and requests encounters 403 / Cloudflare blocks.

    Args:
        cover_url: Remote cover image URL.
        dest_dir: Directory where the cover file should be stored.
        session: Optional requests.Session to use.
        timeout: Network timeout in seconds.
        max_retries: Maximum retry attempts for transient errors.
        retry_backoff: Exponential backoff factor.
        force: If True, re-download and overwrite existing cover file.

    Returns:
        Path to the saved cover image file, or None if download failed.
    """
    if not cover_url or not isinstance(cover_url, str) or not cover_url.strip():
        return None

    cover_url = cover_url.strip()
    if cover_url.startswith("//"):
        cover_url = f"https:{cover_url}"
    elif cover_url.startswith("/"):
        cover_url = urljoin(BASE_URL, cover_url)

    os.makedirs(dest_dir, exist_ok=True)

    # Infer extension from URL path
    parsed = urlparse(cover_url)
    _, ext = os.path.splitext(parsed.path)
    ext = ext.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"):
        ext = ".jpg"

    target_path = os.path.join(dest_dir, f"cover{ext}")

    # Check cache unless force is requested
    if not force:
        if os.path.isfile(target_path) and os.path.getsize(target_path) > 0:
            logger.debug("Existing cover image found at %s. Skipping download.", target_path)
            return target_path
        for cand_ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            cand_path = os.path.join(dest_dir, f"cover{cand_ext}")
            if os.path.isfile(cand_path) and os.path.getsize(cand_path) > 0:
                logger.debug("Existing cover image found at %s. Skipping download.", cand_path)
                return cand_path

    client = session or get_default_session()
    img_headers = {
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "User-Agent": USER_AGENT,
    }

    content_bytes: Optional[bytes] = None
    content_type: str = ""

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(
                "Downloading cover image from %s (attempt %d/%d)...",
                cover_url,
                attempt,
                max_retries,
            )
            resp = client.get(cover_url, headers=img_headers, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                ct = resp.headers.get("Content-Type", "").lower()
                if "text/html" in ct:
                    logger.warning(
                        "Cover URL %s returned HTML content instead of an image.",
                        cover_url,
                    )
                    break
                content_bytes = resp.content
                content_type = ct
                break
            elif resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait_time = retry_backoff * attempt
                logger.warning(
                    "HTTP %s for cover %s. Retrying in %.1fs...",
                    resp.status_code,
                    cover_url,
                    wait_time,
                )
                time.sleep(wait_time)
            elif resp.status_code in (401, 403):
                logger.debug(
                    "HTTP %s fetching cover with requests. Will attempt browser fallback.",
                    resp.status_code,
                )
                break
            else:
                logger.warning("HTTP %s when fetching cover image: %s", resp.status_code, cover_url)
                break

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            if attempt < max_retries:
                wait_time = retry_backoff * attempt
                logger.warning(
                    "Network error fetching cover image (%s). Retrying in %.1fs...",
                    exc.__class__.__name__,
                    wait_time,
                )
                time.sleep(wait_time)
            else:
                logger.warning("Network error fetching cover image from %s after retries.", cover_url)
                break
        except Exception as exc:
            logger.debug("Unexpected error fetching cover %s: %s", cover_url, exc)
            break

    # If requests was blocked or returned no content, try Playwright persistent browser context
    if not content_bytes:
        try:
            from fenrirealm.fetcher import _context
            if _context is not None:
                logger.debug("Attempting to fetch cover image via persistent browser session...")
                playwright_resp = _context.request.get(cover_url, timeout=timeout * 1000)
                if playwright_resp.ok:
                    body = playwright_resp.body()
                    ct = playwright_resp.headers.get("content-type", "").lower()
                    if body and "text/html" not in ct:
                        content_bytes = body
                        content_type = ct
                        logger.debug(
                            "Successfully fetched cover image via browser session (%d bytes).",
                            len(body),
                        )
        except Exception as exc:
            logger.debug("Browser context fallback for cover image failed: %s", exc)

    if not content_bytes:
        logger.warning("Could not download cover image from %s.", cover_url)
        return None

    # Refine extension based on Content-Type header if available
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    elif "gif" in content_type:
        ext = ".gif"
    elif "jpeg" in content_type or "jpg" in content_type:
        ext = ".jpg"

    target_path = os.path.join(dest_dir, f"cover{ext}")
    try:
        with open(target_path, "wb") as f:
            f.write(content_bytes)
        logger.info("Saved cover image to %s (%d bytes).", target_path, len(content_bytes))
        return target_path
    except OSError as exc:
        logger.error("Failed saving cover image to %s: %s", target_path, exc)
        return None

