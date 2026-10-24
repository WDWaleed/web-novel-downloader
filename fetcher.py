"""
HTTP fetching module with retry logic, exponential backoff, and rate limiting.
"""

import logging
import random
import time
from typing import Optional

import requests

from config import (
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
    """Return a shared requests.Session configured with user-agent headers."""
    global _default_session
    if _default_session is None:
        _default_session = requests.Session()
        _default_session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
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


def fetch_page(
    url: str,
    session: Optional[requests.Session] = None,
    timeout: int = REQUEST_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    retry_backoff: float = RETRY_BACKOFF,
) -> str:
    """
    Fetch a single URL, returning the page HTML as text.
    Retries on transient HTTP errors (429, 5xx) and connection/timeout errors.

    Raises:
        requests.exceptions.HTTPError: On non-retryable HTTP errors (e.g., 404).
        RuntimeError: If all retry attempts fail.
    """
    client = session or get_default_session()

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug("GET %s (attempt %d/%d)", url, attempt, max_retries)
            resp = client.get(url, timeout=timeout)
            resp.raise_for_status()

            # Ensure UTF-8 decoding for proper character handling
            resp.encoding = "utf-8"
            return resp.text

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
