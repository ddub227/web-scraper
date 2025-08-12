from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from w3lib.html import get_base_url

from .utils import collapse_whitespace


def extract_links(html: str, page_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    base_url = get_base_url(html, page_url)
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if href:
            links.append(urljoin(base_url, href))
    return links


def extract_pagination_next_links(html: str, page_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    base_url = get_base_url(html, page_url)
    candidates: List[str] = []
    # <link rel="next" href="...">
    for link in soup.find_all("link", rel=lambda x: x and "next" in x):
        href = link.get("href")
        if href:
            candidates.append(urljoin(base_url, href))
    # anchors with rel/aria-label/text hints
    for a in soup.find_all("a", href=True):
        text = collapse_whitespace(a.get_text(" "))[:100].lower()
        rel = (a.get("rel") or [])
        aria = (a.get("aria-label") or "").lower()
        if ("next" in rel) or ("next" in aria) or ("next" in text) or ("older" in text) or ("more" in text):
            candidates.append(urljoin(base_url, a["href"]))
    return list(dict.fromkeys(candidates))


def extract_text_content(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    # Remove script/style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    # Collapse excessive blank lines
    lines = [collapse_whitespace(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_metadata(html: str, page_url: str) -> Dict[str, Optional[str]]:
    soup = BeautifulSoup(html, "lxml")
    meta: Dict[str, Optional[str]] = {}

    # Title
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    meta["title"] = title

    # Meta description/keywords
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        meta["meta_description"] = desc.get("content").strip()
    keyw = soup.find("meta", attrs={"name": "keywords"})
    if keyw and keyw.get("content"):
        meta["meta_keywords"] = keyw.get("content").strip()

    # OpenGraph basic fields
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        meta["og_title"] = og_title.get("content").strip()
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        meta["og_description"] = og_desc.get("content").strip()
    og_type = soup.find("meta", property="og:type")
    if og_type and og_type.get("content"):
        meta["og_type"] = og_type.get("content").strip()
    og_url = soup.find("meta", property="og:url")
    if og_url and og_url.get("content"):
        meta["og_url"] = og_url.get("content").strip()

    # Canonical
    canonical = soup.find("link", rel=lambda x: x and "canonical" in x)
    if canonical and canonical.get("href"):
        meta["canonical"] = canonical.get("href").strip()

    return meta


def extract_structured_data(html: str, page_url: str) -> Dict[str, List[dict]]:
    # Minimal structured data: extract JSON-LD only to avoid heavy deps
    soup = BeautifulSoup(html, "lxml")
    jsonld_list: List[dict] = []
    for script in soup.find_all("script", type=lambda t: t and "ld+json" in t):
        try:
            import json
            data = json.loads(script.string or script.get_text() or "")
            if isinstance(data, list):
                jsonld_list.extend([d for d in data if isinstance(d, dict)])
            elif isinstance(data, dict):
                jsonld_list.append(data)
        except Exception:
            continue
    return {"json-ld": jsonld_list}


def extract_image_sources(html: str, page_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    base_url = get_base_url(html, page_url)
    srcs: List[str] = []
    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-original", "data-lazy-src"]:
            val = img.get(attr)
            if val:
                srcs.append(urljoin(base_url, val))
                break
    # De-duplicate while preserving order
    return list(dict.fromkeys(srcs))