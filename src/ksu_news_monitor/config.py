"""Configuration and Europe/Kyiv DST schedule utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from zoneinfo import ZoneInfo


KYIV_TZ = ZoneInfo("Europe/Kyiv")
SUMMER_CRON = "30 6 * * *"  # 09:30 EEST (UTC+3)
WINTER_CRON = "30 7 * * *"  # 09:30 EET (UTC+2)

DEFAULT_GOOGLE_NEWS_QUERIES: tuple[tuple[str, str, str, str], ...] = (
    ('"Херсонський державний університет"', "uk", "UA", "UA:uk"),
    ('"Kherson State University"', "en", "US", "US:en"),
)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def expected_kyiv_cron(now_utc: datetime | None = None) -> str:
    """Return the UTC cron expression corresponding to 09:30 in Europe/Kyiv."""
    ref = now_utc or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    now_kyiv = ref.astimezone(KYIV_TZ)
    offset = now_kyiv.utcoffset()
    if offset == timedelta(hours=3):
        return SUMMER_CRON
    return WINTER_CRON


def is_scheduled_kyiv_run_due(
    event_name: str,
    schedule_cron: str = "",
    now_utc: datetime | None = None,
) -> tuple[bool, str]:
    """Determine whether a GitHub Actions trigger should run the 09:30 Kyiv digest.

    Because GitHub Actions cron triggers only support UTC, the workflow registers both
    ``30 6 * * *`` (summer EEST, UTC+3) and ``30 7 * * *`` (winter EET, UTC+2).
    Matching ``github.event.schedule`` against the current Europe/Kyiv UTC offset
    handles DST transitions accurately even if GitHub Actions delays job startup.
    """
    if event_name != "schedule":
        return True, f"Non-schedule trigger ({event_name or 'local'}): running."

    expected = expected_kyiv_cron(now_utc)
    normalized_cron = " ".join((schedule_cron or "").split())
    ref = now_utc or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    kyiv_now = ref.astimezone(KYIV_TZ)

    if not normalized_cron:
        # Fallback if cron string is unavailable: allow 09:00-10:29 Kyiv
        in_window = kyiv_now.hour == 9 or (kyiv_now.hour == 10 and kyiv_now.minute < 30)
        return in_window, f"Kyiv time {kyiv_now.isoformat()} (expected cron {expected})."

    if normalized_cron == expected:
        return True, (
            f"Schedule '{normalized_cron}' matches active Europe/Kyiv offset "
            f"({kyiv_now.strftime('%Y-%m-%d %H:%M %Z')})."
        )

    return False, (
        f"Skipping schedule '{normalized_cron}': active Europe/Kyiv offset requires "
        f"'{expected}' ({kyiv_now.strftime('%Y-%m-%d %H:%M %Z')})."
    )


@dataclass(slots=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    state_path: Path = Path("state.json")
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_channel: str = "ksuniver"
    kspu_rss_url: str = "https://kspu.edu/rss"
    kspu_web_url: str = "https://kspu.edu/default"
    google_news_queries: tuple[tuple[str, str, str, str], ...] = field(
        default_factory=lambda: DEFAULT_GOOGLE_NEWS_QUERIES
    )
    max_age_hours: int = 72
    request_timeout: int = 20
    send_empty_digest: bool = False
    dry_run: bool = False
    force: bool = False
    max_state_items: int = 1500
    state_retention_days: int = 180

    @classmethod
    def from_env(cls) -> "Config":
        raw_queries = os.getenv("GOOGLE_NEWS_QUERIES", "").strip()
        if raw_queries:
            queries = tuple(
                (q.strip(), "uk", "UA", "UA:uk")
                for q in raw_queries.split(";")
                if q.strip()
            )
        else:
            queries = DEFAULT_GOOGLE_NEWS_QUERIES

        return cls(
            state_path=Path(os.getenv("STATE_PATH", "state.json")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            telegram_channel=os.getenv("TELEGRAM_CHANNEL", "ksuniver").lstrip("@").strip()
            or "ksuniver",
            kspu_rss_url=os.getenv("KSPU_RSS_URL", "https://kspu.edu/rss").strip(),
            kspu_web_url=os.getenv("KSPU_WEB_URL", "https://kspu.edu/default").strip(),
            google_news_queries=queries,
            max_age_hours=max(1, _parse_int(os.getenv("MAX_AGE_HOURS"), 72)),
            request_timeout=max(5, _parse_int(os.getenv("REQUEST_TIMEOUT"), 20)),
            send_empty_digest=_parse_bool(os.getenv("SEND_EMPTY_DIGEST"), False),
            dry_run=_parse_bool(os.getenv("DRY_RUN"), False),
            force=_parse_bool(os.getenv("FORCE_RUN"), False),
        )
