"""
Batch verification test for watermark removal across chapters 11 to 40.
Fetches live chapter content, runs dual-pass comparison, scans for leakage/residuals,
and generates a Rich summary table + markdown audit log.
"""

import argparse
import difflib
import json
import logging
import os
import re
import sys
import unittest
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from fetcher import fetch_json, sleep_with_jitter
from parser import clean_chapter_content
from scraper import fetch_chapter_index, filter_chapters

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(highlight=False)
logger = logging.getLogger("watermark_verifier")

CACHE_DIR = ".test_cache"
AUDIT_REPORT_PATH = "watermark_audit_results.md"

# Suspicious patterns to detect potential leaks/unseen watermark variants
LEAK_PATTERNS = [
    # 1. Any variant of "novelight" in Latin
    (re.compile(r"(?i)\bnovelight\b"), "Plain 'novelight'"),
    (
        re.compile(
            r"(?i)n[\s\-_.*]{0,3}o[\s\-_.*]{0,3}v[\s\-_.*]{0,3}e[\s\-_.*]{0,3}l[\s\-_.*]{0,3}i[\s\-_.*]{0,3}g[\s\-_.*]{0,3}h[\s\-_.*]{0,3}t"
        ),
        "Spaced/broken 'novelight'",
    ),
    # 2. Cyrillic lookalike characters in English prose
    (
        re.compile(r"[\u0430\u0435\u043E\u0440\u0441\u0443\u0445\u0456\u0433\u04BB]"),
        "Cyrillic homoglyph",
    ),
    # 3. Known watermark dingbats/symbols that shouldn't be in novel text
    (re.compile(r"[❀❖◆➤]"), "Watermark decorative symbol"),
    # 4. Attached anti-piracy promo phrases
    (
        re.compile(
            r"(?i)\((?:read more|don’t copy|dont copy|exclusive on|only on|read here|source\b)"
        ),
        "Promo parenthetical",
    ),
]


def extract_raw_paragraphs_without_cleaner(content_html: str) -> list[str]:
    """Extract list of paragraph strings with ads/scripts removed, but without watermark cleaner."""
    soup = BeautifulSoup(content_html, "html.parser")
    for junk in soup.select(
        "script, style, noscript, iframe, .advertisment, .advertisement, .ad, .ads, .ad-banner"
    ):
        junk.decompose()
    container = soup.select_one("div.chapter-text") or soup
    paras: list[str] = []
    child_divs = container.find_all("div", recursive=False)
    if child_divs:
        for div in child_divs:
            t = div.get_text(strip=True).replace("\xa0", "").strip()
            if t:
                paras.append(div.decode_contents().strip())
    else:
        for p in container.find_all("p"):
            t = p.get_text(strip=True).replace("\xa0", "").strip()
            if t:
                paras.append(p.decode_contents().strip())
    return paras


def scan_for_leaks(cleaned_html: str) -> list[str]:
    """Check cleaned text for any residual watermarks, homoglyphs, or promo phrases."""
    plain_text = BeautifulSoup(cleaned_html, "html.parser").get_text()
    leaks: list[str] = []
    for pattern, label in LEAK_PATTERNS:
        matches = pattern.findall(plain_text)
        if matches:
            leaks.append(f"{label} ({len(matches)} match: {matches[0]!r})")
    return leaks


def find_watermark_diffs(raw_paras: list[str], cleaned_html: str) -> list[dict]:
    """Find differences between raw paragraphs and cleaned text to identify stripped segments."""
    clean_soup = BeautifulSoup(cleaned_html, "html.parser")
    clean_paras = [p.decode_contents().strip() for p in clean_soup.find_all("p")]

    diffs: list[dict] = []
    matcher = difflib.SequenceMatcher(None, raw_paras, clean_paras)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            for idx in range(i1, i2):
                diffs.append(
                    {
                        "type": "standalone_paragraph_removed",
                        "before": raw_paras[idx][:120],
                        "after": "(paragraph pruned)",
                    }
                )
        elif tag == "replace":
            for r_p, c_p in zip(raw_paras[i1:i2], clean_paras[j1:j2]):
                if r_p != c_p:
                    diffs.append(
                        {
                            "type": "inline_watermark_removed",
                            "before": r_p[:140],
                            "after": c_p[:140],
                        }
                    )
    return diffs


def run_watermark_audit(start_ch: int = 1, count: int = 0) -> list[dict]:
    """Execute the watermark audit for the specified chapter range (count=0 for all available)."""
    os.makedirs(CACHE_DIR, exist_ok=True)

    all_chapters = fetch_chapter_index()
    target_chapters = filter_chapters(
        all_chapters,
        free_only=True,
        start_chapter=start_ch,
        max_chapters=count if count > 0 else 0,
    )
    total_target = len(target_chapters)
    end_ch = start_ch + total_target - 1

    console.print(
        Panel.fit(
            f"[bold cyan]Watermark Verification Test (Chapters {start_ch} to {end_ch})[/bold cyan]\n"
            f"[dim]Book ID:[/dim] {config.BOOK_ID}  |  [dim]Target Count:[/dim] {total_target}",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    results: list[dict] = []
    total_watermarks = 0

    for idx, meta in enumerate(target_chapters, start=start_ch):
        cache_file = os.path.join(CACHE_DIR, f"ch_{meta.chapter_id}.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            if idx % 25 == 0 or idx == start_ch or idx == end_ch:
                console.print(f"[dim]Fetching {idx}/{end_ch} (Vol {meta.volume} Ch {meta.chapter_number})...[/dim]")
            url = f"{config.READ_CHAPTER_URL}/{meta.chapter_id}"
            data = fetch_json(url)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            sleep_with_jitter(0.35, 0.15)

        content_html = data.get("content", "")
        raw_paras = extract_raw_paragraphs_without_cleaner(content_html)
        cleaned_html = clean_chapter_content(content_html)

        leaks = scan_for_leaks(cleaned_html)
        diffs = find_watermark_diffs(raw_paras, cleaned_html)
        total_watermarks += len(diffs)

        status = "[red]FAIL (Leaks)[/red]" if leaks else "[green]PASS (Clean)[/green]"
        results.append(
            {
                "ordinal": idx,
                "volume": meta.volume,
                "chapter_number": meta.chapter_number,
                "title": meta.title or meta.raw_title,
                "chapter_id": meta.chapter_id,
                "watermarks_found": len(diffs),
                "leaks": leaks,
                "diffs": diffs,
                "status": status,
            }
        )

    # Print summary table
    table = Table(
        title=f"Watermark Verification: Chapters {start_ch}–{end_ch} (Total: {total_target})",
        show_header=True,
        header_style="bold magenta",
        border_style="bright_black",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("#", style="cyan", justify="right", no_wrap=True)
    table.add_column("Vol", style="yellow", justify="center", no_wrap=True)
    table.add_column("Ch", style="blue", justify="right", no_wrap=True)
    table.add_column("Title", style="white", justify="left", max_width=40)
    table.add_column("Stripped", style="bold green", justify="center", no_wrap=True)
    table.add_column("Leaks", style="bold red", justify="center", no_wrap=True)
    table.add_column("Status", justify="center", no_wrap=True)

    # If auditing a very large batch, display chapters with leaks/strips, or sample
    display_rows = results
    if len(results) > 100:
        display_rows = [r for r in results if r["leaks"] or r["watermarks_found"] > 0]
        # Show first 5 and last 5 if list is too large
        if len(display_rows) > 60:
            display_rows = display_rows[:30] + display_rows[-30:]

    for r in display_rows:
        table.add_row(
            str(r["ordinal"]),
            str(r["volume"]),
            str(r["chapter_number"]),
            r["title"],
            str(r["watermarks_found"]),
            str(len(r["leaks"])) if r["leaks"] else "[green]0[/green]",
            r["status"],
        )

    console.print()
    console.print(table)
    if len(results) > 100:
        console.print(f"[dim](Table condensed for display; full log saved to {AUDIT_REPORT_PATH})[/dim]")
    console.print()

    total_leaks = sum(len(r["leaks"]) for r in results)
    console.print(
        Panel(
            f"[bold cyan]Total Chapters Tested :[/bold cyan] {len(results)}\n"
            f"[bold green]Watermarks Stripped   :[/bold green] {total_watermarks}\n"
            f"[bold {'red' if total_leaks else 'green'}]Residual Leaks Found  :[/bold {'red' if total_leaks else 'green'}] {total_leaks}\n"
            f"[bold green]Cleanliness Pass Rate :[/bold green] {(1.0 - (total_leaks / max(1, total_watermarks))) * 100:.1f}%",
            title="[bold green]AUDIT SUMMARY[/bold green]",
            border_style="green" if not total_leaks else "red",
            padding=(1, 4),
        )
    )

    # Save detailed markdown report
    with open(AUDIT_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(f"# Watermark Audit Report (Chapters {start_ch}–{end_ch})\n\n")
        f.write(f"- **Total Chapters Tested**: {len(results)}\n")
        f.write(f"- **Watermarks Detected & Stripped**: {total_watermarks}\n")
        f.write(f"- **Residual Leaks**: {total_leaks}\n\n")
        f.write("## Chapter Excerpt Diff Log\n\n")

        for r in results:
            if r["watermarks_found"] > 0 or r["leaks"]:
                f.write(f"### Chapter {r['ordinal']} (Vol {r['volume']} Ch {r['chapter_number']}: {r['title']})\n")
                f.write(f"- **Chapter ID**: `{r['chapter_id']}`\n")
                f.write(f"- **Watermarks Removed**: {r['watermarks_found']}\n")
                f.write(f"- **Residual Leaks**: {', '.join(r['leaks']) if r['leaks'] else 'None'}\n")
                if r["diffs"]:
                    f.write("- **Diff Samples**:\n")
                    for d in r["diffs"]:
                        f.write(f"  - **Before**: `{d['before']}`\n")
                        f.write(f"  - **After**:  `{d['after']}`\n")
                f.write("\n---\n\n")

    logger.info("Saved detailed audit log to %s", AUDIT_REPORT_PATH)
    return results


class TestWatermarkBatch(unittest.TestCase):
    """Unit test runner wrapper."""

    def test_chapters_11_to_40_watermark_removal(self):
        results = run_watermark_audit(start_ch=11, count=30)
        total_leaks = sum(len(r["leaks"]) for r in results)
        self.assertEqual(total_leaks, 0, f"Found {total_leaks} residual watermark leaks!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit watermark removal on batch chapters")
    parser.add_argument("--start", type=int, default=1, help="Starting chapter index (default: 1)")
    parser.add_argument("--count", type=int, default=0, help="Number of chapters to test (0 for all)")
    args = parser.parse_args()

    run_watermark_audit(start_ch=args.start, count=args.count)
