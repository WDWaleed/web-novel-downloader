# 📖 Novelight Web Novel Scraper → EPUB

A robust, configurable Python CLI tool that downloads web novel chapters from `novelight.net`, cleans junk markup and advertisements, normalizes volume and chapter hierarchies, and compiles them into a clean, beautifully styled multi-volume EPUB3 using Pandoc.

---

## ✨ Features

- **Single-Call API Indexing**: Fetches the full chapter catalog (1,300+ chapters) in a single request via Novelight's pagination API.
- **Paywall / Lock Filtering**: Automatically identifies free vs. locked/premium chapters using `<span class="cost">` indicators (`--free-only`).
- **Volume & Chapter Hierarchy**:
  - Organizes downloaded files into volume subdirectories (`output/chapters/vol_01/chapter_0001.html`).
  - Inserts volume title pages (`<h1>Volume N</h1>`) and chapter headings (`<h2>`).
  - Generates a 2-level nested Table of Contents in the EPUB (**Volume** → **Chapters**).
- **Direct JSON Content Extraction**: Downloads chapter prose directly from Novelight's JSON API (`/book/ajax/read-chapter/{id}`) with clean markup and automatic ad removal (`.advertisment`).
- **Resilient HTTP Fetching**:
  - Automatic retries on transient errors (`429 Too Many Requests`, `5xx Server Errors`, connection drops).
  - Polite rate-limiting with randomized jitter.
- **Resume & Caching**:
  - Checks for existing downloaded chapters on disk and skips re-downloading them.
  - Recompiles existing chapters into an EPUB at any time without fetching (`--build-only`).
- **Large-Novel Pandoc Compilation (1,000+ Chapters)**:
  - Generates a Pandoc defaults configuration (`output/pandoc_defaults.yaml`) to compile intermediate HTML chapters.
  - Completely eliminates OS and Windows command-line argument limits (the 32,767 character limit) when compiling thousands of chapters.
- **Graceful Interruption**:
  - Pressing `Ctrl+C` safely halts scraping and compiles whatever chapters have been downloaded so far into EPUB.
- **Rich Terminal UI**:
  - Live progress bar with chapter counts, volume/chapter indicators, elapsed time, and ETA.
  - Windows console encoding safety (prevents `UnicodeEncodeError` on cp1252 consoles).
  - Chapter list preview mode (`--list-only`) to inspect chapters without downloading.

---

## 🚀 Requirements & Installation

### 1. System Dependency: Pandoc
Pandoc is required to generate the EPUB files:
- **Windows**: Install via winget:
  ```powershell
  winget install --id JohnMacFarlane.Pandoc
  ```
  Or download from [pandoc.org](https://pandoc.org/installing.html).
- **macOS**: `brew install pandoc`
- **Linux**: `sudo apt install pandoc`

### 2. Python Environment
Requires **Python 3.10+**.

```powershell
# Clone or navigate to the project directory
cd "d:\Web Dev Projects\25_LoLoBun Scraper"

# Create a virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🛠️ Usage

### Quick Start
Fetch rich novel info and check chapter availability without downloading:
```powershell
python scraper.py --info https://novelight.net/book/shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you
```

Preview all available chapters without downloading:
```powershell
python scraper.py --list-only
```

Download all available free chapters of the default novel:
```powershell
python scraper.py
```

Download any novel directly by URL:
```powershell
python scraper.py https://novelight.net/book/<slug>
```

Download in fast mode:
```powershell
python scraper.py https://novelight.net/book/<slug> --fast
```

### Common CLI Options

| Argument | Shorthand | Default | Description |
|---|---|---|---|
| `--info` | `--fetch-info`, `--novel-info` | `False` | Fetch and display novel details & chapter availability without downloading (accepts optional URL) |
| `URL` | `--url`, `--book-url` | `None` | Novel URL on novelight.net (pass positionally or with `--url`) |
| `--book-id` | `--novel-id` | `337` | Book ID on novelight.net |
| `--free-only` | | `True` | Only download free (unlocked) chapters |
| `--include-locked` | | `False` | Attempt to download locked chapters as well |
| `--volumes` | | `None` | Comma-separated volume numbers to download (e.g. `1,2,3`) |
| `--start-chapter` | `--start`, `-s` | `1` | 1-based start offset in the filtered chapter list |
| `--max-chapters` | `--chapters`, `-n` | `0` | Max chapters to download (`0` = all available) |
| `--fast` | | `False` | Fast download mode (`0.1s` delay, `0.05s` jitter) |
| `--delay` | `-d` | `0.5` | Base seconds delay between requests |
| `--jitter` | | `0.2` | Random variance (+/- seconds) applied to delay |
| `--title` | | `"Shut Up, Malevolent Dragon!..."` | Book title metadata in EPUB |
| `--author` | | `"Unknown"` | Book author metadata in EPUB |
| `--output-dir` | `-o` | `output` | Directory where files and EPUB are stored |
| `--epub-filename` | | `shut_up_malevolent_dragon.epub` | Filename of generated EPUB |
| `--cover` | | `None` | Path to book cover image (`.jpg` or `.png`) |
| `--css` | | `styles.css` | Path to custom stylesheet |
| `--force` | | `False` | Re-download chapters even if cached on disk |
| `--build-only` | | `False` | Skip scraping; build EPUB from existing chapter files |
| `--no-epub` | | `False` | Scrape and save HTML chapters without building EPUB |
| `--list-only` | | `False` | Fetch and display the chapter index table, then exit |
| `--verbose` | `-v` | `False` | Enable debug log output |

---

### Examples

#### List first 20 chapters:
```powershell
python scraper.py --list-only --max-chapters 20
```

#### Download only Volume 1:
```powershell
python scraper.py --volumes 1
```

#### Download Volumes 1 through 3:
```powershell
python scraper.py --volumes 1,2,3
```

#### Fast download mode (high throughput):
```powershell
python scraper.py --fast
```

#### Download a batch of 50 chapters starting from chapter 10:
```powershell
python scraper.py --start-chapter 10 --max-chapters 50
```

#### Resume an interrupted download:
Cached chapters are automatically detected on disk and skipped:
```powershell
python scraper.py
```

#### Rebuild EPUB from existing downloaded chapters:
```powershell
python scraper.py --build-only
```

---

## 📂 Project Structure

```
novelight_scraper/
├── config.py           # Module-level defaults and target novel configuration
├── fetcher.py          # HTTP and JSON requests, retry backoff, and rate limiting
├── parser.py           # HTML and JSON parser, ad remover, and Chapter data models
├── epub_builder.py     # Pandoc EPUB3 compiler with volume-nested TOC
├── scraper.py          # CLI entry point, argument parsing, Rich progress & logging
├── styles.css          # E-reader CSS styling for EPUB typography and volume headers
├── requirements.txt    # Python dependencies
├── tests/              # Automated unit tests (35 tests)
│   ├── test_fetcher.py
│   ├── test_parser.py
│   ├── test_epub_builder.py
│   ├── test_scraper.py
│   └── test_watermark_batch.py
└── output/             # (Ignored in git)
    ├── chapters/       # Volume-organized chapter HTML files (vol_01/chapter_0001.html)
    ├── pandoc_defaults.yaml # Generated Pandoc defaults file for large builds
    └── shut_up_malevolent_dragon.epub
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
