"""Persistent state management and duplicate protection in state.json."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from .config import KYIV_TZ
from .models import NewsItem, normalize_title, normalize_url


@dataclass
class StateStore:
    """Manages state.json for deduplicating news items across runs."""

    path: Path
    version: int = 1
    last_run_at: str | None = None
    last_digest_kyiv_date: str | None = None
    seen: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "StateStore":
        if not path.exists():
            return cls(path=path)
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return cls(path=path)
        data = json.loads(raw)
        seen = data.get("seen")
        if not isinstance(seen, dict):
            seen = {}
        return cls(
            path=path,
            version=int(data.get("version", 1)),
            last_run_at=data.get("last_run_at"),
            last_digest_kyiv_date=data.get("last_digest_kyiv_date"),
            seen=seen,
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "last_run_at": self.last_run_at,
            "last_digest_kyiv_date": self.last_digest_kyiv_date,
            "seen": self.seen,
        }
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def _seen_indexes(self) -> tuple[set[str], set[str]]:
        urls: set[str] = set()
        titles: set[str] = set()
        for entry in self.seen.values():
            if not isinstance(entry, dict):
                continue
            norm_url = normalize_url(str(entry.get("url", "")))
            if norm_url:
                urls.add(norm_url)
            norm_title = normalize_title(str(entry.get("title", "")))
            if norm_title:
                titles.add(norm_title)
        return urls, titles

    def filter_new_items(
        self,
        items: list[NewsItem],
        *,
        max_age_hours: int,
        now_utc: datetime | None = None,
    ) -> list[NewsItem]:
        """Return only unseen, sufficiently recent items without duplicates."""
        ref = now_utc or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        cutoff = ref - timedelta(hours=max_age_hours)

        seen_urls, seen_titles = self._seen_indexes()
        batch_ids: set[str] = set()
        batch_urls: set[str] = set()
        batch_titles: set[str] = set()

        fresh: list[NewsItem] = []
        for item in items:
            if item.item_id in self.seen or item.item_id in batch_ids:
                continue

            pub_utc = item.published_utc()
            if pub_utc is not None and pub_utc < cutoff:
                continue

            norm_url = normalize_url(item.url)
            if norm_url and (norm_url in seen_urls or norm_url in batch_urls):
                continue

            norm_title = normalize_title(item.title)
            if norm_title and len(norm_title) >= 12 and (
                norm_title in seen_titles or norm_title in batch_titles
            ):
                continue

            batch_ids.add(item.item_id)
            if norm_url:
                batch_urls.add(norm_url)
            if norm_title:
                batch_titles.add(norm_title)
            fresh.append(item)

        return fresh

    def mark_seen(
        self,
        items: list[NewsItem],
        *,
        digest_sent: bool,
        now_utc: datetime | None = None,
    ) -> None:
        """Record sent items and run timestamps into state."""
        ref = now_utc or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        now_iso = ref.isoformat()
        self.last_run_at = now_iso
        if digest_sent:
            self.last_digest_kyiv_date = ref.astimezone(KYIV_TZ).date().isoformat()

        for item in items:
            pub_utc = item.published_utc()
            self.seen[item.item_id] = {
                "source": item.source,
                "title": item.title,
                "url": item.url,
                "published_at": pub_utc.isoformat() if pub_utc else None,
                "first_seen_at": now_iso,
            }

    def prune(
        self,
        *,
        retention_days: int = 180,
        max_items: int = 1500,
        now_utc: datetime | None = None,
    ) -> int:
        """Prune entries older than retention_days while capping total entries."""
        if not self.seen:
            return 0
        ref = now_utc or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        cutoff = ref - timedelta(days=retention_days)

        kept: list[tuple[str, dict[str, Any], datetime]] = []
        removed = 0
        for key, entry in self.seen.items():
            if not isinstance(entry, dict):
                removed += 1
                continue
            ts_raw = entry.get("first_seen_at") or entry.get("published_at")
            ts = ref
            if isinstance(ts_raw, str) and ts_raw:
                try:
                    parsed = datetime.fromisoformat(ts_raw)
                    ts = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    ts = ref
            if ts < cutoff:
                removed += 1
                continue
            kept.append((key, entry, ts))

        if len(kept) > max_items:
            kept.sort(key=lambda row: row[2], reverse=True)
            removed += len(kept) - max_items
            kept = kept[:max_items]

        self.seen = {key: entry for key, entry, _ in kept}
        return removed
