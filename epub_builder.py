"""
EPUB assembly module using Pandoc (via pypandoc).
Compiles cleaned HTML chapters into a polished EPUB3 document with volume-aware nested TOC.
"""

import glob
import logging
import os
import re
import shutil
import subprocess
from typing import Optional, Sequence

import pypandoc
from bs4 import BeautifulSoup

from config import (
    BOOK_AUTHOR,
    BOOK_LANGUAGE,
    BOOK_TITLE,
    CHAPTERS_DIR,
    EPUB_FILENAME,
    OUTPUT_DIR,
)
from parser import (
    Chapter,
    ChapterMeta,
    is_redundant_header_paragraph,
    normalize_title,
)
from utils import resolve_output_dir, slugify

logger = logging.getLogger(__name__)


def get_chapter_filepath(
    chapter_number: int,
    volume: Optional[int] = None,
    output_dir: str = CHAPTERS_DIR,
) -> str:
    """
    Return the standard file path for a chapter HTML file.
    If volume is provided (> 0), nests inside a vol_XX subdirectory.
    """
    if volume is not None and volume > 0:
        vol_dir = os.path.join(output_dir, f"vol_{volume:02d}")
        filename = f"chapter_{chapter_number:04d}.html"
        return os.path.join(vol_dir, filename)

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
        match = re.search(
            r'<meta\s+name=["\']next-chapter-url["\']\s+content=["\']([^"\']+)["\']',
            content,
        )
        if match:
            url = match.group(1).strip()
            return url if url else None
    except Exception as exc:
        logger.debug("Failed reading next chapter URL from %s: %s", filepath, exc)
    return None


def create_volume_title_page(
    volume: int,
    output_dir: str = CHAPTERS_DIR,
    lang: str = BOOK_LANGUAGE,
) -> str:
    """
    Generate an HTML title page for a volume (<h1>Volume {volume}</h1>).
    This establishes the top-level section for Pandoc's nested TOC.
    """
    vol_dir = os.path.join(output_dir, f"vol_{volume:02d}")
    os.makedirs(vol_dir, exist_ok=True)
    filepath = os.path.join(vol_dir, f"vol_{volume:02d}_title.html")

    html_content = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <title>Volume {volume}</title>
</head>
<body>
<h1 class="volume-title">Volume {volume}</h1>
</body>
</html>
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

    return os.path.abspath(filepath)


def ensure_chapter_title_normalized(filepath: str, chapter_num: int) -> None:
    """
    Ensure the chapter's <title> and heading (<h1> or <h2>) match the sequential chapter number.
    Fixes any title resets.
    """
    if not os.path.isfile(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        heading_match = re.search(r"<(h[12])>(.*?)</\1>", content)
        if not heading_match:
            return

        tag = heading_match.group(1)
        current_heading = heading_match.group(2).strip()
        new_title = normalize_title(current_heading, chapter_num)

        if new_title != current_heading:
            content = re.sub(r"<title>.*?</title>", f"<title>{new_title}</title>", content)
            content = re.sub(
                r"<" + tag + r">.*?</" + tag + r">",
                f"<{tag}>{new_title}</{tag}>",
                content,
            )
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(
                "Normalized title in %s: '%s' -> '%s'",
                os.path.basename(filepath),
                current_heading,
                new_title,
            )
    except Exception as exc:
        logger.debug("Failed normalizing title in %s: %s", filepath, exc)


def sanitize_saved_chapter_file(filepath: str) -> bool:
    """
    Check a saved chapter HTML file and remove redundant volume or chapter title paragraphs
    that duplicate the chapter's <h1>/<h2> heading.
    Returns True if the file was modified, False otherwise.
    """
    if not os.path.isfile(filepath) or "title.html" in filepath:
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        soup = BeautifulSoup(content, "html.parser")
        heading = soup.find(["h1", "h2"])
        if not heading:
            return False
        h_text = heading.get_text(strip=True)

        vol = 0
        ch = ""
        title = ""
        m_head = re.match(r"^Vol\.?\s*(\d+)\s*Ch\.?\s*([\d.]+)(?:\s*-\s*(.*))?$", h_text, re.I)
        if m_head:
            vol = int(m_head.group(1))
            ch = m_head.group(2)
            title = m_head.group(3) or ""

        meta = ChapterMeta(
            chapter_id="0",
            volume=vol,
            chapter_number=ch,
            title=title,
            raw_title="",
            url="",
            is_locked=False,
        )

        paragraphs = soup.body.find_all("p", recursive=False) if soup.body else soup.find_all("p")
        removed_any = False
        for p in paragraphs:
            ptxt = p.get_text(strip=True)
            if is_redundant_header_paragraph(ptxt, meta=meta):
                p.decompose()
                removed_any = True
            else:
                break

        if removed_any:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(str(soup))
            logger.info("Sanitized redundant headers in %s", os.path.basename(filepath))
            return True
    except Exception as exc:
        logger.debug("Failed sanitizing saved chapter in %s: %s", filepath, exc)
    return False


def save_chapter_file(
    chapter: Chapter,
    output_dir: str = CHAPTERS_DIR,
    lang: str = BOOK_LANGUAGE,
    use_volumes: bool = True,
) -> str:
    """
    Write a single chapter to an HTML file suitable for Pandoc compilation.
    When volume organization is active, chapters are nested under vol_XX directories
    and use <h2> tags so volume <h1> tags form a 2-level TOC in Pandoc.
    """
    vol = getattr(chapter, "volume", 0)
    has_vol = bool(
        use_volumes
        and vol > 0
        and ("vol" in chapter.raw_title.lower() or "vol." in chapter.display_title.lower())
    )

    if has_vol:
        target_dir = os.path.join(output_dir, f"vol_{vol:02d}")
        os.makedirs(target_dir, exist_ok=True)
        filepath = get_chapter_filepath(chapter.ordinal, volume=vol, output_dir=output_dir)
        heading_tag = "h2"
    else:
        os.makedirs(output_dir, exist_ok=True)
        filepath = get_chapter_filepath(chapter.ordinal, output_dir=output_dir)
        heading_tag = "h1"

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
<{heading_tag}>{chapter.display_title}</{heading_tag}>
{chapter.body_html}
</body>
</html>
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.debug("Saved chapter %d to %s", chapter.ordinal, filepath)
    return os.path.abspath(filepath)


def get_saved_chapter_files(chapters_dir: str = CHAPTERS_DIR) -> list[str]:
    """
    Find and return all saved chapter HTML files sorted sequentially.
    Scans chapters_dir recursively, including vol_XX subdirectories.
    Excludes volume title files (e.g. vol_*_title.html).
    """
    if not os.path.isdir(chapters_dir):
        return []

    chapter_files: list[str] = []
    for root, _dirs, files in os.walk(chapters_dir):
        for f in files:
            if f.startswith("chapter_") and f.endswith(".html"):
                chapter_files.append(os.path.join(root, f))

    def extract_chapter_sort_key(path: str) -> tuple[int, int]:
        vol_match = re.search(r"vol_(\d+)", path, re.IGNORECASE)
        vol_num = int(vol_match.group(1)) if vol_match else 0
        ord_match = re.search(r"chapter_(\d+)", os.path.basename(path))
        ord_num = int(ord_match.group(1)) if ord_match else 0
        return (vol_num, ord_num)

    return sorted(chapter_files, key=extract_chapter_sort_key)


def write_pandoc_defaults(
    filepath: str,
    output_file: str,
    input_files: Sequence[str],
    toc_depth: int = 1,
    split_level: int = 1,
    book_title: str = "",
    book_author: str = "",
    book_language: str = "en",
    css_file: Optional[str] = None,
    cover_image: Optional[str] = None,
    book_description: Optional[str] = None,
) -> str:
    """
    Generate a Pandoc defaults YAML file to bypass Windows command-line length
    limits (32,767 characters) when compiling hundreds or thousands of chapters.
    """
    lines = [
        "to: epub3",
        f'output-file: "{os.path.abspath(output_file).replace(os.sep, "/")}"',
        "table-of-contents: true",
        f"toc-depth: {toc_depth}",
        f"split-level: {split_level}",
    ]

    if css_file and os.path.exists(css_file):
        css_abs = os.path.abspath(css_file).replace(os.sep, "/")
        lines.append("css:")
        lines.append(f'  - "{css_abs}"')

    if cover_image and os.path.exists(cover_image):
        cover_abs = os.path.abspath(cover_image).replace(os.sep, "/")
        lines.append(f'epub-cover-image: "{cover_abs}"')

    lines.append("metadata:")
    escaped_title = book_title.replace('\\', '\\\\').replace('"', '\\"')
    escaped_author = book_author.replace('\\', '\\\\').replace('"', '\\"')
    lines.append(f'  title: "{escaped_title}"')
    lines.append(f'  author: "{escaped_author}"')
    lines.append(f'  lang: "{book_language}"')
    if book_description:
        escaped_desc = book_description.replace('\\', '\\\\').replace('"', '\\"')
        clean_desc = re.sub(r"\s+", " ", escaped_desc).strip()
        lines.append(f'  description: "{clean_desc}"')

    lines.append("input-files:")
    for f in input_files:
        f_clean = os.path.abspath(f).replace(os.sep, "/")
        lines.append(f'  - "{f_clean}"')

    with open(filepath, "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")

    return os.path.abspath(filepath)


def build_epub(
    chapters: Optional[Sequence[Chapter]] = None,
    chapter_files: Optional[Sequence[str]] = None,
    output_dir: Optional[str] = None,
    epub_filename: Optional[str] = None,
    book_title: str = BOOK_TITLE,
    book_author: str = BOOK_AUTHOR,
    book_language: str = BOOK_LANGUAGE,
    book_description: Optional[str] = None,
    cover_image: Optional[str] = None,
    css_file: Optional[str] = "styles.css",
) -> str:
    """
    Compile chapters into an EPUB3 file using Pandoc.
    Automatically generates volume title pages and nested TOC if chapters are volume-nested.
    Uses a Pandoc defaults file (pandoc_defaults.yaml) to completely bypass OS command-line
    length limits (32k char limit).
    """
    # Ensure output_dir is isolated per-novel if left as base default
    import config as _cfg
    base_default = _cfg.OUTPUT_DIR
    if output_dir is None or os.path.abspath(output_dir) == os.path.abspath(base_default):
        slug = slugify(book_title) if book_title else "novel"
        output_dir = resolve_output_dir(output_dir, slug, base_default=base_default)

    if not epub_filename:
        epub_filename = f"{slugify(book_title)}.epub" if book_title else EPUB_FILENAME

    chapters_folder = os.path.join(output_dir, "chapters")
    files_to_compile: list[str] = []

    # 1. Gather files to compile
    if chapters:
        for ch in chapters:
            path = save_chapter_file(ch, chapters_folder, lang=book_language)
            files_to_compile.append(path)
    elif chapter_files:
        files_to_compile = [os.path.abspath(f) for f in chapter_files]
    else:
        files_to_compile = get_saved_chapter_files(chapters_folder)

    if not files_to_compile:
        raise ValueError("No chapter files found or provided to build EPUB.")

    # 2. Sanitize any saved chapter files (strips redundant headers even from prior downloads)
    for f in files_to_compile:
        sanitize_saved_chapter_file(f)

    # 3. Check if chapters are organized by volumes
    has_volumes = any(re.search(r"vol_\d+", f, re.IGNORECASE) for f in files_to_compile)

    final_file_list: list[str] = []
    if has_volumes:
        # Group chapters by volume
        volumes_dict: dict[int, list[str]] = {}
        non_volume_files: list[str] = []

        for f in files_to_compile:
            vol_match = re.search(r"vol_(\d+)", f, re.IGNORECASE)
            if vol_match:
                v_num = int(vol_match.group(1))
                volumes_dict.setdefault(v_num, []).append(f)
            else:
                non_volume_files.append(f)

        # Build list with volume title pages inserted before each volume's chapters
        for v_num in sorted(volumes_dict.keys()):
            title_page = create_volume_title_page(
                volume=v_num,
                output_dir=chapters_folder,
                lang=book_language,
            )
            final_file_list.append(title_page)
            final_file_list.extend(volumes_dict[v_num])

        final_file_list.extend(non_volume_files)
        toc_depth = 2
        split_level = 2
    else:
        final_file_list = files_to_compile
        toc_depth = 1
        split_level = 1

    # 3. Create destination directory and output path
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, epub_filename)
    abs_output_path = os.path.abspath(output_path)

    # 4. Generate pandoc_defaults.yaml to avoid Windows command line character limit
    defaults_path = os.path.join(output_dir, "pandoc_defaults.yaml")
    write_pandoc_defaults(
        filepath=defaults_path,
        output_file=abs_output_path,
        input_files=final_file_list,
        toc_depth=toc_depth,
        split_level=split_level,
        book_title=book_title,
        book_author=book_author,
        book_language=book_language,
        css_file=css_file,
        cover_image=cover_image,
        book_description=book_description,
    )
    logger.info("Generated Pandoc defaults configuration: %s", defaults_path)

    # 5. Resolve Pandoc executable
    pandoc_bin = shutil.which("pandoc")
    if not pandoc_bin:
        try:
            pandoc_bin = pypandoc.get_pandoc_path()
        except Exception:
            pandoc_bin = "pandoc"

    logger.info(
        "Compiling %d file(s) into EPUB via Pandoc defaults (%s)...",
        len(final_file_list),
        abs_output_path,
    )

    cmd = [pandoc_bin, "-d", os.path.abspath(defaults_path)]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        logger.error("Pandoc execution failed: %s", result.stderr)
        raise RuntimeError(
            f"Pandoc compilation failed (exit code {result.returncode}): {result.stderr}"
        )

    logger.info("EPUB successfully generated at: %s", abs_output_path)
    return abs_output_path
