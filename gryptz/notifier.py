from __future__ import annotations

import asyncio
import logging

import requests

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from .ai import GryptzScore
from .formatter import format_alert
from .scanner import TokenData

log = logging.getLogger(__name__)


def _send_sync(text: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
        timeout=10,
    ).raise_for_status()


async def notify_signal(token: TokenData, score: GryptzScore) -> None:
    if not TELEGRAM_CHAT_ID:
        return
    text = format_alert(token, score)
    try:
        await asyncio.to_thread(_send_sync, text, TELEGRAM_CHAT_ID)
    except Exception as e:
        log.warning("Telegram notify failed: %s", e)


async def notify_batch(pairs: list[tuple[TokenData, GryptzScore]], min_score: int = 60) -> None:
    top = sorted(pairs, key=lambda x: x[1].score, reverse=True)
    for token, score in top:
        if score.score >= min_score:
            await notify_signal(token, score)
            await asyncio.sleep(1)
