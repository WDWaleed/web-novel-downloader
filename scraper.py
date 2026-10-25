"""
Main orchestrator CLI for the LoLoBun Web Novel Scraper.
Coordinates fetching, parsing, and EPUB compilation with resume and graceful exit support.
Uses Rich for beautiful terminal output.
"""

import argparse
import logging
import os
import sys
from typing import Optional
from urllib.parse import urlparse

from rich import print as rprint
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

import config
from epub_builder import (
    build_epub,
    extract_next_url_from_file,
    get_chapter_filepath,
    get_saved_chapter_files,
    save_chapter_file,
)
from fetcher import fetch_page, sleep_with_jitter
from parser import parse_chapter

console = Console()
logger = logging.getLogger("lolobun_scraper")


# ── Status emoji constants ────────────────────────────────────────────────────
STATUS_CACHED   = "[dim]⏭  Cached[/dim]"
STATUS_FETCHING = "[yellow]⬇  Fetching…[/yellow]"
STATUS_SAVED    = "[green]✔  Saved[/green]"
STATUS_ERROR    = "[red]✘  Error[/red]"
STATUS_NO_URL   = "[orange3]⚠  No URL[/orange3]"


def compute_chapter_url(novel_id: str, chapter_id: int | str) -> str:
    """Compute the URL for a given novel and chapter ID."""
    return f"https://www.lolobun.com/n/{novel_id}/{chapter_id}"


def get_initial_chapter_url(args: argparse.Namespace, chapters_dir: str) -> Optional[str]:
    """Determine the starting chapter URL based on CLI args or cached chapters."""
    if getattr(args, "start_url", None):
        return args.start_url

    if args.start == 1:
        return compute_chapter_url(args.novel_id, args.first_chapter_id)

    # If starting at chapter > 1, check if chapter (start - 1) exists on disk with next_url
    prev_chapter_file = get_chapter_filepath(args.start - 1, chapters_dir)
    prev_url = extract_next_url_from_file(prev_chapter_file)
    if prev_url:
        logger.info(
            "Found URL for chapter %d from cached chapter %d metadata: %s",
            args.start,
            args.start - 1,
            prev_url,
        )
        return prev_url

    return compute_chapter_url(args.novel_id, args.first_chapter_id)


def is_chapter_downloaded(chapter_number: int, chapters_dir: str) -> bool:
    """Check if the chapter file already exists on disk."""
    path = get_chapter_filepath(chapter_number, chapters_dir)
    return os.path.isfile(path) and os.path.getsize(path) > 0


def extract_endpoint(url: Optional[str]) -> str:
    """Extract the last path segment (chapter endpoint ID) from a URL."""
    if not url:
        return "—"
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] if path else "—"


def parse_arguments() -> argparse.Namespace:
    """Configure and parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="LoLoBun Web Novel Scraper -> EPUB",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Novel identity
    parser.add_argument(
        "--novel-id",
        type=str,
        default=config.NOVEL_ID,
        help="Novel ID on lolobun.com",
    )
    parser.add_argument(
        "--first-chapter-id",
        type=int,
        default=config.FIRST_CHAPTER_ID,
        help="First chapter numeric ID for starting sequence",
    )
    parser.add_argument(
        "--start-url",
        type=str,
        default=None,
        help="Explicit starting URL (overrides novel-id and first-chapter-id)",
    )

    # Scraping knobs
    parser.add_argument(
        "--start",
        "-s",
        type=int,
        default=config.START_CHAPTER,
        help="Chapter number to start scraping from (1-based)",
    )
    parser.add_argument(
        "--chapters",
        "-n",
        type=int,
        default=config.NUM_CHAPTERS,
        help="Number of chapters to scrape",
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=config.REQUEST_DELAY,
        help="Seconds delay between HTTP requests",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=config.REQUEST_JITTER,
        help="Random variation (+/- seconds) applied to delay",
    )

    # Output options
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default=config.OUTPUT_DIR,
        help="Root output directory for chapters and EPUB",
    )
    parser.add_argument(
        "--epub-filename",
        type=str,
        default=config.EPUB_FILENAME,
        help="Output EPUB filename",
    )

    # Book metadata
    parser.add_argument(
        "--title",
        type=str,
        default=config.BOOK_TITLE,
        help="EPUB book title metadata",
    )
    parser.add_argument(
        "--author",
        type=str,
        default=config.BOOK_AUTHOR,
        help="EPUB book author metadata",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=config.BOOK_LANGUAGE,
        help="EPUB book language code",
    )
    parser.add_argument(
        "--cover",
        type=str,
        default=None,
        help="Path to book cover image (PNG or JPG)",
    )
    parser.add_argument(
        "--css",
        type=str,
        default="styles.css" if os.path.exists("styles.css") else None,
        help="Path to custom CSS file for EPUB formatting",
    )

    # Workflow controls
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download chapters even if they already exist on disk",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Skip downloading and build EPUB from existing saved chapters",
    )
    parser.add_argument(
        "--no-epub",
        action="store_true",
        help="Download and save chapters without generating an EPUB",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging",
    )

    return parser.parse_args()


def setup_logging(verbose: bool = False) -> None:
    """Initialize Rich logging format and log levels."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=verbose,
                markup=True,
            )
        ],
    )


def _build_chapter_table(rows: list[dict]) -> Table:
    """Build a Rich Table summarising scraped chapters."""
    table = Table(
        title="Chapter Download Summary",
        show_header=True,
        header_style="bold magenta",
        border_style="bright_black",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("#",          style="cyan",       justify="right",  no_wrap=True)
    table.add_column("Endpoint",   style="blue",       justify="left",   no_wrap=True)
    table.add_column("Title",      style="white",      justify="left",   no_wrap=False, max_width=50)
    table.add_column("Status",     style="bold",       justify="center", no_wrap=True)

    for r in rows:
        table.add_row(
            str(r["number"]),
            r["endpoint"],
            r["title"],
            r["status"],
        )
    return table


def scrape_novel(args: argparse.Namespace) -> None:
    """Execute the scraping workflow with the provided arguments."""
    chapters_dir = os.path.join(args.output_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    # ── Print header banner ───────────────────────────────────────────────────
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]LoLoBun Web Novel Scraper[/bold cyan]\n"
            f"[dim]Novel:[/dim] [yellow]{args.novel_id}[/yellow]  "
            f"[dim]|[/dim]  [dim]Chapters:[/dim] [yellow]{args.start} – {args.start + args.chapters - 1}[/yellow]  "
            f"[dim]|[/dim]  [dim]Output:[/dim] [yellow]{args.output_dir}[/yellow]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    rows: list[dict] = []   # accumulates per-chapter results for the summary table

    if args.build_only:
        logger.info("Build-only mode active. Skipping chapter downloads.")
    else:
        end_chapter = args.start + args.chapters - 1
        logger.info(
            "Starting scrape: chapters %d to %d (total %d) for novel [bold]%s[/bold]",
            args.start,
            end_chapter,
            args.chapters,
            args.novel_id,
        )

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        )

        task_id = progress.add_task(
            "[cyan]Scraping chapters…",
            total=args.chapters,
        )

        current_url = get_initial_chapter_url(args, chapters_dir)
        interrupted = False

        with progress:
            try:
                for current_ch in range(args.start, end_chapter + 1):
                    endpoint = extract_endpoint(current_url)
                    progress.update(
                        task_id,
                        description=f"[cyan]Ch {current_ch:>4}[/cyan] [dim]({endpoint})[/dim]",
                    )

                    # ── Check cache ───────────────────────────────────────────
                    if not args.force and is_chapter_downloaded(current_ch, chapters_dir):
                        cached_file = get_chapter_filepath(current_ch, chapters_dir)
                        cached_next_url = extract_next_url_from_file(cached_file)
                        if cached_next_url or current_ch == end_chapter:
                            logger.debug("Chapter %d already exists. Skipping.", current_ch)
                            rows.append({
                                "number":   current_ch,
                                "endpoint": endpoint,
                                "title":    f"[dim](cached)[/dim]",
                                "status":   STATUS_CACHED,
                            })
                            if cached_next_url:
                                current_url = cached_next_url
                            progress.advance(task_id)
                            continue
                        else:
                            logger.info(
                                "Cached chapter %d missing next URL metadata. Re-fetching…",
                                current_ch,
                            )

                    # ── No URL available ──────────────────────────────────────
                    if not current_url:
                        logger.warning(
                            "No URL available to fetch chapter %d. Stopping scrape.", current_ch
                        )
                        rows.append({
                            "number":   current_ch,
                            "endpoint": "—",
                            "title":    "—",
                            "status":   STATUS_NO_URL,
                        })
                        break

                    # ── Fetch & parse ─────────────────────────────────────────
                    try:
                        html = fetch_page(current_url)
                        chapter = parse_chapter(html, ordinal=current_ch, base_url=current_url)
                        save_chapter_file(chapter, chapters_dir, lang=args.lang)

                        rows.append({
                            "number":   current_ch,
                            "endpoint": endpoint,
                            "title":    chapter.display_title,
                            "status":   STATUS_SAVED,
                        })

                        current_url = chapter.next_url

                        if not current_url and current_ch < end_chapter:
                            logger.info(
                                "No next chapter link found on chapter %d "
                                "(div#bottom-open-next-btn). Reached end of novel.",
                                current_ch,
                            )
                            progress.advance(task_id)
                            break

                    except Exception as exc:
                        logger.error(
                            "Failed processing chapter %d (%s): %s", current_ch, current_url, exc
                        )
                        rows.append({
                            "number":   current_ch,
                            "endpoint": endpoint,
                            "title":    "[red]error[/red]",
                            "status":   STATUS_ERROR,
                        })
                        if "404" in str(exc):
                            logger.warning(
                                "Stopping early — chapter %d returned 404.", current_ch
                            )
                            progress.advance(task_id)
                            break

                    # ── Inter-request delay ───────────────────────────────────
                    if current_ch < end_chapter and current_url:
                        sleep_with_jitter(args.delay, args.jitter)

                    progress.advance(task_id)

            except KeyboardInterrupt:
                interrupted = True
                console.print()
                logger.warning("Scrape interrupted by user (Ctrl+C).")

        if interrupted:
            logger.info("Proceeding to compile EPUB with chapters downloaded so far…")

        # ── Print chapter summary table ───────────────────────────────────────
        if rows:
            console.print()
            console.print(_build_chapter_table(rows))

    # ── EPUB generation step ──────────────────────────────────────────────────
    if args.no_epub:
        logger.info("Skipping EPUB creation (--no-epub specified).")
        return

    saved_files = get_saved_chapter_files(chapters_dir)
    if not saved_files:
        logger.warning(
            "No chapter files found in %s. EPUB cannot be created.", chapters_dir
        )
        return

    logger.info("Found %d saved chapter file(s). Generating EPUB…", len(saved_files))
    try:
        with console.status("[bold green]Compiling EPUB with Pandoc…[/bold green]", spinner="dots"):
            epub_path = build_epub(
                chapter_files=saved_files,
                output_dir=args.output_dir,
                epub_filename=args.epub_filename,
                book_title=args.title,
                book_author=args.author,
                book_language=args.lang,
                cover_image=args.cover,
                css_file=args.css,
            )

        console.print()
        console.print(
            Panel(
                f"[bold green]✔  EPUB created successfully![/bold green]\n\n"
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


def main() -> None:
    args = parse_arguments()
    setup_logging(args.verbose)
    scrape_novel(args)


if __name__ == "__main__":
    main()
