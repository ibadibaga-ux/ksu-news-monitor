"""Telegram Bot API sender for digest delivery."""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


def send_telegram_messages(
    bot_token: str,
    chat_id: str,
    messages: list[str],
    *,
    timeout: int = 20,
    session: requests.Session | None = None,
) -> None:
    """Send preformatted HTML messages to Telegram via Bot API."""
    if not bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is not set. Configure it in GitHub Actions Secrets."
        )
    if not chat_id:
        raise ValueError(
            "TELEGRAM_CHAT_ID is not set. Configure it in GitHub Actions Secrets."
        )

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    http = session or requests.Session()

    for idx, text in enumerate(messages, start=1):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = http.post(api_url, json=payload, timeout=timeout)
        if resp.status_code == 429:
            retry_after = 3
            try:
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 3))
            except Exception:
                retry_after = 3
            logger.warning("Telegram rate limit hit; sleeping %ds", retry_after)
            time.sleep(retry_after)
            resp = http.post(api_url, json=payload, timeout=timeout)

        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error on message {idx}: {body}")

        logger.info("Sent Telegram digest part %d/%d", idx, len(messages))
        if idx < len(messages):
            time.sleep(0.5)
