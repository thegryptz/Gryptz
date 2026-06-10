import pytest
from unittest.mock import patch, MagicMock
from gryptz.scanner import TokenData, filter_tokens, _parse_pair


SAMPLE_PAIR = {
    "baseToken": {"address": "So11111111111111111111111111111111111111112", "symbol": "SOL", "name": "Solana"},
    "priceUsd": "150.00",
    "liquidity": {"usd": 100000},
    "volume": {"h1": 50000, "h24": 500000},
    "txns": {"h1": {"buys": 70, "sells": 30}},
    "priceChange": {"h1": 5.2, "h24": 12.1},
    "marketCap": 70000000000,
    "url": "https://dexscreener.com/solana/test",
    "dexId": "raydium",
    "chainId": "solana",
}


def test_parse_pair_valid():
    token = _parse_pair(SAMPLE_PAIR)
    assert token is not None
    assert token.symbol == "SOL"
    assert token.buy_ratio_1h == pytest.approx(0.7)
    assert token.liquidity_usd == 100000
    assert token.volume_1h == 50000


def test_parse_pair_missing_txns():
    pair = {**SAMPLE_PAIR, "txns": {}}
    token = _parse_pair(pair)
    assert token is not None
    assert token.buy_ratio_1h == pytest.approx(0.5)


def test_filter_tokens_passes():
    token = TokenData(
        ca="abc", symbol="TEST", name="Test", price_usd=1.0,
        liquidity_usd=10000, volume_1h=20000, volume_24h=100000,
        buy_ratio_1h=0.65, price_change_1h=3.0, price_change_24h=10.0,
        market_cap=5000000, pair_url="", dex="raydium", chain="solana",
    )
    result = filter_tokens([token])
    assert len(result) == 1


def test_filter_tokens_blocks_low_liq():
    token = TokenData(
        ca="abc", symbol="RUG", name="Rug", price_usd=0.001,
        liquidity_usd=100, volume_1h=20000, volume_24h=100000,
        buy_ratio_1h=0.65, price_change_1h=50.0, price_change_24h=200.0,
        market_cap=10000, pair_url="", dex="raydium", chain="solana",
    )
    result = filter_tokens([token])
    assert len(result) == 0


def test_filter_tokens_blocks_low_buy_ratio():
    token = TokenData(
        ca="abc", symbol="DUMP", name="Dump", price_usd=0.01,
        liquidity_usd=50000, volume_1h=15000, volume_24h=100000,
        buy_ratio_1h=0.3, price_change_1h=-10.0, price_change_24h=-30.0,
        market_cap=500000, pair_url="", dex="raydium", chain="solana",
    )
    result = filter_tokens([token])
    assert len(result) == 0
