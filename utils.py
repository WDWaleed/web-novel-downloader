"""
Shared utility functions for the Novelight scraper.
Kept in a standalone module to avoid circular imports between
scraper.py and fenrirealm/scraper.py.
"""

from __future__ import annotations
import os
import re
import unicodedata
from typing import Optional

from fetcher import download_cover_image


def detect_source(url: Optional[str] = None, default: str = "novelight") -> str:
    """Detect platform source ('novelight' or 'fenrirealm') from a URL.

    Args:
        url: URL string to inspect.
        default: Fallback source if URL is empty or does not match a known domain.

    Returns:
        'fenrirealm' if 'fenrirealm.com' is in url,
        'novelight' if 'novelight.net' is in url,
        otherwise `default`.
    """
    if url:
        url_lower = str(url).lower()
        if "fenrirealm.com" in url_lower:
            return "fenrirealm"
        if "novelight.net" in url_lower:
            return "novelight"
    return default


def slugify(text: str) -> str:
    """Convert text into a safe filesystem folder/filename slug.

    Examples:
        "Shut Up, Malevolent Dragon!"  -> "shut-up-malevolent-dragon"
        "Solo Leveling: Ragnarök"      -> "solo-leveling-ragnarok"
        ""                             -> "novel"
    """
    if not text:
        return "novel"
    # Normalise unicode (e.g. accented chars -> ASCII equivalents)
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    # Keep only word chars, hyphens, and spaces; lowercase
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    # Collapse runs of spaces/hyphens into a single hyphen
    return re.sub(r"[-\s]+", "-", text) or "novel"


def extract_novel_slug(
    url: Optional[str] = None,
    title: Optional[str] = None,
    default_slug: Optional[str] = None,
) -> str:
    """Extract or derive a filesystem-friendly novel slug.

    Priority order:
    1. URL slug — parsed from known URL patterns:
       - Novelight: ``/book/<slug>``
       - Fenrir Realm: ``/series/<slug>``
    2. ``default_slug`` (already-known machine slug, e.g. from config)
    3. ``title`` slugified
    4. Fallback: ``"novel"``
    """
    if url:
        clean_url = url.split("?")[0].split("#")[0].rstrip("/")
        # Novelight: /book/<slug>  (skip pure-numeric chapter IDs)
        m_nl = re.search(r"/book/([a-zA-Z0-9_-]+)", clean_url)
        if m_nl:
            slug = m_nl.group(1).strip()
            if not slug.isdigit():
                return slug
        # Fenrir Realm: /series/<slug>
        m_fr = re.search(r"/series/([a-zA-Z0-9_-]+)", clean_url)
        if m_fr:
            return m_fr.group(1).strip()

    if default_slug:
        return slugify(default_slug)

    if title:
        return slugify(title)

    return "novel"


def resolve_output_dir(
    output_dir: Optional[str],
    slug: str,
    base_default: Optional[str] = None,
) -> str:
    """Resolve the final per-novel output directory.

    Behaviour:
    - If ``output_dir`` is ``None`` **or** equals the base default root
      (``config.OUTPUT_DIR`` / ``"output"``), the novel is nested under
      ``<base_default>/<slug>`` so each novel gets its own folder.
    - If a genuinely custom path was provided (anything other than the
      bare default), it is returned unchanged — the user is in control.

    Args:
        output_dir:   Value of ``args.output_dir`` as parsed from the CLI.
        slug:         Novel slug returned by :func:`extract_novel_slug`.
        base_default: Root directory to nest under when output_dir is the
                      default.  Falls back to ``config.OUTPUT_DIR`` if
                      ``None`` (read at call time, not module-load time, to
                      support test-time patching).
    """
    if base_default is None:
        # Deferred import to avoid importing config at module level
        import config as _cfg
        base_default = _cfg.OUTPUT_DIR
    if not output_dir or os.path.abspath(output_dir) == os.path.abspath(base_default):
        return os.path.join(base_default, slug)
    return output_dir

