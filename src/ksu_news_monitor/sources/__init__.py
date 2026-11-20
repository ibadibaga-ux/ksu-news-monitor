"""News source collectors for ksu-news-monitor."""

from .google_news import fetch_google_news
from .kspu import fetch_kspu_news
from .telegram_channel import fetch_telegram_channel_news

__all__ = [
    "fetch_kspu_news",
    "fetch_google_news",
    "fetch_telegram_channel_news",
]
