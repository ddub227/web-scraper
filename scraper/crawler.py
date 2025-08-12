import asyncio
import contextlib
import re
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx

from .extractors import (
    extract_image_sources,
    extract_links,
    extract_metadata,
    extract_pagination_next_links,
    extract_structured_data,
    extract_text_content,
)
from .storage import StorageManager
from .utils import (
    guess_filename_for_url,
    is_allowed_domain,
    normalize_url,
    should_render_heuristic,
)


@dataclass
class CrawlTask:
    url: str
    depth: int


class PlaywrightManager:
    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def ensure_browser(self):
        async with self._lock:
            if self._browser is not None:
                return
            try:
                from playwright.async_api import async_playwright  # type: ignore
            except Exception as e:
                raise RuntimeError("Playwright is not installed. Install it or run with --render never.") from e
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)

    async def render_content(self, url: str, timeout_ms: int = 30000) -> str:
        if self._browser is None:
            await self.ensure_browser()
        assert self._playwright is not None
        assert self._browser is not None
        context = await self._browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = await page.content()
            return html
        finally:
            await context.close()

    async def close(self):
        with contextlib.suppress(Exception):
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()


class AsyncCrawler:
    def __init__(
        self,
        start_urls: Iterable[str],
        output_dir: str,
        allowed_domains: Iterable[str],
        max_pages: int = 200,
        max_depth: int = 5,
        max_concurrency: int = 8,
        request_timeout_s: float = 20.0,
        user_agent: str = "Mozilla/5.0 (compatible; SiteScraper/1.0; +https://example.com/bot)",
        robots: bool = True,
        render: str = "auto",  # 'auto' | 'always' | 'never'
        download_images: bool = True,
        per_host_limit: int = 4,
        delay_ms: int = 0,
    ) -> None:
        self.start_urls = list(start_urls)
        self.output_dir = output_dir
        self.allowed_domains = list(allowed_domains)
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.render_mode = render
        self.download_images = download_images
        self.delay_ms = delay_ms

        limits = httpx.Limits(max_connections=max_concurrency, max_keepalive_connections=max_concurrency)
        self.client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            timeout=httpx.Timeout(request_timeout_s, connect=request_timeout_s),
            limits=limits,
            http2=True,
        )
        self.storage = StorageManager(output_dir)
        self.playwright = PlaywrightManager() if render != "never" else None

        self.visited: Set[str] = set()
        self.queue: asyncio.Queue[CrawlTask] = asyncio.Queue()
        self.enqueued: Set[str] = set()
        self.pages_processed = 0

        self._per_host_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._per_host_limit = per_host_limit
        self._global_semaphore = asyncio.Semaphore(max_concurrency)

        # Cache robot parser per base URL
        self._robots_parsers: Dict[str, object] = {}
        self._robots_enabled = robots

    def _host_semaphore(self, url: str) -> asyncio.Semaphore:
        host = urlparse(url).netloc
        if host not in self._per_host_semaphores:
            self._per_host_semaphores[host] = asyncio.Semaphore(self._per_host_limit)
        return self._per_host_semaphores[host]

    async def _robots_allows(self, url: str) -> bool:
        if not self._robots_enabled:
            return True
        from urllib import robotparser

        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._robots_parsers.get(base)
        if rp is None:
            rp = robotparser.RobotFileParser()
            robots_url = base + "/robots.txt"
            try:
                r = await self.client.get(robots_url)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:
                    rp.disallow_all = False  # type: ignore[attr-defined]
            except Exception:
                rp.disallow_all = False  # type: ignore[attr-defined]
            self._robots_parsers[base] = rp
        return rp.can_fetch(self.client.headers["User-Agent"], url)  # type: ignore[return-value]

    async def _fetch_http(self, url: str) -> Optional[Tuple[str, Optional[str]]]:
        try:
            r = await self.client.get(url)
            ct = r.headers.get("content-type", "").lower()
            if r.status_code == 200 and ("text/html" in ct or ct.startswith("application/xhtml")):
                return r.text, r.headers.get("content-disposition")
        except Exception:
            return None
        return None

    async def _download_image(self, url: str, content_disposition: Optional[str]) -> Optional[str]:
        try:
            r = await self.client.get(url)
            if r.status_code == 200 and r.content:
                filename = guess_filename_for_url(url, r.headers.get("content-disposition") or content_disposition)
                return await self.storage.save_binary(url, r.content, filename)
        except Exception:
            return None
        return None

    async def _process_page(self, url: str, html: str, content_disposition: Optional[str]) -> None:
        metadata = extract_metadata(html, url)
        text_content = extract_text_content(html)
        structured = extract_structured_data(html, url)
        links = extract_links(html, url)
        next_links = extract_pagination_next_links(html, url)
        images = extract_image_sources(html, url) if self.download_images else []

        html_path = await self.storage.save_html(url, html)

        image_saves: List[Tuple[str, Optional[str]]] = []
        if self.download_images and images:
            sem = asyncio.Semaphore(8)

            async def save_one(img_url: str) -> None:
                async with sem:
                    saved = await self._download_image(img_url, content_disposition)
                    image_saves.append((img_url, saved))

            await asyncio.gather(*(save_one(i) for i in images))

        record = {
            "url": url,
            "html_path": html_path,
            "metadata": metadata,
            "structured_data": structured,
            "text": text_content,
            "links": links,
            "pagination_next_links": next_links,
            "images": [{"src": src, "saved_path": path} for src, path in image_saves],
        }
        await self.storage.append_jsonl(record)

        # Enqueue discovered links with incremented depth
        next_depth = 1
        for href in links + next_links:
            norm = normalize_url(url, href)
            if not norm:
                continue
            if norm in self.enqueued or norm in self.visited:
                continue
            if not is_allowed_domain(norm, self.allowed_domains):
                continue
            await self.queue.put(CrawlTask(norm, next_depth))
            self.enqueued.add(norm)

    async def _handle_task(self, task: CrawlTask) -> None:
        if self.pages_processed >= self.max_pages:
            return
        if task.url in self.visited:
            return
        if task.depth > self.max_depth:
            return
        if not is_allowed_domain(task.url, self.allowed_domains):
            return
        if not await self._robots_allows(task.url):
            return

        self.visited.add(task.url)

        # Optional per-host and global throttling
        await self._global_semaphore.acquire()
        host_sem = self._host_semaphore(task.url)
        await host_sem.acquire()
        try:
            if self.delay_ms:
                await asyncio.sleep(self.delay_ms / 1000.0)

            http_result = await self._fetch_http(task.url)
            html, content_disposition = (http_result or (None, None))
            needs_render = False

            if self.render_mode == "always":
                needs_render = True
            elif self.render_mode == "auto":
                if not html or should_render_heuristic(html):
                    needs_render = True

            if needs_render and self.playwright is not None:
                try:
                    rendered = await self.playwright.render_content(task.url)
                    if rendered:
                        html = rendered
                except Exception:
                    pass

            if not html:
                return

            await self._process_page(task.url, html, content_disposition)
            self.pages_processed += 1
        finally:
            host_sem.release()
            self._global_semaphore.release()

    async def run(self) -> None:
        for url in self.start_urls:
            self.enqueued.add(url)
            await self.queue.put(CrawlTask(url, 0))

        workers = []
        num_workers = max(2, min(32, self._global_semaphore._value))  # type: ignore[attr-defined]
        async def worker() -> None:
            while self.pages_processed < self.max_pages:
                try:
                    task = await asyncio.wait_for(self.queue.get(), timeout=1.5)
                except asyncio.TimeoutError:
                    if self.pages_processed >= self.max_pages:
                        break
                    # no task
                    continue
                try:
                    await self._handle_task(task)
                finally:
                    self.queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(num_workers)]
        await self.queue.join()
        for w in workers:
            w.cancel()
        with contextlib.suppress(Exception):
            await asyncio.gather(*workers)
        await self.client.aclose()
        if self.playwright:
            await self.playwright.close()