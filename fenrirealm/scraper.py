"""
Fenrirealm scraping orchestrator.
Iterates chapter URLs sequentially, handles Cloudflare via persistent browser,
parses HTML, and passes chapters to the existing save + EPUB pipeline.
"""

from __future__ import annotations
import atexit
import logging
import os
import sys
import argparse

# Ensure stdout/stderr use UTF-8 on Windows to avoid cp1252 UnicodeEncodeError
# with Rich's spinner/box-drawing characters.
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from epub_builder import build_epub, get_chapter_filepath, get_saved_chapter_files, save_chapter_file
from fenrirealm.config import (
    CHAPTER_URL_TEMPLATE,
    FIRST_CHAPTER,
    REQUEST_DELAY,
    REQUEST_JITTER,
    SERIES_TITLE,
    SERIES_AUTHOR,
    SERIES_SLUG,
    EPUB_FILENAME,
)
from fenrirealm.fetcher import fetch_chapter_html, close_browser
from fenrirealm.parser import parse_fenrirealm_chapter, is_end_of_series
from fetcher import download_cover_image, sleep_with_jitter  # reuse existing rate-limiter
from utils import extract_novel_slug, resolve_output_dir, slugify

console = Console(highlight=False, legacy_windows=False)
logger = logging.getLogger(__name__)

MAX_GAP = 3  # Consecutive missing chapters before stopping

STATUS_CACHED   = "[dim]Cached[/dim]"
STATUS_SAVED    = "[green]Saved[/green]"
STATUS_EMPTY    = "[yellow]Empty[/yellow]"
STATUS_ERROR    = "[red]Error[/red]"
STATUS_GAP      = "[yellow]Gap[/yellow]"


def _build_summary_table(rows: list[dict]) -> Table:
    """Build a Rich Table summarising scraped chapters."""
    table = Table(
        title="Fenrirealm Chapter Download Summary",
        show_header=True,
        header_style="bold magenta",
        border_style="bright_black",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("#", style="cyan", justify="right", no_wrap=True)
    table.add_column("Ch", style="blue", justify="right", no_wrap=True)
    table.add_column("Title", style="white", justify="left", max_width=50)
    table.add_column("Status", style="bold", justify="center", no_wrap=True)
    for r in rows:
        table.add_row(
            str(r["ordinal"]),
            str(r["chapter_number"]),
            r["title"],
            r["status"],
        )
    return table


def _is_chapter_cached(chapter_number: int, chapters_dir: str) -> bool:
    """Return True if a chapter file already exists on disk and is non-empty."""
    # Fenrirealm chapters have no volume nesting (all in root chapters_dir)
    path = get_chapter_filepath(chapter_number, output_dir=chapters_dir)
    return os.path.isfile(path) and os.path.getsize(path) > 0


def scrape_fenrirealm(args: argparse.Namespace) -> None:
    """Fenrirealm download orchestrator — called from scraper.py when --source=fenrirealm."""
    atexit.register(close_browser)

    slug = extract_novel_slug(
        url=getattr(args, "url", None),
        title=getattr(args, "title", None),
        default_slug=SERIES_SLUG,
    )
    args.output_dir = resolve_output_dir(getattr(args, "output_dir", None), slug)

    if getattr(args, "title", None) is None:
        args.title = SERIES_TITLE
    if getattr(args, "author", None) is None:
        args.author = SERIES_AUTHOR
    if getattr(args, "epub_filename", None) is None:
        args.epub_filename = f"{slugify(args.title)}.epub"

    chapters_dir = os.path.join(args.output_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    start_ch: int = getattr(args, "start_chapter", FIRST_CHAPTER)
    max_ch: int = getattr(args, "max_chapters", 0)   # 0 = unlimited
    delay: float = getattr(args, "delay", REQUEST_DELAY)
    jitter: float = getattr(args, "jitter", REQUEST_JITTER)
    force: bool = getattr(args, "force", False)
    lang: str = getattr(args, "lang", "en")

    # Resolve cover image (Issue 7: automatic cover fetching and embedding)
    cover_image_path: Optional[str] = getattr(args, "cover", None)
    if not cover_image_path:
        cover_url = getattr(args, "cover_url", None)
        if not cover_url and getattr(args, "url", None):
            try:
                from fenrirealm.parser import fetch_fenrirealm_info
                series_info = fetch_fenrirealm_info(args.url)
                if series_info:
                    if series_info.cover_url:
                        cover_url = series_info.cover_url
                    if getattr(args, "title", None) == SERIES_TITLE and series_info.title:
                        args.title = series_info.title
                    if getattr(args, "author", None) == SERIES_AUTHOR and series_info.author:
                        args.author = series_info.author
            except Exception as exc:
                logger.debug("Could not fetch Fenrirealm series info for cover: %s", exc)

        if cover_url:
            try:
                cover_image_path = download_cover_image(
                    cover_url=cover_url,
                    dest_dir=args.output_dir,
                    force=force,
                )
            except Exception as exc:
                logger.warning("Failed to download cover image: %s", exc)

        if not cover_image_path:
            for cand in ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp"):
                cand_path = os.path.join(args.output_dir, cand)
                if os.path.isfile(cand_path) and os.path.getsize(cand_path) > 0:
                    cover_image_path = cand_path
                    break

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Fenrirealm Scraper[/bold cyan] — [italic]{args.title}[/italic]\n"
            f"[dim]Start chapter:[/dim] [yellow]{start_ch}[/yellow]  "
            f"[dim]|[/dim]  [dim]Max chapters:[/dim] [yellow]{max_ch if max_ch else 'unlimited'}[/yellow]  "
            f"[dim]|[/dim]  [dim]Output:[/dim] [yellow]{args.output_dir}[/yellow]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    chapter_number = start_ch
    fetched = 0
    consecutive_misses = 0
    rows: list[dict] = []
    interrupted = False

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )
    task_id = progress.add_task("[cyan]Fetching chapters...", total=None)

    with progress:
        try:
            while True:
                if max_ch and fetched >= max_ch:
                    logger.info("Reached max-chapters limit (%d).", max_ch)
                    break

                url = CHAPTER_URL_TEMPLATE.format(chapter_number=chapter_number)
                progress.update(
                    task_id,
                    description=f"[cyan]Ch {chapter_number:>4}[/cyan]",
                )

                # Cache skip
                if not force and _is_chapter_cached(chapter_number, chapters_dir):
                    logger.debug("Chapter %d already cached. Skipping.", chapter_number)
                    rows.append({
                        "ordinal": chapter_number,
                        "chapter_number": chapter_number,
                        "title": f"Ch. {chapter_number}",
                        "status": STATUS_CACHED,
                    })
                    chapter_number += 1
                    fetched += 1
                    consecutive_misses = 0
                    progress.advance(task_id)
                    continue

                # Fetch HTML
                try:
                    html = fetch_chapter_html(url)
                except Exception as exc:
                    logger.error("Failed to fetch chapter %d: %s", chapter_number, exc)
                    rows.append({
                        "ordinal": chapter_number,
                        "chapter_number": chapter_number,
                        "title": f"Ch. {chapter_number}",
                        "status": STATUS_ERROR,
                    })
                    chapter_number += 1
                    consecutive_misses += 1
                    if consecutive_misses >= MAX_GAP:
                        logger.warning("Too many consecutive errors. Stopping.")
                        break
                    progress.advance(task_id)
                    sleep_with_jitter(delay, jitter)
                    continue

                # Parse
                chapter = parse_fenrirealm_chapter(html, chapter_number, url)

                if chapter is None:
                    if is_end_of_series(html):
                        logger.info("End of series detected at chapter %d.", chapter_number)
                        break
                    consecutive_misses += 1
                    logger.warning(
                        "Chapter %d missing (gap?). Consecutive misses: %d/%d",
                        chapter_number, consecutive_misses, MAX_GAP,
                    )
                    rows.append({
                        "ordinal": chapter_number,
                        "chapter_number": chapter_number,
                        "title": f"Ch. {chapter_number}",
                        "status": STATUS_GAP,
                    })
                    if consecutive_misses >= MAX_GAP:
                        logger.warning("Max gap reached. Stopping.")
                        break
                    chapter_number += 1
                    progress.advance(task_id)
                    sleep_with_jitter(delay, jitter)
                    continue

                if not chapter.body_html.strip():
                    logger.warning(
                        "Chapter %d fetched but content is empty (challenge not resolved?).",
                        chapter_number,
                    )
                    rows.append({
                        "ordinal": chapter_number,
                        "chapter_number": chapter_number,
                        "title": chapter.display_title,
                        "status": STATUS_EMPTY,
                    })
                    chapter_number += 1
                    consecutive_misses += 1
                    if consecutive_misses >= MAX_GAP:
                        logger.warning("Too many empty chapters. Stopping.")
                        break
                    progress.advance(task_id)
                    sleep_with_jitter(delay, jitter)
                    continue

                # Save
                consecutive_misses = 0
                save_chapter_file(chapter, output_dir=chapters_dir, lang=lang)
                rows.append({
                    "ordinal": chapter_number,
                    "chapter_number": chapter_number,
                    "title": chapter.display_title,
                    "status": STATUS_SAVED,
                })
                fetched += 1
                chapter_number += 1
                progress.advance(task_id)

                # Rate-limit only between requests
                if max_ch == 0 or fetched < max_ch:
                    sleep_with_jitter(delay, jitter)

        except KeyboardInterrupt:
            interrupted = True
            console.print()
            logger.warning("Scrape interrupted by user (Ctrl+C).")

    if interrupted:
        logger.info("Proceeding to compile EPUB with chapters downloaded so far...")

    if rows:
        console.print()
        console.print(_build_summary_table(rows))

    # EPUB phase (reuses existing pipeline)
    if getattr(args, "no_epub", False):
        logger.info("Skipping EPUB creation (--no-epub specified).")
        return

    if getattr(args, "build_only", False):
        logger.info("Build-only mode: skipping download, compiling EPUB from saved files.")

    saved_files = get_saved_chapter_files(chapters_dir)
    if not saved_files:
        logger.warning("No chapter files found in %s. EPUB cannot be created.", chapters_dir)
        return

    logger.info("Found %d saved chapter file(s). Generating EPUB...", len(saved_files))
    try:
        with console.status("[bold green]Compiling EPUB with Pandoc...[/bold green]", spinner="dots"):
            epub_path = build_epub(
                chapter_files=saved_files,
                output_dir=args.output_dir,
                epub_filename=args.epub_filename,
                book_title=args.title,
                book_author=args.author,
                book_language=lang,
                cover_image=cover_image_path,
                css_file=getattr(args, "css", None),
            )

        console.print()
        console.print(
            Panel(
                f"[bold green]EPUB created successfully![/bold green]\n\n"
                f"[dim]Location :[/dim]  [cyan]{epub_path}[/cyan]\n"
                f"[dim]Chapters :[/dim]  [yellow]{len(saved_files)}[/yellow]",
                title="[bold green]SUCCESS[/bold green]",
                border_style="green",
                padding=(1, 4),
            )
        )
        console.print()
    except Exception as exc:
        logger.error("Failed to build EPUB: %s", exc)
        raise

