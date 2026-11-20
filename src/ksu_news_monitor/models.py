"""Data models and normalization helpers for KSU news monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from urllib.parse import parse_qs, urlparse


_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]+")
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def clean_text(text: str) -> str:
    """Remove zero-width characters and collapse whitespace."""
    cleaned = _INVISIBLE_RE.sub("", text or "")
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def truncate_text(text: str, max_len: int = 220) -> str:
    """Truncate text cleanly at word boundaries."""
    cleaned = clean_text(text)
    if len(cleaned) <= max_len:
        return cleaned
    clipped = cleaned[: max_len - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    if not clipped:
        clipped = cleaned[: max_len - 1]
    return f"{clipped}…"


def normalize_title(title: str) -> str:
    """Normalize a news title for cross-source duplicate detection."""
    cleaned = clean_text(title).lower()
    cleaned = _PUNCT_RE.sub(" ", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def normalize_url(url: str) -> str:
    """Normalize URL for duplicate comparison."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    query = parsed.query
    # Preserve newsId on kspu.edu/PublisherReader while ignoring culture/noise
    if "kspu.edu" in netloc and "publisherreader" in path.lower():
        qs = parse_qs(query)
        news_id = qs.get("newsId") or qs.get("newsid")
        if news_id:
            return f"https://kspu.edu/PublisherReader?newsId={news_id[0]}"
    base = f"{parsed.scheme.lower()}://{netloc}{path}"
    if query:
        base = f"{base}?{query}"
    return base


@dataclass(slots=True, frozen=True)
class NewsItem:
    """Normalized news item collected from any monitored source."""

    item_id: str
    source: str  # "kspu" | "google_news" | "telegram"
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""
    publisher: str = ""

    def published_utc(self) -> datetime | None:
        """Return publication timestamp normalized to UTC if available."""
        if self.published_at is None:
            return None
        if self.published_at.tzinfo is None:
            return self.published_at.replace(tzinfo=timezone.utc)
        return self.published_at.astimezone(timezone.utc)
