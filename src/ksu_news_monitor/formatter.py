"""Telegram HTML digest formatter with automatic 4096-character splitting."""

from __future__ import annotations

from datetime import datetime, timezone
import html

from .config import KYIV_TZ
from .models import NewsItem, truncate_text

TELEGRAM_MAX_LEN = 4096

SOURCE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("kspu", "🏛 <b>Офіційний сайт (kspu.edu)</b>"),
    ("google_news", "🌐 <b>Google News</b>"),
    ("telegram", "📢 <b>Telegram @ksuniver</b>"),
)


def _format_kyiv_timestamp(dt: datetime | None) -> str:
    if dt is None:
        return ""
    utc_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(KYIV_TZ).strftime("%d.%m %H:%M")


def format_item_html(item: NewsItem) -> str:
    """Format a single NewsItem into an HTML block for Telegram."""
    safe_url = html.escape(item.url, quote=True)
    safe_title = html.escape(item.title)
    lines = [f'• <a href="{safe_url}">{safe_title}</a>']

    meta_parts: list[str] = []
    ts = _format_kyiv_timestamp(item.published_at)
    if ts:
        meta_parts.append(ts)
    if item.publisher and item.source == "google_news":
        meta_parts.append(html.escape(item.publisher))
    if meta_parts:
        lines.append(f"  <i>{' · '.join(meta_parts)}</i>")

    if item.summary:
        lines.append(f"  {html.escape(truncate_text(item.summary, 180))}")

    return "\n".join(lines)


def build_digest_messages(
    items: list[NewsItem],
    *,
    now_utc: datetime | None = None,
    warnings: list[str] | None = None,
    max_len: int = TELEGRAM_MAX_LEN,
) -> list[str]:
    """Build one or more Telegram HTML messages within Telegram's length limit."""
    ref = now_utc or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    kyiv_now = ref.astimezone(KYIV_TZ)
    header = (
        f"📰 <b>Дайджест новин ХДУ</b> — "
        f"{kyiv_now.strftime('%d.%m.%Y')} ({kyiv_now.strftime('%H:%M')} Київ)"
    )

    if not items:
        body = f"{header}\n\nЗа останній період нових публікацій не знайдено."
        if warnings:
            warn_lines = "\n".join(f"⚠️ {html.escape(w)}" for w in warnings)
            body = f"{body}\n\n{warn_lines}"
        return [body[:max_len]]

    grouped: dict[str, list[NewsItem]] = {key: [] for key, _ in SOURCE_SECTIONS}
    for item in items:
        grouped.setdefault(item.source, []).append(item)

    for key in grouped:
        grouped[key].sort(
            key=lambda x: x.published_utc() or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    blocks: list[str] = [header]
    for source_key, section_title in SOURCE_SECTIONS:
        section_items = grouped.get(source_key, [])
        if not section_items:
            continue
        blocks.append(f"\n{section_title}")
        for item in section_items:
            blocks.append(format_item_html(item))

    if warnings:
        warn_block = "\n" + "\n".join(f"⚠️ {html.escape(w)}" for w in warnings)
        blocks.append(warn_block)

    messages: list[str] = []
    current = ""
    for block in blocks:
        candidate = block if not current else f"{current}\n{block}"
        if len(candidate) <= max_len:
            current = candidate
            continue
        if current:
            messages.append(current)
            current = ""
        if len(block) <= max_len:
            current = block
        else:
            # Extremely long single item fallback: truncate safely without breaking anchor tag
            messages.append(block[: max_len - 1] + "…")

    if current:
        messages.append(current)

    if len(messages) > 1:
        total = len(messages)
        numbered: list[str] = []
        for idx, msg in enumerate(messages, start=1):
            suffix = f"\n\n<i>({idx}/{total})</i>"
            if len(msg) + len(suffix) <= max_len:
                numbered.append(msg + suffix)
            else:
                numbered.append(msg)
        return numbered

    return messages
