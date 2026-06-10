from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from .ai import score_tokens, GryptzScore
from .config import MIN_GRYPTZ_SCORE, SCAN_INTERVAL
from .notifier import notify_batch
from .scanner import TokenData, scan_trending

log = logging.getLogger(__name__)

_latest_results: list[tuple[TokenData, GryptzScore]] = []
_scan_meta: dict = {}


def get_latest() -> list[tuple[TokenData, GryptzScore]]:
    return _latest_results


def get_scan_meta() -> dict:
    return _scan_meta


async def _run_once(on_result: Optional[Callable] = None) -> None:
    global _latest_results, _scan_meta
    log.info("Scanning trending Solana tokens...")
    tokens = await scan_trending()
    log.info("Found %d tokens after filters", len(tokens))

    if not tokens:
        _scan_meta = {"ts": time.time(), "total": 0, "signals": 0}
        return

    pairs = await score_tokens(tokens)
    _latest_results = sorted(pairs, key=lambda x: x[1].score, reverse=True)

    signals = [(t, s) for t, s in _latest_results if s.score >= MIN_GRYPTZ_SCORE]
    _scan_meta = {
        "ts": time.time(),
        "total": len(_latest_results),
        "signals": len(signals),
    }
    log.info("%d tokens scored >= %d", len(signals), MIN_GRYPTZ_SCORE)

    await notify_batch(_latest_results, min_score=MIN_GRYPTZ_SCORE)

    if on_result:
        await on_result(_latest_results)


async def scan_loop(on_result: Optional[Callable] = None) -> None:
    while True:
        try:
            await _run_once(on_result)
        except Exception as e:
            log.error("Scan loop error: %s", e)
        await asyncio.sleep(SCAN_INTERVAL)
