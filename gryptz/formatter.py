from __future__ import annotations

from .ai import GryptzScore
from .scanner import TokenData


def _score_bar(score: int) -> str:
    filled = score // 10
    return "█" * filled + "░" * (10 - filled)


def _risk_emoji(risk: str) -> str:
    return {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")


def _momentum_emoji(momentum: str) -> str:
    return {"weak": "📉", "moderate": "➡️", "strong": "🚀"}.get(momentum, "❓")


def format_alert(token: TokenData, score: GryptzScore) -> str:
    bar = _score_bar(score.score)
    risk_e = _risk_emoji(score.rug_risk)
    mom_e = _momentum_emoji(score.momentum)

    signals_text = ""
    if score.signals:
        signals_text = "\n" + "\n".join(f"  • {s}" for s in score.signals)

    mcap = f"${token.market_cap / 1_000_000:.2f}M" if token.market_cap >= 1_000_000 else f"${token.market_cap:,.0f}"
    liq = f"${token.liquidity_usd / 1_000:.1f}K"
    vol1h = f"${token.volume_1h / 1_000:.1f}K"

    lines = [
        f"⚡ *GRYPTZ SIGNAL*",
        f"",
        f"*${token.symbol}* — {token.name}",
        f"`{token.ca}`",
        f"",
        f"🎯 *Score: {score.score}/100*",
        f"`[{bar}]`",
        f"",
        f"{risk_e} Rug Risk: *{score.rug_risk.upper()}*",
        f"{mom_e} Momentum: *{score.momentum.upper()}*",
        f"",
        f"💬 _{score.verdict}_",
        f"",
        f"📊 *Market Data*",
        f"  💰 Price: `${token.price_usd:.8f}`",
        f"  💧 Liq: `{liq}`  |  MCap: `{mcap}`",
        f"  📈 Vol 1h: `{vol1h}`",
        f"  🔄 Buy Ratio: `{token.buy_ratio_1h:.1%}`",
        f"  ⏱ 1h: `{token.price_change_1h:+.1f}%`  |  24h: `{token.price_change_24h:+.1f}%`",
        f"",
        f"🔍 Signals:{signals_text if signals_text else ' —'}",
        f"",
        f"🦎 DEX: [{token.dex.upper()}]({token.pair_url})",
    ]
    return "\n".join(lines)


def format_score_card(token: TokenData, score: GryptzScore) -> str:
    return format_alert(token, score)


def format_no_signals() -> str:
    return "🔍 *No signals found* — market is quiet or nothing passed filters right now."
