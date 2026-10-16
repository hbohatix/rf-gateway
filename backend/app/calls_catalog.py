"""Small public Broadcastify Calls discovery index (not the licensed audio API).

The public playlists page offers a complete published-playlist listing; the
Calls landing page only contains *sample* active nodes and groups. Neither is
represented as a complete searchable Calls system/group catalog.
"""
from __future__ import annotations

import re
import time
import threading
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, parse_qs

PUBLIC_URLS = {
    "playlist": "https://www.broadcastify.com/calls/public-playlists/",
    "group": "https://www.broadcastify.com/calls/",
    "node": "https://www.broadcastify.com/calls/",
}
CACHE_TTL_SECONDS = 600
MAX_PAGE_BYTES = 2 * 1024 * 1024


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def parse_catalog(html: str, kind: str) -> list[dict]:
    """Parse only known Calls link shapes; reject non-Broadcastify URLs."""
    if kind not in PUBLIC_URLS:
        raise ValueError("Invalid catalog kind")
    parser = _LinkParser()
    parser.feed(html)
    items = {}
    for href, name in parser.links:
        url = urljoin(PUBLIC_URLS[kind], href)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "www.broadcastify.com":
            continue
        if not name:
            continue
        value = None
        if kind == "playlist" and parsed.path.rstrip("/") == "/calls/playlists":
            uuid = parse_qs(parsed.query).get("uuid", [""])[0]
            if re.fullmatch(r"[A-Za-z0-9-]{8,64}", uuid):
                value = uuid
        elif kind == "group":
            match = re.fullmatch(r"/calls/tg/(\d+)/(\d+)/?", parsed.path)
            if match:
                value = f"{match.group(1)}-{match.group(2)}"
        elif kind == "node":
            match = re.fullmatch(r"/calls/node/(\d+)/?", parsed.path)
            if match:
                value = match.group(1)
        if value and value not in items:
            items[value] = {
                "kind": kind,
                "id": value,
                "name": name,
                "url": url,
            }
    return sorted(items.values(), key=lambda item: item["name"].casefold())


_lock = threading.RLock()
_cache: dict[str, tuple[float, list[dict]]] = {}


def search_public_catalog(kind: str, query: str = "", limit: int = 75) -> dict:
    if kind not in PUBLIC_URLS:
        raise ValueError("kind must be playlist, group or node")
    if not isinstance(query, str) or len(query) > 120:
        raise ValueError("Search phrase too long")
    limit = max(1, min(int(limit), 100))
    now = time.monotonic()
    with _lock:
        cached = _cache.get(kind)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            items = cached[1]
        else:
            req = urllib.request.Request(
                PUBLIC_URLS[kind],
                headers={
                    "User-Agent": "RF-Gateway/0.12 (public Calls catalog)",
                    "Accept": "text/html",
                },
            )
            # HTTPS only; fixed origin and no user-provided URL.
            with urllib.request.urlopen(req, timeout=12) as response:
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname != "www.broadcastify.com":
                    raise ValueError("Unexpected catalog redirect")
                raw = response.read(MAX_PAGE_BYTES + 1)
            if len(raw) > MAX_PAGE_BYTES:
                raise ValueError("Public catalog response too large")
            items = parse_catalog(raw.decode("utf-8", errors="replace"), kind)
            if not items:
                raise ValueError("Public catalog has no matching links (page may have changed)")
            _cache[kind] = (time.monotonic(), items)

    needle = query.strip().casefold()
    selected = [item for item in items if needle in item["name"].casefold() or needle in item["id"].casefold()]
    return {
        "kind": kind,
        "query": query,
        "count": len(selected),
        "items": selected[:limit],
        "catalog_scope": (
            "public_playlists" if kind == "playlist"
            else "live_sample_only"
        ),
        "complete": kind == "playlist",
    }
