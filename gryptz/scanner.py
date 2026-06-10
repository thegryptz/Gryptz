from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

from .config import (
    DEXSCREENER_BASE,
    MIN_BUY_RATIO,
    MIN_LIQUIDITY_USD,
    MIN_VOLUME_1H_USD,
)

log = logging.getLogger(__name__)


@dataclass
class TokenData:
    ca: str
    symbol: str
    name: str
    price_usd: float
    liquidity_usd: float
    volume_1h: float
    volume_24h: float
    buy_ratio_1h: float
    price_change_1h: float
    price_change_24h: float
    market_cap: float
    pair_url: str
    dex: str
    chain: str
    created_at: Optional[str] = None
    extra: dict = field(default_factory=dict)


def _parse_pair(p: dict) -> Optional[TokenData]:
    try:
        base = p.get("baseToken", {})
        liq = p.get("liquidity", {})
        vol = p.get("volume", {})
        txns = p.get("txns", {})
        chg = p.get("priceChange", {})

        liq_usd = float(liq.get("usd", 0) or 0)
        vol_1h = float(vol.get("h1", 0) or 0)
        vol_24h = float(vol.get("h24", 0) or 0)

        h1_txns = txns.get("h1", {})
        buys = int(h1_txns.get("buys", 0) or 0)
        sells = int(h1_txns.get("sells", 0) or 0)
        total_txns = buys + sells
        buy_ratio = buys / total_txns if total_txns > 0 else 0.5

        return TokenData(
            ca=base.get("address", ""),
            symbol=base.get("symbol", ""),
            name=base.get("name", ""),
            price_usd=float(p.get("priceUsd", 0) or 0),
            liquidity_usd=liq_usd,
            volume_1h=vol_1h,
            volume_24h=vol_24h,
            buy_ratio_1h=buy_ratio,
            price_change_1h=float(chg.get("h1", 0) or 0),
            price_change_24h=float(chg.get("h24", 0) or 0),
            market_cap=float(p.get("marketCap", 0) or 0),
            pair_url=p.get("url", ""),
            dex=p.get("dexId", ""),
            chain=p.get("chainId", ""),
            created_at=p.get("pairCreatedAt"),
        )
    except Exception as e:
        log.debug("parse_pair error: %s", e)
        return None


def _get_trending_solana() -> list[TokenData]:
    url = f"{DEXSCREENER_BASE}/token-profiles/latest/v1"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        profiles = resp.json()

        sol_cas = [
            p["tokenAddress"]
            for p in profiles
            if p.get("chainId") == "solana" and p.get("tokenAddress")
        ][:30]
        if not sol_cas:
            return []

        batch = ",".join(sol_cas)
        resp2 = requests.get(
            f"{DEXSCREENER_BASE}/tokens/v1/solana/{batch}", timeout=15
        )
        resp2.raise_for_status()
        pairs = resp2.json()
        if isinstance(pairs, dict):
            pairs = pairs.get("pairs", [])
    except Exception as e:
        log.warning("DexScreener trending fetch failed: %s", e)
        return []

    tokens: list[TokenData] = []
    seen_ca: set[str] = set()
    for p in (pairs or []):
        tok = _parse_pair(p)
        if tok and tok.ca and tok.ca not in seen_ca:
            seen_ca.add(tok.ca)
            tokens.append(tok)

    return tokens


def _get_token_by_ca(ca: str) -> Optional[TokenData]:
    try:
        resp = requests.get(
            f"{DEXSCREENER_BASE}/tokens/v1/solana/{ca}", timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        pairs = data if isinstance(data, list) else data.get("pairs", [])
        if not pairs:
            return None
        pairs_sorted = sorted(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
        return _parse_pair(pairs_sorted[0])
    except Exception as e:
        log.warning("DexScreener CA fetch failed for %s: %s", ca, e)
        return None


def filter_tokens(tokens: list[TokenData]) -> list[TokenData]:
    return [
        t for t in tokens
        if t.liquidity_usd >= MIN_LIQUIDITY_USD
        and t.volume_1h >= MIN_VOLUME_1H_USD
        and t.buy_ratio_1h >= MIN_BUY_RATIO
    ]


async def scan_trending() -> list[TokenData]:
    raw = await asyncio.to_thread(_get_trending_solana)
    return filter_tokens(raw)


async def get_token(ca: str) -> Optional[TokenData]:
    return await asyncio.to_thread(_get_token_by_ca, ca)
