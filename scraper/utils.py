import hashlib
import os
import re
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_eid",
}


def compute_sha1(data: bytes) -> str:
    sha1 = hashlib.sha1()
    sha1.update(data)
    return sha1.hexdigest()


def sanitize_filename(name: str, max_length: int = 140) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name[:max_length] or "file"


def strip_fragment_and_tracking(url: str) -> str:
    parsed = urlparse(url)
    # Drop fragment
    parsed = parsed._replace(fragment="")
    # Remove common tracking params
    query_pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    parsed = parsed._replace(query=urlencode(query_pairs))
    return urlunparse(parsed)


def normalize_url(base_url: str, href: str) -> Optional[str]:
    if not href:
        return None
    # Ignore javascript:, mailto:, tel:
    if re.match(r"^(javascript:|mailto:|tel:)", href, re.I):
        return None
    absolute = urljoin(base_url, href)
    return strip_fragment_and_tracking(absolute)


def is_allowed_domain(url: str, allowed_domains: Iterable[str]) -> bool:
    if not allowed_domains:
        return True
    netloc = urlparse(url).netloc.lower()
    for domain in allowed_domains:
        d = domain.lower().lstrip(".")
        if netloc == d or netloc.endswith("." + d):
            return True
    return False


def guess_filename_for_url(url: str, content_disposition: Optional[str] = None) -> str:
    filename = None
    if content_disposition:
        match = re.search(r'filename\*?="?([^";]+)"?', content_disposition)
        if match:
            filename = match.group(1)
    if not filename:
        path = urlparse(url).path
        filename = os.path.basename(path) or "index.html"
    return sanitize_filename(filename)


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def should_render_heuristic(html: str) -> bool:
    # Render if page looks empty or heavily JS-driven
    # Heuristics: very low text, many scripts, common SPA markers
    text_len = len(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", html or "")))
    script_count = len(re.findall(r"<script[\s>]", html or "", re.I))
    spa_markers = [
        "id=\"__next\"",
        "data-reactroot",
        "ng-version",
        "id=\"app\"",
        "id=\"root\"",
    ]
    has_spa_marker = any(m in (html or "") for m in spa_markers)
    return (text_len < 400 and script_count >= 5) or has_spa_marker