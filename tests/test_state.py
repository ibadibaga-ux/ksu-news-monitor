"""Tests for state.json persistence, deduplication, and pruning."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ksu_news_monitor.models import NewsItem
from ksu_news_monitor.state import StateStore


def test_state_dedup_by_id_url_and_title(tmp_path: Path):
    state_path = tmp_path / "state.json"
    now = datetime(2026, 11, 20, 7, 30, tzinfo=timezone.utc)

    store = StateStore.load(state_path)
    first = NewsItem(
        item_id="kspu:25721",
        source="kspu",
        title="У ХДУ відбувся тренінг із профорієнтаційної діяльності",
        url="https://kspu.edu/PublisherReader?newsId=25721",
        published_at=now - timedelta(hours=3),
    )
    store.mark_seen([first], digest_sent=True, now_utc=now)
    store.save()

    reloaded = StateStore.load(state_path)
    assert reloaded.last_digest_kyiv_date == "2026-11-20"

    candidates = [
        # Exact same ID
        first,
        # Same URL with different query param / www
        NewsItem(
            item_id="kspu:other",
            source="kspu",
            title="Інший заголовок",
            url="https://www.kspu.edu/PublisherReader?newsId=25721&culture=uk",
            published_at=now - timedelta(hours=2),
        ),
        # Same normalized title from Google News
        NewsItem(
            item_id="gnews:abc123",
            source="google_news",
            title="У ХДУ відбувся тренінг із профорієнтаційної діяльності!",
            url="https://news.google.com/rss/articles/xyz",
            published_at=now - timedelta(hours=1),
        ),
        # Too old (> 72h)
        NewsItem(
            item_id="tg:ksuniver/1786",
            source="telegram",
            title="Стара публікація",
            url="https://t.me/ksuniver/1786",
            published_at=now - timedelta(days=30),
        ),
        # Truly new and recent
        NewsItem(
            item_id="gnews:fresh1",
            source="google_news",
            title="Нова публікація про Херсонський державний університет",
            url="https://news.google.com/rss/articles/fresh1",
            published_at=now - timedelta(hours=5),
        ),
    ]

    fresh = reloaded.filter_new_items(candidates, max_age_hours=72, now_utc=now)
    assert [item.item_id for item in fresh] == ["gnews:fresh1"]


def test_state_batch_dedup_and_pruning(tmp_path: Path):
    now = datetime(2026, 11, 20, 7, 30, tzinfo=timezone.utc)
    store = StateStore(path=tmp_path / "state.json")

    dup_batch = [
        NewsItem(
            item_id="gnews:1",
            source="google_news",
            title="Херсонський державний університет відкрив набір",
            url="https://news.google.com/rss/articles/1",
            published_at=now - timedelta(hours=2),
        ),
        NewsItem(
            item_id="gnews:2",
            source="google_news",
            title="Херсонський державний університет відкрив набір",
            url="https://news.google.com/rss/articles/2",
            published_at=now - timedelta(hours=1),
        ),
    ]
    fresh = store.filter_new_items(dup_batch, max_age_hours=72, now_utc=now)
    assert len(fresh) == 1

    old_ts = (now - timedelta(days=200)).isoformat()
    recent_ts = (now - timedelta(days=1)).isoformat()
    store.seen = {
        "old:1": {"first_seen_at": old_ts},
        "recent:1": {"first_seen_at": recent_ts},
    }
    removed = store.prune(retention_days=180, max_items=100, now_utc=now)
    assert removed == 1
    assert "recent:1" in store.seen
    assert "old:1" not in store.seen
