"""
Main orchestrator CLI for the Novelight Web Novel Scraper.
Coordinates index fetching, chapter filtering, JSON downloading,
and volume-nested EPUB compilation with resume and graceful exit support.
Uses Rich for terminal output with Windows cp1252 safety.
"""

import argparse
import logging
import os
import sys
from typing import Optional, Sequence

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

import config
from epub_builder import (
    build_epub,
    get_chapter_filepath,
    get_saved_chapter_files,
    save_chapter_file,
)
from fetcher import fetch_json, sleep_with_jitter
from parser import (
    Chapter,
    ChapterMeta,
    is_chapter_content_empty,
    parse_chapter,
    parse_chapter_list,
)

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(highlight=False)
logger = logging.getLogger("novelight_scraper")

# Terminal-safe status strings
STATUS_CACHED   = "[dim]Cached[/dim]"
STATUS_FETCHING = "[yellow]Fetching[/yellow]"
STATUS_SAVED    = "[green]Saved[/green]"
STATUS_LOCKED   = "[red]Locked[/red]"
STATUS_EMPTY    = "[yellow]Empty[/yellow]"
STATUS_ERROR    = "[red]Error[/red]"


def fetch_chapter_index(
    book_id: str = config.BOOK_ID,
    chapter_id: str = config.FIRST_CHAPTER_ID,
) -> list[ChapterMeta]:
    """
    Fetch all chapters from Novelight's pagination API in one request.
    Returns chapters sorted oldest-first (chronological reading order).
    """
    params = {
        "book_id": book_id,
        "current_id": chapter_id,
        "page": 1,
        "pagination": 0,
    }
    data = fetch_json(config.CHAPTER_PAGINATION_URL, params=params)
    html = data.get("html", "")
    chapters = parse_chapter_list(html, base_url=config.BASE_URL)
    # The API returns newest first; reverse so index is chronological
    return list(reversed(chapters))


def filter_chapters(
    chapters: list[ChapterMeta],
    free_only: bool = True,
    volumes: Optional[set[int]] = None,
    start_chapter: int = 1,
    max_chapters: int = 0,
) -> list[ChapterMeta]:
    """Filter and slice the chapter list according to criteria."""
    result = list(chapters)

    if free_only:
        result = [ch for ch in result if not ch.is_locked]

    if volumes:
        result = [ch for ch in result if ch.volume in volumes]

    if start_chapter > 1:
        start_idx = max(0, start_chapter - 1)
        result = result[start_idx:]

    if max_chapters > 0:
        result = result[:max_chapters]

    return result


def is_chapter_downloaded(meta: ChapterMeta, ordinal: int, chapters_dir: str) -> bool:
    """Check if the chapter file already exists on disk and is non-empty."""
    path = get_chapter_filepath(ordinal, volume=meta.volume, output_dir=chapters_dir)
    return os.path.isfile(path) and os.path.getsize(path) > 0


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Configure and parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Novelight Web Novel Scraper -> EPUB",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Target Novel
    parser.add_argument(
        "--book-id",
        "--novel-id",
        dest="book_id",
        type=str,
        default=config.BOOK_ID,
        help="Novel ID on novelight.net",
    )
    parser.add_argument(
        "--first-chapter-id",
        type=str,
        default=config.FIRST_CHAPTER_ID,
        help="First chapter ID for pagination query",
    )

    # Scraping Filters & Controls
    parser.add_argument(
        "--free-only",
        action="store_true",
        default=True,
        help="Only download free (unlocked) chapters",
    )
    parser.add_argument(
        "--include-locked",
        dest="free_only",
        action="store_false",
        help="Include locked/premium chapters in download",
    )
    parser.add_argument(
        "--volumes",
        type=str,
        default=None,
        help="Comma-separated volume numbers to download (e.g. '1,2,3')",
    )
    parser.add_argument(
        "--start-chapter",
        "--start",
        "-s",
        dest="start_chapter",
        type=int,
        default=config.START_CHAPTER,
        help="1-based starting index in the filtered chapter list",
    )
    parser.add_argument(
        "--max-chapters",
        "--chapters",
        "-n",
        dest="max_chapters",
        type=int,
        default=config.NUM_CHAPTERS,
        help="Maximum chapters to download (0 = all available)",
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

    # Output Paths & Files
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

    # Metadata & Styling
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
        help="Path to book cover image",
    )
    parser.add_argument(
        "--css",
        type=str,
        default="styles.css" if os.path.exists("styles.css") else None,
        help="Path to custom CSS stylesheet for EPUB formatting",
    )

    # Workflow Flags
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download chapters even if already saved on disk",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Skip downloading and compile EPUB from existing saved files",
    )
    parser.add_argument(
        "--no-epub",
        action="store_true",
        help="Download and save chapters without generating EPUB",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Fetch and display chapter index table, then exit",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args(argv)
    args.start = args.start_chapter
    args.chapters = args.max_chapters
    args.novel_id = args.book_id
    return args


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


def _build_index_table(chapters: list[ChapterMeta], title: str = "Chapter List") -> Table:
    """Build a Rich Table displaying chapters in the index."""
    table = Table(
        title=title,
        show_header=True,
        header_style="bold magenta",
        border_style="bright_black",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("#", style="cyan", justify="right", no_wrap=True)
    table.add_column("Vol", style="yellow", justify="center", no_wrap=True)
    table.add_column("Ch", style="blue", justify="right", no_wrap=True)
    table.add_column("Title", style="white", justify="left", max_width=45)
    table.add_column("Translator", style="dim", justify="left", no_wrap=True)
    table.add_column("Date", style="dim", justify="center", no_wrap=True)
    table.add_column("Status", style="bold", justify="center", no_wrap=True)

    for idx, ch in enumerate(chapters, start=1):
        status = "[red]Locked[/red]" if ch.is_locked else "[green]Free[/green]"
        table.add_row(
            str(idx),
            str(ch.volume) if ch.volume > 0 else "-",
            str(ch.chapter_number),
            ch.title or ch.raw_title,
            ch.translator or "-",
            ch.date or "-",
            status,
        )
    return table


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
    table.add_column("#", style="cyan", justify="right", no_wrap=True)
    table.add_column("Vol", style="yellow", justify="center", no_wrap=True)
    table.add_column("Ch", style="blue", justify="right", no_wrap=True)
    table.add_column("Title", style="white", justify="left", max_width=45)
    table.add_column("Status", style="bold", justify="center", no_wrap=True)

    for r in rows:
        table.add_row(
            str(r["ordinal"]),
            str(r.get("volume", "-")),
            str(r.get("chapter_number", "-")),
            r["title"],
            r["status"],
        )
    return table


def scrape_novel(args: argparse.Namespace) -> None:
    """Execute the scraping workflow with the provided arguments."""
    chapters_dir = os.path.join(args.output_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    # Header banner
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Novelight Web Novel Scraper[/bold cyan]\n"
            f"[dim]Book ID:[/dim] [yellow]{args.book_id}[/yellow]  "
            f"[dim]|[/dim]  [dim]Free Only:[/dim] [yellow]{args.free_only}[/yellow]  "
            f"[dim]|[/dim]  [dim]Output:[/dim] [yellow]{args.output_dir}[/yellow]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    if args.build_only:
        logger.info("Build-only mode active. Skipping chapter downloads.")
    else:
        # Phase 1: Fetch Index
        with console.status("[bold cyan]Fetching chapter index from Novelight...[/bold cyan]", spinner="dots"):
            all_chapters = fetch_chapter_index(
                book_id=args.book_id,
                chapter_id=args.first_chapter_id,
            )

        # Parse volumes filter if provided
        volumes_set = None
        if getattr(args, "volumes", None):
            volumes_set = {
                int(v.strip()) for v in args.volumes.split(",") if v.strip().isdigit()
            }

        # Phase 2: Filter chapters
        target_chapters = filter_chapters(
            chapters=all_chapters,
            free_only=args.free_only,
            volumes=volumes_set,
            start_chapter=args.start_chapter,
            max_chapters=args.max_chapters,
        )

        total_available = len(all_chapters)
        total_selected = len(target_chapters)
        logger.info(
            "Found %d total chapters. %d selected for download.",
            total_available,
            total_selected,
        )

        # If list-only mode, display table and exit
        if getattr(args, "list_only", False):
            console.print(_build_index_table(target_chapters, title=f"Chapter Index ({total_selected} chapters)"))
            return

        if not target_chapters:
            logger.warning("No chapters match the selected criteria.")
            return

        # Phase 3: Download Loop
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
            "[cyan]Scraping chapters...",
            total=total_selected,
        )

        rows: list[dict] = []
        interrupted = False

        with progress:
            try:
                for idx, meta in enumerate(target_chapters, start=args.start_chapter):
                    progress.update(
                        task_id,
                        description=f"[cyan]Ch {idx:>4}[/cyan] [dim]Vol.{meta.volume} Ch.{meta.chapter_number}[/dim]",
                    )

                    # Check cache
                    if not args.force and is_chapter_downloaded(meta, idx, chapters_dir):
                        logger.debug("Chapter %s already exists. Skipping.", meta.display_title)
                        rows.append({
                            "ordinal": idx,
                            "volume": meta.volume,
                            "chapter_number": meta.chapter_number,
                            "title": meta.display_title,
                            "status": STATUS_CACHED,
                        })
                        progress.advance(task_id)
                        continue

                    # Fetch chapter content
                    try:
                        read_url = f"{config.READ_CHAPTER_URL}/{meta.chapter_id}"
                        data = fetch_json(read_url)
                        content_html = data.get("content", "")

                        if is_chapter_content_empty(content_html):
                            logger.warning(
                                "Chapter %s (ID %s) has empty content (locked/unavailable).",
                                meta.display_title,
                                meta.chapter_id,
                            )
                            rows.append({
                                "ordinal": idx,
                                "volume": meta.volume,
                                "chapter_number": meta.chapter_number,
                                "title": meta.display_title,
                                "status": STATUS_EMPTY,
                            })
                        else:
                            chapter = parse_chapter(content_html, meta=meta, ordinal=idx)
                            save_chapter_file(chapter, output_dir=chapters_dir, lang=args.lang)
                            rows.append({
                                "ordinal": idx,
                                "volume": meta.volume,
                                "chapter_number": meta.chapter_number,
                                "title": chapter.display_title,
                                "status": STATUS_SAVED,
                            })

                    except Exception as exc:
                        logger.error("Failed fetching chapter %s: %s", meta.display_title, exc)
                        rows.append({
                            "ordinal": idx,
                            "volume": meta.volume,
                            "chapter_number": meta.chapter_number,
                            "title": meta.display_title,
                            "status": STATUS_ERROR,
                        })

                    # Rate limiting
                    if idx < (args.start_chapter + total_selected - 1):
                        sleep_with_jitter(args.delay, args.jitter)

                    progress.advance(task_id)

            except KeyboardInterrupt:
                interrupted = True
                console.print()
                logger.warning("Scrape interrupted by user (Ctrl+C).")

        if interrupted:
            logger.info("Proceeding to compile EPUB with chapters downloaded so far...")

        if rows:
            console.print()
            console.print(_build_chapter_table(rows))

    # Phase 4: Compile EPUB
    if args.no_epub:
        logger.info("Skipping EPUB creation (--no-epub specified).")
        return

    saved_files = get_saved_chapter_files(chapters_dir)
    if not saved_files:
        logger.warning(
            "No chapter files found in %s. EPUB cannot be created.", chapters_dir
        )
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
                book_language=args.lang,
                cover_image=args.cover,
                css_file=args.css,
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


def main() -> None:
    args = parse_arguments()
    setup_logging(args.verbose)
    scrape_novel(args)


if __name__ == "__main__":
    main()
