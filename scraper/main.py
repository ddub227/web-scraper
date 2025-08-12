import argparse
import asyncio
import os
from typing import List

from .crawler import AsyncCrawler


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Automated web scraper for text, images, structured data, and metadata.")
    p.add_argument("start_urls", nargs="+", help="One or more starting URLs to crawl")
    p.add_argument("--output-dir", default="./scrape_output", help="Directory to store outputs")
    p.add_argument("--allowed-domains", nargs="*", default=[], help="Restrict crawling to these domains (and subdomains)")
    p.add_argument("--max-pages", type=int, default=200, help="Maximum number of pages to process")
    p.add_argument("--max-depth", type=int, default=5, help="Maximum crawl depth")
    p.add_argument("--concurrency", type=int, default=8, help="Maximum global concurrency")
    p.add_argument("--per-host", type=int, default=4, help="Maximum connections per host")
    p.add_argument("--timeout", type=float, default=20.0, help="Request timeout in seconds")
    p.add_argument("--user-agent", default="Mozilla/5.0 (compatible; SiteScraper/1.0; +https://example.com/bot)")
    p.add_argument("--no-robots", action="store_true", help="Ignore robots.txt")
    p.add_argument("--render", choices=["auto", "always", "never"], default="auto", help="Use Playwright rendering policy")
    p.add_argument("--no-images", action="store_true", help="Do not download images")
    p.add_argument("--delay-ms", type=int, default=0, help="Optional delay between requests in milliseconds")
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    os.makedirs(args.output_dir, exist_ok=True)
    crawler = AsyncCrawler(
        start_urls=args.start_urls,
        output_dir=args.output_dir,
        allowed_domains=args.allowed_domains,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_concurrency=args.concurrency,
        per_host_limit=args.per_host,
        request_timeout_s=args.timeout,
        user_agent=args.user_agent,
        robots=not args.no_robots,
        render=args.render,
        download_images=not args.no_images,
        delay_ms=args.delay_ms,
    )
    await crawler.run()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()