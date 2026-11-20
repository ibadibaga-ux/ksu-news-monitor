"""Collector for Google News RSS mentions of Kherson State University."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import logging
import re
from urllib.parse import quote, urlparse
import xml.etree.ElementTree as ET

import requests

from ..config import DEFAULT_GOOGLE_NEWS_QUERIES
from ..models import NewsItem, clean_text

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "ksu-news-monitor/0.1 (+https://github.com/ibadibaga-ux/ksu-news-monitor)"
}

_RELEVANT_PATTERNS = (
    re.compile(r"херсонськ\w*\s+державн\w*\s+університет", re.I),
    re.compile(r"херсонск\w*\s+государственн\w*\s+университет", re.I),
    re.compile(r"херсонськ\w*\s+університет", re.I),
    re.compile(r"kherson\s+state\s+university", re.I),
    re.compile(r"kspu\.edu", re.I),
    re.compile(r"\bхду\b", re.I),
)

_FALSE_POSITIVE_PATTERNS = (
    re.compile(r"аграрн", re.I),
    re.compile(r"agrarian", re.I),
    re.compile(r"національний технічний університет", re.I),
    re.compile(r"national technical university", re.I),
)


def is_relevant_ksu_news(title: str, source_url: str = "") -> bool:
    """Ensure Google News results actually refer to Kherson State University (KSU)."""
    if "kspu.edu" in source_url.lower():
        return True
    has_match = any(p.search(title) for p in _RELEVANT_PATTERNS)
    if not has_match:
        return False
    # Reject unrelated Kherson universities unless KSU is explicitly named too
    if any(p.search(title) for p in _FALSE_POSITIVE_PATTERNS):
        explicit_ksu = (
            re.search(r"херсонськ\w*\s+державн\w*\s+університет", title, re.I)
            or re.search(r"kherson\s+state\s+university", title, re.I)
            or re.search(r"\bхду\b", title, re.I)
        )
        return bool(explicit_ksu)
    return True


def _strip_publisher_suffix(title: str, publisher: str) -> str:
    if publisher:
        suffix = f" - {publisher}"
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title


def parse_google_news_rss(
    xml_text: str,
    *,
    skip_kspu_domain: bool = True,
) -> list[NewsItem]:
    """Parse Google News RSS search XML into NewsItem objects."""
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []

    for node in root.findall("./channel/item"):
        raw_title = clean_text(node.findtext("title") or "")
        link = (node.findtext("link") or "").strip()
        guid = clean_text(node.findtext("guid") or "")
        if not raw_title or not link:
            continue

        source_el = node.find("source")
        publisher = clean_text(source_el.text or "") if source_el is not None else ""
        source_url = (source_el.attrib.get("url", "") if source_el is not None else "").strip()

        if skip_kspu_domain and "kspu.edu" in urlparse(source_url).netloc.lower():
            continue

        title = _strip_publisher_suffix(raw_title, publisher)
        if not is_relevant_ksu_news(title, source_url):
            continue

        pub_at: datetime | None = None
        pub_raw = (node.findtext("pubDate") or "").strip()
        if pub_raw:
            try:
                dt = parsedate_to_datetime(pub_raw)
                pub_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pub_at = None

        key_base = guid or link
        key_hash = hashlib.sha1(key_base.encode("utf-8")).hexdigest()[:16]

        items.append(
            NewsItem(
                item_id=f"gnews:{key_hash}",
                source="google_news",
                title=title,
                url=link,
                published_at=pub_at,
                summary="",
                publisher=publisher,
            )
        )

    return items


def fetch_google_news(
    queries: tuple[tuple[str, str, str, str], ...] = DEFAULT_GOOGLE_NEWS_QUERIES,
    timeout: int = 20,
    session: requests.Session | None = None,
) -> list[NewsItem]:
    """Fetch KSU news across configured Google News RSS queries."""
    http = session or requests.Session()
    collected: list[NewsItem] = []
    seen_ids: set[str] = set()

    for query, hl, gl, ceid in queries:
        rss_url = (
            "https://news.google.com/rss/search"
            f"?q={quote(query)}&hl={quote(hl)}&gl={quote(gl)}&ceid={quote(ceid)}"
        )
        resp = http.get(rss_url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        parsed = parse_google_news_rss(resp.text)
        for item in parsed:
            if item.item_id not in seen_ids:
                seen_ids.add(item.item_id)
                collected.append(item)

    logger.info("Fetched %d items from Google News RSS", len(collected))
    return collected
