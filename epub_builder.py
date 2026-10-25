"""
EPUB assembly module using Pandoc (via pypandoc).
Compiles cleaned HTML chapters into a polished EPUB3 document.
"""

import glob
import logging
import os
import re
from typing import Optional, Sequence

import pypandoc

from config import (
    BOOK_AUTHOR,
    BOOK_LANGUAGE,
    BOOK_TITLE,
    CHAPTERS_DIR,
    EPUB_FILENAME,
    OUTPUT_DIR,
)
from parser import Chapter

logger = logging.getLogger(__name__)


def get_chapter_filepath(chapter_number: int, output_dir: str = CHAPTERS_DIR) -> str:
    """Return the standard file path for a chapter HTML file."""
    filename = f"chapter_{chapter_number:04d}.html"
    return os.path.join(output_dir, filename)


def extract_next_url_from_file(filepath: str) -> Optional[str]:
    """
    Read the next chapter URL stored in a saved chapter HTML file's meta tag.
    Returns None if file does not exist or meta tag is not present.
    """
    if not os.path.isfile(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(4096)
        match = re.search(r'<meta\s+name=["\']next-chapter-url["\']\s+content=["\']([^"\']+)["\']', content)
        if match:
            url = match.group(1).strip()
            return url if url else None
    except Exception as exc:
        logger.debug("Failed reading next chapter URL from %s: %s", filepath, exc)
    return None


def save_chapter_file(
    chapter: Chapter,
    output_dir: str = CHAPTERS_DIR,
    lang: str = BOOK_LANGUAGE,
) -> str:
    """
    Write a single chapter to an HTML file suitable for Pandoc compilation.
    Returns the absolute path of the written file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = get_chapter_filepath(chapter.number, output_dir)

    next_meta = (
        f'\n    <meta name="next-chapter-url" content="{chapter.next_url}">'
        if getattr(chapter, "next_url", None)
        else ""
    )

    html_content = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">{next_meta}
    <title>{chapter.display_title}</title>
</head>
<body>
<h1>{chapter.display_title}</h1>
{chapter.body_html}
</body>
</html>
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.debug("Saved chapter %d to %s", chapter.number, filepath)
    return os.path.abspath(filepath)


def get_saved_chapter_files(chapters_dir: str = CHAPTERS_DIR) -> list[str]:
    """
    Find and return all saved chapter HTML files sorted sequentially by chapter number.
    Matches files like `chapter_0001.html`.
    """
    if not os.path.isdir(chapters_dir):
        return []

    pattern = os.path.join(chapters_dir, "chapter_*.html")
    files = glob.glob(pattern)

    def extract_chapter_num(path: str) -> int:
        match = re.search(r'chapter_(\d+)\.html$', os.path.basename(path))
        return int(match.group(1)) if match else 0

    return sorted(files, key=extract_chapter_num)


def build_epub(
    chapters: Optional[Sequence[Chapter]] = None,
    chapter_files: Optional[Sequence[str]] = None,
    output_dir: str = OUTPUT_DIR,
    epub_filename: str = EPUB_FILENAME,
    book_title: str = BOOK_TITLE,
    book_author: str = BOOK_AUTHOR,
    book_language: str = BOOK_LANGUAGE,
    cover_image: Optional[str] = None,
    css_file: Optional[str] = "styles.css",
) -> str:
    """
    Compile chapters into an EPUB3 file using Pandoc.

    Args:
        chapters: Optional list of Chapter objects to save and compile.
        chapter_files: Optional list of existing chapter HTML file paths.
        output_dir: Directory where the output EPUB should be placed.
        epub_filename: Name of the generated EPUB file.
        book_title: Title metadata for the EPUB.
        book_author: Author metadata for the EPUB.
        book_language: Language code (e.g. 'en').
        cover_image: Optional path to an image file for the book cover.
        css_file: Optional path to a CSS stylesheet for typography.

    Returns:
        The path of the created EPUB file.
    """
    files_to_compile: list[str] = []

    # 1. If chapters were provided, write them first
    if chapters:
        chapters_folder = os.path.join(output_dir, "chapters")
        for ch in chapters:
            path = save_chapter_file(ch, chapters_folder, lang=book_language)
            files_to_compile.append(path)
    elif chapter_files:
        files_to_compile = [os.path.abspath(f) for f in chapter_files]
    else:
        # Fall back to scanning the chapters directory
        chapters_folder = os.path.join(output_dir, "chapters")
        files_to_compile = get_saved_chapter_files(chapters_folder)

    if not files_to_compile:
        raise ValueError("No chapter files found or provided to build EPUB.")

    # 2. Build Pandoc CLI arguments
    extra_args = [
        "--toc",
        "--toc-depth=1",
        "--split-level=1",
        f"--metadata=title:{book_title}",
        f"--metadata=author:{book_author}",
        f"--metadata=lang:{book_language}",
    ]

    # Optional cover image
    if cover_image and os.path.exists(cover_image):
        extra_args.append(f"--epub-cover-image={os.path.abspath(cover_image)}")
        logger.info("Using cover image: %s", cover_image)

    # Optional custom CSS
    if css_file and os.path.exists(css_file):
        extra_args.append(f"--css={os.path.abspath(css_file)}")
        logger.info("Using CSS stylesheet: %s", css_file)

    # 3. Create destination directory and output path
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, epub_filename)
    abs_output_path = os.path.abspath(output_path)

    logger.info(
        "Compiling %d chapter(s) into EPUB: %s...",
        len(files_to_compile),
        abs_output_path,
    )

    pypandoc.convert_file(
        files_to_compile,
        to="epub3",
        outputfile=abs_output_path,
        extra_args=extra_args,
    )

    logger.info("EPUB successfully generated at: %s", abs_output_path)
    return abs_output_path
