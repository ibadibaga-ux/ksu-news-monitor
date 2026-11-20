"""Collector for public Telegram channel web preview (t.me/s/<channel>)."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re

from bs4 import BeautifulSoup
import requests

from ..models import NewsItem, clean_text, truncate_text

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_title_and_summary(raw_lines: list[str]) -> tuple[str, str]:
    non_empty = [clean_text(line) for line in raw_lines if clean_text(line)]
    if not non_empty:
        return "Публікація в @ksuniver (медіа без тексту)", ""

    first_line = non_empty[0]
    rest = " ".join(non_empty[1:]).strip()

    if len(first_line) <= 140:
        return first_line, truncate_text(rest, 220) if rest else ""

    parts = _SENTENCE_SPLIT_RE.split(first_line, maxsplit=1)
    headline = truncate_text(parts[0], 140)
    tail_parts = []
    if len(parts) > 1 and parts[1].strip():
        tail_parts.append(parts[1].strip())
    if rest:
        tail_parts.append(rest)
    summary = truncate_text(" ".join(tail_parts), 220) if tail_parts else ""
    return headline, summary


def parse_telegram_channel_html(html_text: str, channel: str = "ksuniver") -> list[NewsItem]:
    """Parse https://t.me/s/<channel> HTML into NewsItem objects."""
    soup = BeautifulSoup(html_text, "html.parser")
    items: list[NewsItem] = []

    for msg in soup.select("div.tgme_widget_message[data-post]"):
        data_post = (msg.get("data-post") or "").strip()
        if not data_post or "/" not in data_post:
            continue

        date_link = msg.select_one("a.tgme_widget_message_date[href]")
        post_url = (
            str(date_link["href"]).strip()
            if date_link and date_link.get("href")
            else f"https://t.me/{data_post}"
        )

        pub_at: datetime | None = None
        time_el = msg.select_one("a.tgme_widget_message_date time[datetime]")
        if time_el and time_el.get("datetime"):
            dt_str = str(time_el["datetime"]).strip()
            try:
                parsed = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                pub_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pub_at = None

        text_el = msg.select_one(".tgme_widget_message_text")
        lines: list[str] = []
        if text_el is not None:
            for br in text_el.find_all("br"):
                br.replace_with("\n")
            raw_text = text_el.get_text()
            lines = [line for line in raw_text.splitlines()]

        title, summary = _split_title_and_summary(lines)

        # Include inline button link target if it adds useful context and text was media-only
        if not summary:
            inline_btn = msg.select_one("a.tgme_widget_message_inline_button[href]")
            if inline_btn and inline_btn.get_text(strip=True):
                btn_label = clean_text(inline_btn.get_text(" "))
                if btn_label and btn_label not in title:
                    summary = btn_label

        items.append(
            NewsItem(
                item_id=f"tg:{data_post}",
                source="telegram",
                title=title,
                url=post_url,
                published_at=pub_at,
                summary=summary,
                publisher=f"@{channel}",
            )
        )

    return items


def fetch_telegram_channel_news(
    channel: str = "ksuniver",
    timeout: int = 20,
    session: requests.Session | None = None,
) -> list[NewsItem]:
    """Fetch recent posts from a public Telegram channel via t.me/s/<channel>."""
    clean_channel = channel.lstrip("@").strip()
    url = f"https://t.me/s/{clean_channel}"
    http = session or requests.Session()
    resp = http.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    items = parse_telegram_channel_html(resp.text, channel=clean_channel)
    logger.info("Fetched %d posts from Telegram @%s", len(items), clean_channel)
    return items
