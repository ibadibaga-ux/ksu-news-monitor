"""Tests for Telegram HTML digest formatting and message splitting."""

from datetime import datetime, timezone

from ksu_news_monitor.formatter import TELEGRAM_MAX_LEN, build_digest_messages
from ksu_news_monitor.models import NewsItem


def test_formatter_escapes_html_and_groups_sources():
    now = datetime(2026, 11, 20, 7, 30, tzinfo=timezone.utc)
    items = [
        NewsItem(
            item_id="kspu:1",
            source="kspu",
            title="Новина <ХДУ> & партнерство",
            url="https://kspu.edu/PublisherReader?newsId=1",
            published_at=now,
            summary="Короткий опис <тест>",
        ),
        NewsItem(
            item_id="gnews:1",
            source="google_news",
            title="ЗМІ про ХДУ",
            url="https://news.google.com/rss/articles/1",
            published_at=now,
            publisher="Інтент",
        ),
    ]
    msgs = build_digest_messages(items, now_utc=now)
    assert len(msgs) == 1
    assert "Новина &lt;ХДУ&gt; &amp; партнерство" in msgs[0]
    assert "Офіційний сайт (kspu.edu)" in msgs[0]
    assert "Google News" in msgs[0]
    assert "09:30" in msgs[0]


def test_formatter_splits_over_4096_chars():
    now = datetime(2026, 11, 20, 7, 30, tzinfo=timezone.utc)
    items = [
        NewsItem(
            item_id=f"kspu:{i}",
            source="kspu",
            title=f"Дуже важливий заголовок новини ХДУ номер {i} про академічні події",
            url=f"https://kspu.edu/PublisherReader?newsId={i}",
            published_at=now,
            summary="Детальний опис події в Херсонському державному університеті " * 3,
        )
        for i in range(40)
    ]
    msgs = build_digest_messages(items, now_utc=now)
    assert len(msgs) > 1
    assert all(len(m) <= TELEGRAM_MAX_LEN for m in msgs)
    assert "(1/" in msgs[0]
