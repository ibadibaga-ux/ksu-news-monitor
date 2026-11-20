"""Collector for official Kherson State University news (kspu.edu)."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import logging
from urllib.parse import parse_qs, urljoin, urlparse
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import requests

from ..config import KYIV_TZ
from ..models import NewsItem, clean_text, normalize_url, truncate_text

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "ksu-news-monitor/0.1 (+https://github.com/ibadibaga-ux/ksu-news-monitor)"
}


def _kspu_item_id(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    news_id = qs.get("newsId") or qs.get("newsid")
    if news_id and news_id[0].strip():
        return f"kspu:{news_id[0].strip()}"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"kspu:{digest}"


def parse_kspu_rss(xml_text: str, base_url: str = "https://kspu.edu") -> list[NewsItem]:
    """Parse kspu.edu/rss XML feed into NewsItem objects."""
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []

    for node in root.findall("./channel/item"):
        title = clean_text(node.findtext("title") or "")
        raw_link = (node.findtext("link") or node.findtext("guid") or "").strip()
        if not title or not raw_link:
            continue
        url = normalize_url(urljoin(base_url, raw_link))

        pub_at: datetime | None = None
        pub_raw = (node.findtext("pubDate") or "").strip()
        if pub_raw:
            try:
                dt = parsedate_to_datetime(pub_raw)
                pub_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pub_at = None

        desc_html = node.findtext("description") or ""
        desc_text = clean_text(BeautifulSoup(desc_html, "html.parser").get_text(" "))

        items.append(
            NewsItem(
                item_id=_kspu_item_id(url),
                source="kspu",
                title=title,
                url=url,
                published_at=pub_at,
                summary=truncate_text(desc_text, 220) if desc_text else "",
                publisher="kspu.edu",
            )
        )

    return items


def parse_kspu_html(html_text: str, base_url: str = "https://kspu.edu") -> list[NewsItem]:
    """Fallback HTML parser for kspu.edu/default news cards."""
    soup = BeautifulSoup(html_text, "html.parser")
    items: list[NewsItem] = []

    for article in soup.select("article.news-item"):
        title_link = article.select_one(".news-item__title a[href]")
        if not title_link:
            continue
        title = clean_text(title_link.get_text(" "))
        href = (title_link.get("href") or "").strip()
        if not title or not href:
            continue
        url = normalize_url(urljoin(base_url, href))

        pub_at: datetime | None = None
        time_el = article.select_one("time[datetime]")
        if time_el and time_el.get("datetime"):
            dt_str = str(time_el["datetime"]).strip()
            try:
                if len(dt_str) == 10:
                    # Date-only string like 2026-11-19 -> start of day in Kyiv
                    parsed = datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=KYIV_TZ)
                else:
                    parsed = datetime.fromisoformat(dt_str)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=KYIV_TZ)
                pub_at = parsed.astimezone(timezone.utc)
            except ValueError:
                pub_at = None

        desc_el = article.select_one(".news-item__description")
        desc_text = clean_text(desc_el.get_text(" ")) if desc_el else ""

        items.append(
            NewsItem(
                item_id=_kspu_item_id(url),
                source="kspu",
                title=title,
                url=url,
                published_at=pub_at,
                summary=truncate_text(desc_text, 220) if desc_text else "",
                publisher="kspu.edu",
            )
        )

    return items


def fetch_kspu_news(
    rss_url: str = "https://kspu.edu/rss",
    web_url: str = "https://kspu.edu/default",
    timeout: int = 20,
    session: requests.Session | None = None,
) -> list[NewsItem]:
    """Fetch news from kspu.edu RSS feed, falling back to HTML scraping on error."""
    http = session or requests.Session()
    try:
        resp = http.get(rss_url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        items = parse_kspu_rss(resp.text, base_url=rss_url)
        if items:
            logger.info("Fetched %d items from kspu.edu RSS", len(items))
            return items
        logger.warning("kspu.edu RSS returned 0 items, trying HTML fallback")
    except Exception as exc:
        logger.warning("kspu.edu RSS failed (%s), trying HTML fallback", exc)

    resp = http.get(web_url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    items = parse_kspu_html(resp.text, base_url=web_url)
    logger.info("Fetched %d items from kspu.edu HTML fallback", len(items))
    return items
