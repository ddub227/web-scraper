# Automated Web Scraper (Async + Optional Rendering)

This tool crawls a website and extracts:
- Text content
- Images (saved to disk)
- Structured data (JSON-LD, Microdata, RDFa, OpenGraph)
- Metadata (title, meta description, canonical, OG tags)

It supports pagination discovery, same-domain restrictions, robots.txt, per-host throttling, and optional JavaScript rendering via Playwright.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Optional: install Playwright browser for rendering
python -m playwright install chromium
```

## Usage

```bash
python -m scraper.main https://example.com \
  --allowed-domains example.com \
  --output-dir ./scrape_output \
  --max-pages 100 \
  --render auto
```

Output files:
- `scrape_output/data.jsonl`: one JSON record per page
- `scrape_output/pages/<hash>.html`: saved HTML snapshot
- `scrape_output/assets/images/`: downloaded images

Flags of interest:
- `--render {auto,always,never}`: control Playwright rendering
- `--no-images`: skip image downloads
- `--no-robots`: ignore robots.txt (be polite!)
- `--allowed-domains`: restrict to listed domains
- `--delay-ms`: add delay between requests

## Notes
- Rendering requires Playwright and the browser binaries installed.
- Respect target sites' terms of service and robots.txt. Use responsibly.