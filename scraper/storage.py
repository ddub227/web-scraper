import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles

from .utils import compute_sha1, sanitize_filename


class StorageManager:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.pages_dir = self.base_dir / "pages"
        self.assets_dir = self.base_dir / "assets"
        self.images_dir = self.assets_dir / "images"
        self.jsonl_path = self.base_dir / "data.jsonl"
        self._jsonl_lock = asyncio.Lock()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    async def append_jsonl(self, record: Dict[str, Any]) -> None:
        text = json.dumps(record, ensure_ascii=False) + "\n"
        async with self._jsonl_lock:
            async with aiofiles.open(self.jsonl_path, mode="a", encoding="utf-8") as f:
                await f.write(text)

    async def save_html(self, url: str, html: str) -> str:
        # Use a hash to avoid path length issues and ensure uniqueness
        sha = compute_sha1(url.encode("utf-8"))
        filename = f"{sha}.html"
        full_path = self.pages_dir / filename
        async with aiofiles.open(full_path, mode="w", encoding="utf-8") as f:
            await f.write(html)
        return str(full_path)

    async def save_binary(self, url: str, content: bytes, suggested_filename: Optional[str] = None) -> str:
        if suggested_filename:
            filename = sanitize_filename(suggested_filename)
        else:
            sha = compute_sha1(content)
            filename = f"{sha}"
        full_path = self.images_dir / filename
        async with aiofiles.open(full_path, mode="wb") as f:
            await f.write(content)
        return str(full_path)