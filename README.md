# 📖 Web Novel Scraper → EPUB (Novelight & Fenrir Realm)

A robust, configurable Python CLI tool that downloads web novel chapters from **Novelight** (`novelight.net`) and **Fenrir Realm** (`fenrirealm.com`), cleans junk markup, watermarks, and advertisements, dynamically adapts volume and chapter hierarchies, auto-downloads cover images, and compiles novels into clean, beautifully styled EPUB3 ebooks using Pandoc.

---

## ✨ Features

- **Multi-Platform Support**:
  - **Novelight (`novelight.net`)**: High-speed direct extraction via Novelight's pagination and chapter JSON APIs (`/book/ajax/read-chapter/{id}`).
  - **Fenrir Realm (`fenrirealm.com`)**: Headless browser automation powered by Playwright with stealth evasions to navigate Cloudflare Turnstile anti-bot challenges and extract clean chapter prose.
  - **Smart Dispatch (`--source auto`)**: Automatically detects the target platform directly from the URL.

- **Dynamic Metadata & Naming (No Manual Flags Needed)**:
  - Automatically fetches official title, author, synopsis/description, genres, tags, and status.
  - Automatically derives a clean, filesystem-safe novel slug and EPUB filename (e.g. `solo-leveling.epub`).
  - Embeds novel description and metadata directly into the EPUB3 metadata block.
  - User-provided CLI flags (`--title`, `--author`, `--epub-filename`) cleanly override auto-detected values when supplied.

- **Automatic Cover Image Fetching & Embedding**:
  - Automatically resolves and downloads the official cover image for both Novelight and Fenrir Realm novels.
  - Caches the cover image inside the novel's directory (`output/<novel-slug>/cover.jpg`).
  - Automatically embeds the cover as the standard EPUB3 cover page via Pandoc without requiring manual `--cover` arguments.

- **Adaptive Volume Handling (No Artificial Volumes)**:
  - **Real Multi-Volume Novels**: Generates a 2-level nested Table of Contents (**Volume X** → **Chapters**), inserts volume title divider pages (`<h1>Volume X</h1>`), formats chapter headings as `Vol. X Ch. Y - Title` (`<h2>`), and compiles with `toc-depth: 2` and `split-level: 2`.
  - **Flat-Chapter Novels**: Flat novels (such as all Fenrir Realm novels and flat Novelight series) automatically compile into a clean 1-level TOC with `Ch. X - Title` headings (`<h1>`), `toc-depth: 1`, `split-level: 1`, and completely omit artificial "Volume 1" pages.

- **Isolated Per-Novel Directory Structure**:
  - Every novel is isolated under its own directory (`output/<novel-slug>/`).
  - Dedicated `output/<novel-slug>/pandoc_defaults.yaml`, `output/<novel-slug>/chapters/`, `output/<novel-slug>/cover.jpg`, and `output/<novel-slug>/<novel-slug>.epub` ensure zero collisions or stale metadata when scraping multiple series.

- **Advanced Content & Watermark Cleaning**:
  - Strips obfuscated Novelight watermarks across homoglyphs, invisible symbols, zero-width spaces, and attached promotional notices while preserving authentic prose typography (curly quotes, em-dashes, ellipses).
  - Automatically strips redundant headers, banner ads, and navigation scripts.

- **Large-Novel Pandoc Compilation (1,000+ Chapters)**:
  - Generates a dedicated Pandoc defaults file (`pandoc_defaults.yaml`) per novel, bypassing Windows command-line argument limits (the 32,767 character limit) when compiling massive web novel series.

- **Resilience & Politeness**:
  - Automatic retries on rate limits (`429`) and server errors (`5xx`) with exponential backoff.
  - Rate limiting with randomized jitter (`--delay`, `--jitter`, or high-throughput `--fast`).
  - Automatic caching and resume: skips already-downloaded chapters on disk.
  - Graceful exit: `Ctrl+C` safely halts downloads and compiles whatever chapters have been downloaded so far.

- **Rich Terminal UI & Series Inspection (`--info`)**:
  - `--info` fetches and presents an overview table with synopsis, availability (free vs. locked chapters), and suggested download commands without downloading.
  - Real-time progress bar with chapter counts, volume/chapter indicators, elapsed time, and ETA.
  - Chapter list preview mode (`--list-only`) to inspect chapters without downloading.

---

## 🚀 Requirements & Installation

### 1. System Dependency: Pandoc

Pandoc is required to generate EPUB files:

- **Windows** (winget):
  ```powershell
  winget install --id JohnMacFarlane.Pandoc
  ```
  Or download the installer from [pandoc.org](https://pandoc.org/installing.html).
- **macOS**: `brew install pandoc`
- **Linux**: `sudo apt install pandoc`

### 2. Python Environment & Dependencies

Requires **Python 3.10+**.

```powershell
# Clone or navigate to the project directory
mkdir "d:\Web Novel Downloader"
cd "d:\Web Novel Downloader"
git clone https://github.com/WDWaleed/web-novel-downloader.git .

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser engine (required for Fenrir Realm)
playwright install chromium
```

---

## 🛠️ Usage

### Quick Start: Inspect Novel Info

Inspect novel metadata, availability, and description without downloading anything:

```powershell
# Novelight series
python scraper.py --info https://novelight.net/book/shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you

# Fenrir Realm series
python scraper.py --info https://fenrirealm.com/series/absolute-regression
```

### Quick Start: Download & Compile to EPUB

Simply pass the novel URL (positionally or via `--url`):

```powershell
# Scrape Novelight web novel
python scraper.py https://novelight.net/book/shut-up-malevolent-dragon-i-dont-want-to-have-any-more-children-with-you

# Scrape Fenrir Realm web novel
python scraper.py https://fenrirealm.com/series/absolute-regression
```

The scraper will:

1. Detect the platform and fetch novel metadata (title, author, cover, description).
2. Download all free chapters into `output/<novel-slug>/chapters/`.
3. Auto-download the cover image to `output/<novel-slug>/cover.jpg`.
4. Compile an EPUB into `output/<novel-slug>/<novel-slug>.epub`.

---

### Common CLI Options

| Argument           | Shorthand                      | Default       | Description                                                                    |
| ------------------ | ------------------------------ | ------------- | ------------------------------------------------------------------------------ |
| `URL`              | `--url`, `--book-url`          | `None`        | Novel URL on Novelight or Fenrir Realm (pass positionally or via `--url`)      |
| `--info`           | `--fetch-info`, `--novel-info` | `False`       | Display novel overview, metadata, and chapter availability without downloading |
| `--source`         |                                | `auto`        | Target source platform: `auto`, `novelight`, or `fenrirealm`                   |
| `--start-chapter`  | `--start`, `-s`                | `1`           | 1-based start offset in chapter list (or chapter number for Fenrir Realm)      |
| `--max-chapters`   | `--chapters`, `-n`             | `0`           | Maximum number of chapters to download (`0` = all available)                   |
| `--fast`           |                                | `False`       | Fast download mode (`0.1s` delay, `0.05s` jitter)                              |
| `--delay`          | `-d`                           | `0.5`         | Base delay in seconds between chapter requests                                 |
| `--jitter`         |                                | `0.2`         | Random variation (+/- seconds) added to delay                                  |
| `--free-only`      |                                | `True`        | Only download free (unlocked) chapters (Novelight)                             |
| `--include-locked` |                                | `False`       | Attempt to download locked/premium chapters (Novelight)                        |
| `--volumes`        |                                | `None`        | Comma-separated volume numbers to download, e.g. `1,2,3` (Novelight)           |
| `--output-dir`     | `-o`                           | `output`      | Root output directory; automatically subfolders per novel slug                 |
| `--epub-filename`  |                                | `<slug>.epub` | Custom EPUB filename (defaults to sanitized novel title)                       |
| `--title`          |                                | Auto          | Custom EPUB book title metadata (defaults to fetched novel title)              |
| `--author`         |                                | Auto          | Custom EPUB author metadata (defaults to fetched novel author)                 |
| `--cover`          |                                | Auto          | Custom path to book cover image (defaults to auto-downloading official cover)  |
| `--css`            |                                | `styles.css`  | Path to custom CSS stylesheet for EPUB e-reader styling                        |
| `--force`          |                                | `False`       | Force re-download of chapters and cover even if cached on disk                 |
| `--build-only`     |                                | `False`       | Skip downloading and compile EPUB directly from existing saved chapter files   |
| `--no-epub`        |                                | `False`       | Download and save HTML chapters without compiling into an EPUB                 |
| `--list-only`      |                                | `False`       | Display the chapter index table and exit (Novelight)                           |
| `--verbose`        | `-v`                           | `False`       | Enable verbose debug logging output                                            |

---

### Examples

#### Download with High Throughput (`--fast`)

```powershell
python scraper.py "https://novelight.net/book/ghost-story" --fast
```

#### Download a Specific Chapter Range

```powershell
# Download 50 chapters starting from chapter 10
python scraper.py "https://fenrirealm.com/series/absolute-regression" --start 10 --max-chapters 50
```

#### Filter by Volume (Novelight Multi-Volume Novels)

```powershell
# Download only Volume 1
python scraper.py "https://novelight.net/book/ghost-story" --volumes 1

# Download Volumes 1 and 2
python scraper.py "https://novelight.net/book/ghost-story" --volumes 1,2
```

#### Resume an Interrupted Download

Cached chapters are automatically detected on disk and skipped:

```powershell
python scraper.py "https://novelight.net/book/ghost-story"
```

#### Rebuild EPUB from Existing Saved Files

Recompile an EPUB at any time without fetching from the web:

```powershell
python scraper.py "https://novelight.net/book/ghost-story" --build-only
```

#### Provide Custom Metadata & Overrides

```powershell
python scraper.py "https://fenrirealm.com/series/absolute-regression" `
  --title "Absolute Regression: Definitive Edition" `
  --author "Custom Author" `
  --cover "my_custom_cover.jpg" `
  --epub-filename "absolute_regression_v1.epub"
```

---

## 📂 Project Structure

```
Web Novel Downloader/
├── config.py                 # Default settings, timeouts, and fallback configurations
├── utils.py                  # Shared helpers: source detection, slug extraction, output dir resolution
├── fetcher.py                # HTTP requests, session management, retry logic, cover downloader
├── parser.py                 # Novelight HTML/JSON parser, metadata dataclasses, watermark removal
├── epub_builder.py           # Pandoc EPUB3 compiler, defaults generator, adaptive volume handler
├── scraper.py                # CLI entry point, argument parsing, dispatch, Rich progress & tables
├── styles.css                # Clean e-reader CSS typography and volume divider styling
├── requirements.txt          # Python package requirements
├── fenrirealm/               # Fenrir Realm scraping package
│   ├── __init__.py
│   ├── fetcher.py            # Playwright headless browser automation & anti-bot bypass
│   ├── parser.py             # Series overview info parser & chapter content extractor
│   └── scraper.py            # Fenrir Realm download orchestrator & sequential crawler
├── tests/                    # Comprehensive automated unit test suite (110 tests)
│   ├── test_scraper.py
│   ├── test_fetcher.py
│   ├── test_epub_builder.py
│   ├── test_novel_info.py
│   ├── test_parser.py
│   ├── test_fenrirealm_parser.py
│   └── test_watermark_batch.py
└── output/                   # Default storage root (per-novel isolated subdirectories)
    └── <novel-slug>/
        ├── chapters/         # Saved chapter HTML files (vol_XX/ or flat chapter_XXXX.html)
        ├── cover.jpg         # Auto-downloaded novel cover image
        ├── pandoc_defaults.yaml # Novel-specific Pandoc compilation configuration
        └── <novel-slug>.epub # Compiled EPUB3 ebook
```

---

## 🧪 Running Tests

Run the full automated test suite with Python's built-in `unittest`:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_scraper tests.test_fetcher tests.test_epub_builder tests.test_novel_info tests.test_parser tests.test_fenrirealm_parser
```

---

## 📄 License

MIT License.
