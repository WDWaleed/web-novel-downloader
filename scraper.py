"""
Main orchestrator CLI for the LoLoBun Web Novel Scraper.
Coordinates fetching, parsing, and EPUB compilation with resume and graceful exit support.
"""

import argparse
import logging
import os
import sys
from typing import Optional

from tqdm import tqdm

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

logger = logging.getLogger("lolobun_scraper")


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
    """Initialize logging format and log levels."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def scrape_novel(args: argparse.Namespace) -> None:
    """Execute the scraping workflow with the provided arguments."""
    chapters_dir = os.path.join(args.output_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    if args.build_only:
        logger.info("Build-only mode active. Skipping chapter downloads.")
    else:
        end_chapter = args.start + args.chapters - 1
        logger.info(
            "Starting scrape: chapters %d to %d (total %d) for novel %s",
            args.start,
            end_chapter,
            args.chapters,
            args.novel_id,
        )

        pbar = tqdm(range(args.start, end_chapter + 1), unit="ch", desc="Scraping")
        interrupted = False
        current_url = get_initial_chapter_url(args, chapters_dir)

        try:
            for current_ch in pbar:
                # Check for existing download unless --force is specified
                if not args.force and is_chapter_downloaded(current_ch, chapters_dir):
                    cached_file = get_chapter_filepath(current_ch, chapters_dir)
                    cached_next_url = extract_next_url_from_file(cached_file)
                    if cached_next_url or current_ch == end_chapter:
                        pbar.set_postfix_str(f"Ch {current_ch} (cached)")
                        logger.debug("Chapter %d already exists. Skipping download.", current_ch)
                        if cached_next_url:
                            current_url = cached_next_url
                        continue
                    else:
                        logger.info(
                            "Cached chapter %d missing next URL metadata. Fetching to determine next chapter link...",
                            current_ch,
                        )

                if not current_url:
                    logger.warning("No URL available to fetch chapter %d. Stopping scrape.", current_ch)
                    break

                pbar.set_postfix_str(f"Fetching Ch {current_ch}")

                try:
                    html = fetch_page(current_url)
                    chapter = parse_chapter(html, ordinal=current_ch, base_url=current_url)
                    save_chapter_file(chapter, chapters_dir, lang=args.lang)
                    pbar.set_postfix_str(f"Saved: {chapter.display_title[:25]}")
                    current_url = chapter.next_url

                    if not current_url and current_ch < end_chapter:
                        logger.info(
                            "No next chapter link found on chapter %d (div#bottom-open-next-btn). Reached end of novel.",
                            current_ch,
                        )
                        break
                except Exception as exc:
                    logger.error("Failed processing chapter %d (%s): %s", current_ch, current_url, exc)
                    # Stop on 404 which usually signifies end of novel chapters
                    if "404" in str(exc):
                        logger.warning("Stopping early as chapter %d returned 404.", current_ch)
                        break

                # Sleep between requests (skip delay after last chapter)
                if current_ch < end_chapter and current_url:
                    sleep_with_jitter(args.delay, args.jitter)

        except KeyboardInterrupt:
            interrupted = True
            logger.warning("\nScrape interrupted by user (Ctrl+C).")
        finally:
            pbar.close()

        if interrupted:
            logger.info("Proceeding to compile EPUB with chapters downloaded so far...")

    # EPUB generation step
    if args.no_epub:
        logger.info("Skipping EPUB creation (--no-epub specified).")
        return

    saved_files = get_saved_chapter_files(chapters_dir)
    if not saved_files:
        logger.warning("No chapter files found in %s. EPUB cannot be created.", chapters_dir)
        return

    logger.info("Found %d saved chapter file(s). Generating EPUB...", len(saved_files))
    try:
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
        print(f"\n==========================================")
        print(f" SUCCESS: EPUB created successfully!")
        print(f" Location: {epub_path}")
        print(f" Chapters: {len(saved_files)}")
        print(f"==========================================\n")
    except Exception as exc:
        logger.error("Failed to build EPUB: %s", exc)
        raise


def main() -> None:
    args = parse_arguments()
    setup_logging(args.verbose)
    scrape_novel(args)


if __name__ == "__main__":
    main()
