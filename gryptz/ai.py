from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

import requests

from .config import DEEPINFRA_API_KEY, DEEPINFRA_BASE_URL, DEEPINFRA_MODEL
from .scanner import TokenData

log = logging.getLogger(__name__)

SCORE_PROMPT = """You are Gryptz, a Solana token analyst. Analyze this token and return a JSON score.

Token Data:
- Symbol: {symbol}
- Name: {name}
- Price: ${price:.8f}
- Liquidity: ${liquidity:,.0f}
- Volume 1h: ${vol_1h:,.0f}
- Volume 24h: ${vol_24h:,.0f}
- Buy Ratio 1h: {buy_ratio:.1%}
- Price Change 1h: {chg_1h:+.1f}%
- Price Change 24h: {chg_24h:+.1f}%
- Market Cap: ${mcap:,.0f}
- DEX: {dex}

Analyze and return ONLY valid JSON (no markdown, no explanation):
{{
  "score": <integer 0-100>,
  "rug_risk": <"low"|"medium"|"high">,
  "momentum": <"weak"|"moderate"|"strong">,
  "verdict": "<1 sentence max, brutal honest assessment>",
  "signals": ["<signal1>", "<signal2>", "<signal3>"]
}}

Score guidelines:
- 80-100: Strong buy signal, solid liquidity + momentum + low risk
- 60-79: Decent opportunity, worth watching
- 40-59: Neutral, mixed signals
- 20-39: Weak, high risk
- 0-19: Likely rug or dead"""


@dataclass
class GryptzScore:
    score: int
    rug_risk: str
    momentum: str
    verdict: str
    signals: list[str]

    @classmethod
    def fallback(cls) -> "GryptzScore":
        return cls(
            score=50,
            rug_risk="unknown",
            momentum="unknown",
            verdict="AI analysis unavailable.",
            signals=[],
        )


def _call_deepinfra(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPINFRA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.2,
    }
    resp = requests.post(
        f"{DEEPINFRA_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _parse_score(raw: str) -> GryptzScore:
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON in response")
    data = json.loads(raw[start:end])
    return GryptzScore(
        score=int(data.get("score", 50)),
        rug_risk=data.get("rug_risk", "unknown"),
        momentum=data.get("momentum", "unknown"),
        verdict=data.get("verdict", ""),
        signals=data.get("signals", []),
    )


def _score_token_sync(token: TokenData) -> GryptzScore:
    prompt = SCORE_PROMPT.format(
        symbol=token.symbol,
        name=token.name,
        price=token.price_usd,
        liquidity=token.liquidity_usd,
        vol_1h=token.volume_1h,
        vol_24h=token.volume_24h,
        buy_ratio=token.buy_ratio_1h,
        chg_1h=token.price_change_1h,
        chg_24h=token.price_change_24h,
        mcap=token.market_cap,
        dex=token.dex,
    )
    try:
        raw = _call_deepinfra(prompt)
        return _parse_score(raw)
    except Exception as e:
        log.warning("AI score failed for %s: %s", token.symbol, e)
        return GryptzScore.fallback()


async def score_token(token: TokenData) -> GryptzScore:
    return await asyncio.to_thread(_score_token_sync, token)


async def score_tokens(tokens: list[TokenData]) -> list[tuple[TokenData, GryptzScore]]:
    tasks = [score_token(t) for t in tokens]
    scores = await asyncio.gather(*tasks)
    return list(zip(tokens, scores))
