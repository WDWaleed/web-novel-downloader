# 📖 LoLoBun Web Novel Scraper → EPUB

A robust, configurable Python CLI tool that scrapes web novel chapters from `lolobun.com`, cleans junk markup, formats chapter titles consistently, and compiles them into a clean, beautifully styled EPUB3 using Pandoc.

---

## ✨ Features

- **Dynamic Chapter Traversal**: Automatically discovers and follows each chapter's "Next episode" link (`div#bottom-open-next-btn a`), reliably handling non-sequential and non-linear database chapter IDs.
- **Resilient HTTP Fetching**:
  - Realistic `User-Agent` and headers.
  - Automatic retries on transient errors (`429 Too Many Requests`, `5xx Server Errors`, connection drops).
  - Exponential backoff and polite rate-limiting with randomized jitter.
- **Smart HTML Cleaning & Parsing**:
  - Extracts titles and prose paragraphs from `div.title` and `div.text-content-box`.
  - Removes intrusive scripts, styles, and advertisements.
  - Unifies inconsistent chapter title formats (`"Chapter 1: ..."` vs `"2 ..."`).
- **Pandoc EPUB3 Compilation**:
  - Automatically generates an interactive Table of Contents (TOC).
  - Includes book metadata (title, author, language).
  - Uses an elegant e-reader stylesheet (`styles.css`) for readability.
  - Supports custom cover images (`--cover`).
- **Resume & Caching**:
  - Checks for existing downloaded chapters on disk and skips re-downloading them.
  - Caches next-chapter URL metadata to seamlessly resume subsequent downloads without extra network requests.
  - Can re-compile existing chapters into an EPUB at any time without fetching (`--build-only`).
- **Graceful Interruption**:
  - Pressing `Ctrl+C` safely halts scraping and compiles whatever chapters have been downloaded so far.
- **Rich Terminal UI**:
  - Coloured, formatted log output via `rich`.
  - Live progress bar with spinner, chapter count, elapsed time, and ETA.
  - Real-time status column showing the current chapter's **endpoint ID** (the numeric URL segment, e.g. `7173996`).
  - Chapter download summary table (chapter #, endpoint, title, status) printed after the scrape.
  - Styled success and error panels.

---

## 🚀 Requirements & Installation

### 1. System Dependency: Pandoc
Pandoc is required to generate the EPUB files:
- **Windows**: Install via winget:
  ```powershell
  winget install --id JohnMacFarlane.Pandoc
  ```
  Or download the installer from [pandoc.org](https://pandoc.org/installing.html).
- **macOS**: `brew install pandoc`
- **Linux**: `sudo apt install pandoc`

### 2. Python Environment
Requires **Python 3.10+**.

```powershell
# Clone or navigate to the project directory
cd d:\projects\lolobun_scrapper

# Create a virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🛠️ Usage

### Quick Start
Scrape the default novel configured in `config.py`:
```powershell
python scraper.py
```

### Common CLI Options

| Argument | Shorthand | Default | Description |
|---|---|---|---|
| `--novel-id` | | `5320155` | Novel ID on lolobun.com |
| `--first-chapter-id` | | `7173977` | First chapter's numeric ID (for initial URL) |
| `--start-url` | | `None` | Direct URL to start scraping from (overrides novel and chapter IDs) |
| `--start` | `-s` | `1` | Starting chapter ordinal (1-based) |
| `--chapters` | `-n` | `50` | Number of chapters to scrape |
| `--delay` | `-d` | `2.0` | Seconds delay between requests |
| `--jitter` | | `0.5` | Random variance (+/- seconds) applied to delay |
| `--title` | | `"My Web Novel"` | Book title metadata in EPUB |
| `--author` | | `"Unknown Author"`| Book author metadata in EPUB |
| `--output-dir` | `-o` | `output` | Directory where files are stored |
| `--epub-filename` | | `novel.epub` | Filename of generated EPUB |
| `--cover` | | `None` | Path to book cover image (`.jpg` or `.png`) |
| `--css` | | `styles.css` | Path to custom stylesheet |
| `--force` | | `False` | Re-download chapters even if cached on disk |
| `--build-only` | | `False` | Skip scraping; build EPUB from existing chapter files |
| `--no-epub` | | `False` | Scrape and save HTML chapters without building EPUB |
| `--verbose` | `-v` | `False` | Enable debug log output |

### Examples

#### Scrape a specific range (e.g., Chapters 1 to 20):
```powershell
python scraper.py --start 1 --chapters 20 --title "After Defeat and Capture" --author "Author Name"
```

#### Scrape starting from a specific chapter URL:
```powershell
python scraper.py --start-url "https://www.lolobun.com/n/5320155/7173996" --chapters 15
```

#### Resume a download:
If your download was interrupted or you want to fetch more chapters:
```powershell
# Chapters 1-10 are already cached; scraper will fetch chapters 11-30 and combine all 1-30 into EPUB:
python scraper.py --start 1 --chapters 30
```

#### Rebuild EPUB from already downloaded chapters:
```powershell
python scraper.py --build-only --title "Updated Title"
```

#### Add a cover image:
```powershell
python scraper.py --cover cover.jpg
```

---

## 📂 Project Structure

```
lolobun_scraper/
├── config.py           # Module-level defaults and knobs
├── fetcher.py          # HTTP requests, session management, exponential backoff
├── parser.py           # BeautifulSoup chapter parser and title normalizer
├── epub_builder.py     # Pandoc EPUB3 compiler with TOC & metadata
├── scraper.py          # CLI entry point, argument parsing, Rich progress & logging
├── styles.css          # E-reader CSS styling for EPUB typography
├── requirements.txt    # Python dependencies
├── tests/              # Automated unit tests
│   ├── test_fetcher.py
│   ├── test_parser.py
│   ├── test_epub_builder.py
│   └── test_scraper.py
└── output/             # (Ignored in git)
    ├── chapters/       # Intermediate chapter HTML files (chapter_0001.html, etc.)
    └── novel.epub      # Final assembled EPUB book
```

---

## 🧪 Running Tests

Run the full automated test suite with Python's built-in `unittest`:

```powershell
python -m unittest discover tests
```

---

## 📄 License
MIT License.
