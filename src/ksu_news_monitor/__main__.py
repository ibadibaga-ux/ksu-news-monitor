"""CLI entry point for KSU news monitor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
import os
import sys

import requests

from .config import Config, KYIV_TZ, is_scheduled_kyiv_run_due
from .formatter import build_digest_messages
from .models import NewsItem
from .notifier import send_telegram_messages
from .sources import (
    fetch_google_news,
    fetch_kspu_news,
    fetch_telegram_channel_news,
)
from .state import StateStore

logger = logging.getLogger("ksu_news_monitor")


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def run_monitor(config: Config, *, now_utc: datetime | None = None) -> int:
    """Execute one monitoring cycle and return process exit code."""
    ref = now_utc or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    state = StateStore.load(config.state_path)
    today_kyiv = ref.astimezone(KYIV_TZ).date().isoformat()
    if (
        not config.force
        and not config.dry_run
        and state.last_digest_kyiv_date == today_kyiv
    ):
        logger.info(
            "Digest already sent today (%s Kyiv time). Skipping duplicate run.",
            today_kyiv,
        )
        return 0

    all_items: list[NewsItem] = []
    warnings: list[str] = []
    succeeded_sources = 0

    with requests.Session() as session:
        collectors = (
            (
                "kspu.edu",
                lambda: fetch_kspu_news(
                    rss_url=config.kspu_rss_url,
                    web_url=config.kspu_web_url,
                    timeout=config.request_timeout,
                    session=session,
                ),
            ),
            (
                "Google News RSS",
                lambda: fetch_google_news(
                    queries=config.google_news_queries,
                    timeout=config.request_timeout,
                    session=session,
                ),
            ),
            (
                f"Telegram @{config.telegram_channel}",
                lambda: fetch_telegram_channel_news(
                    channel=config.telegram_channel,
                    timeout=config.request_timeout,
                    session=session,
                ),
            ),
        )

        for name, collector in collectors:
            try:
                items = collector()
                all_items.extend(items)
                succeeded_sources += 1
            except Exception as exc:
                logger.exception("Failed to collect from %s: %s", name, exc)
                warnings.append(f"Не вдалося отримати дані з {name}")

    if succeeded_sources == 0:
        logger.error("All news sources failed. Aborting without updating state.")
        return 1

    new_items = state.filter_new_items(
        all_items,
        max_age_hours=config.max_age_hours,
        now_utc=ref,
    )
    logger.info(
        "Collected %d total items; %d new items within last %dh",
        len(all_items),
        len(new_items),
        config.max_age_hours,
    )

    should_send = bool(new_items) or config.send_empty_digest
    if not should_send:
        logger.info("No new items found and SEND_EMPTY_DIGEST=false; nothing to send.")
        if not config.dry_run:
            state.mark_seen([], digest_sent=False, now_utc=ref)
            state.prune(
                retention_days=config.state_retention_days,
                max_items=config.max_state_items,
                now_utc=ref,
            )
            state.save()
        return 0

    messages = build_digest_messages(
        new_items,
        now_utc=ref,
        warnings=warnings or None,
    )

    if config.dry_run:
        logger.info("DRY RUN enabled — printing %d digest message(s):", len(messages))
        for idx, msg in enumerate(messages, start=1):
            print(f"\n--- MESSAGE {idx}/{len(messages)} ---\n{msg}\n")
        return 0

    send_telegram_messages(
        config.telegram_bot_token,
        config.telegram_chat_id,
        messages,
        timeout=config.request_timeout,
    )

    state.mark_seen(new_items, digest_sent=True, now_utc=ref)
    state.prune(
        retention_days=config.state_retention_days,
        max_items=config.max_state_items,
        now_utc=ref,
    )
    state.save()
    logger.info("Updated %s with %d new item(s).", config.state_path, len(new_items))
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(description="KSU daily news monitor")
    parser.add_argument(
        "--check-schedule",
        action="store_true",
        help="Check if GitHub Actions schedule cron matches current Europe/Kyiv DST offset.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not send or save state.")
    parser.add_argument("--force", action="store_true", help="Bypass same-day digest guard.")
    args = parser.parse_args(argv)

    if args.check_schedule:
        event_name = os.getenv("GITHUB_EVENT_NAME", "local")
        schedule_cron = os.getenv("GITHUB_EVENT_SCHEDULE", "")
        due, reason = is_scheduled_kyiv_run_due(event_name, schedule_cron)
        logger.info(reason)
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as f:
                f.write(f"should_run={'true' if due else 'false'}\n")
        print(f"should_run={'true' if due else 'false'}")
        return 0

    config = Config.from_env()
    if args.dry_run:
        config.dry_run = True
    if args.force:
        config.force = True

    return run_monitor(config)


if __name__ == "__main__":
    sys.exit(main())
