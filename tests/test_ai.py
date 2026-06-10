import pytest
from unittest.mock import patch
from gryptz.ai import GryptzScore, _parse_score
from gryptz.scanner import TokenData


SAMPLE_TOKEN = TokenData(
    ca="So11111111111111111111111111111111111111112",
    symbol="SOL", name="Solana", price_usd=150.0,
    liquidity_usd=100000, volume_1h=50000, volume_24h=500000,
    buy_ratio_1h=0.7, price_change_1h=5.0, price_change_24h=12.0,
    market_cap=70000000000, pair_url="", dex="raydium", chain="solana",
)


def test_parse_score_valid():
    raw = '{"score": 75, "rug_risk": "low", "momentum": "strong", "verdict": "Solid token.", "signals": ["high buy ratio", "good liquidity"]}'
    score = _parse_score(raw)
    assert score.score == 75
    assert score.rug_risk == "low"
    assert score.momentum == "strong"
    assert len(score.signals) == 2


def test_parse_score_with_markdown():
    raw = '```json\n{"score": 60, "rug_risk": "medium", "momentum": "moderate", "verdict": "Watch it.", "signals": []}\n```'
    score = _parse_score(raw)
    assert score.score == 60


def test_fallback_score():
    fb = GryptzScore.fallback()
    assert fb.score == 50
    assert fb.rug_risk == "unknown"


@pytest.mark.asyncio
async def test_score_token_calls_deepinfra():
    mock_response = '{"score": 80, "rug_risk": "low", "momentum": "strong", "verdict": "Strong momentum.", "signals": ["high buy pressure"]}'
    with patch("gryptz.ai._call_deepinfra", return_value=mock_response):
        from gryptz.ai import score_token
        result = await score_token(SAMPLE_TOKEN)
    assert result.score == 80
    assert result.rug_risk == "low"


@pytest.mark.asyncio
async def test_score_token_returns_fallback_on_error():
    with patch("gryptz.ai._call_deepinfra", side_effect=Exception("API down")):
        from gryptz.ai import score_token
        result = await score_token(SAMPLE_TOKEN)
    assert result.score == 50
