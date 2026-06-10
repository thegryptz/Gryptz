from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .ai import score_token
from .config import MIN_GRYPTZ_SCORE, TELEGRAM_BOT_TOKEN
from .formatter import format_score_card
from .scanner import TokenData, get_new_pairs, get_token, get_top_gainers
from .scanner_loop import get_latest, get_scan_meta
from .wallet import address_short, generate_wallet

log = logging.getLogger(__name__)

WAIT_CA = 1
CA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

DIV = "━━━━━━━━━━━━━━━━━━━━━"


# ── helpers ──────────────────────────────────────────────────────────────────

def _fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:.2f}"


def _fmt_pct(v: float) -> str:
    arrow = "▲" if v >= 0 else "▼"
    return f"{arrow} {abs(v):.2f}%"


def _wallet_info(ctx: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return ctx.user_data.get("wallet")


def _main_kb(has_wallet: bool) -> InlineKeyboardMarkup:
    wallet_label = "💼 Wallet" if not has_wallet else "💼 My Wallet"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Top Signals", callback_data="top"),
            InlineKeyboardButton("📈 Top Gainers", callback_data="gainers"),
        ],
        [
            InlineKeyboardButton("🆕 New Pairs", callback_data="new_pairs"),
            InlineKeyboardButton("📊 All Scanned", callback_data="all"),
        ],
        [
            InlineKeyboardButton("🔍 Score CA", callback_data="score_ca"),
            InlineKeyboardButton(wallet_label, callback_data="wallet"),
        ],
        [
            InlineKeyboardButton("ℹ️ How It Works", callback_data="about"),
        ],
    ])


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="home")]])


def _build_home_text(ctx: ContextTypes.DEFAULT_TYPE) -> str:
    wallet = _wallet_info(ctx)
    meta = get_scan_meta()

    wallet_line = f"`{wallet['address'][:6]}...{wallet['address'][-4:]}`" if wallet else "Not connected"
    last_scan = "Never"
    tokens_scored = 0
    signals_found = 0

    if meta:
        elapsed = int(time.time() - meta["ts"])
        if elapsed < 60:
            last_scan = f"{elapsed}s ago"
        else:
            last_scan = f"{elapsed // 60}m ago"
        tokens_scored = meta["total"]
        signals_found = meta["signals"]

    lines = [
        "🦎 *Gryptz AI Scanner*",
        "",
        DIV,
        f"👛 Wallet: {wallet_line}",
        DIV,
        "",
        "AI scans trending Solana tokens every *2 minutes*.",
        "Each token gets a *Gryptz Score 0–100* powered by DeepInfra.",
        "Score ≥ 60 = signal worth watching.",
        "Score ≥ 80 = strong buy signal.",
        "",
        DIV,
        f"🕐 Last scan: *{last_scan}*",
        f"📦 Tokens scored: *{tokens_scored}*",
        f"⚡ Signals found: *{signals_found}*",
        DIV,
    ]
    return "\n".join(lines)


# ── commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = _build_home_text(ctx)
    kb = _main_kb(bool(_wallet_info(ctx)))
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def cmd_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: `/score <CA>`", parse_mode=ParseMode.MARKDOWN)
        return
    ca = args[0].strip()
    if not CA_RE.match(ca):
        await update.message.reply_text("❌ Invalid Solana address.")
        return
    msg = await update.message.reply_text("🔍 Fetching token data...")
    token = await get_token(ca)
    if not token:
        await msg.edit_text("❌ Token not found on DexScreener.")
        return
    await msg.edit_text("🤖 Scoring with DeepInfra AI...")
    score = await score_token(token)
    text = format_score_card(token, score)
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    results = get_latest()
    top = [(t, s) for t, s in results if s.score >= MIN_GRYPTZ_SCORE]
    if not top:
        await update.message.reply_text("📭 No signals right now. Next scan in ~2 min.")
        return
    await update.message.reply_text(f"🔥 *Top {min(len(top), 5)} Signals*", parse_mode=ParseMode.MARKDOWN)
    for token, score in top[:5]:
        text = format_score_card(token, score)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


# ── callbacks: home ───────────────────────────────────────────────────────────

async def cb_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await cmd_start(update, ctx)


# ── callbacks: top signals ────────────────────────────────────────────────────

async def cb_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Loading signals...")
    results = get_latest()
    top = [(t, s) for t, s in results if s.score >= MIN_GRYPTZ_SCORE]
    if not top:
        await query.edit_message_text(
            "📭 *No signals right now.*\n\nFilters didn't pass anything this scan. Try again in ~2 min.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_back_kb(),
        )
        return
    await query.edit_message_text(
        f"🔥 *Top Signals* — {len(top)} found\n\nSending...",
        parse_mode=ParseMode.MARKDOWN,
    )
    for token, score in top[:5]:
        text = format_score_card(token, score)
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    await ctx.bot.send_message(
        chat_id=query.message.chat_id,
        text="« Back to menu",
        reply_markup=_main_kb(bool(_wallet_info(ctx))),
    )


# ── callbacks: all scanned ────────────────────────────────────────────────────

async def cb_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    results = get_latest()
    if not results:
        await query.edit_message_text(
            "📭 No scan data yet. First scan runs at startup — check back in a moment.",
            reply_markup=_back_kb(),
        )
        return

    lines = [f"📊 *All Scanned Tokens* ({len(results)} total)\n", DIV]
    for token, score in results[:20]:
        bar = "█" * (score.score // 10) + "░" * (10 - score.score // 10)
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(score.rug_risk, "⚪")
        signal = "⚡" if score.score >= 60 else "  "
        lines.append(
            f"{signal} `{score.score:>3}` [{bar}] *${token.symbol}* {risk_icon}"
        )

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_back_kb(),
    )


# ── callbacks: top gainers ────────────────────────────────────────────────────

async def cb_gainers(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Fetching gainers...")
    await query.edit_message_text("📈 Fetching top gainers on Solana...")
    tokens = await get_top_gainers()
    if not tokens:
        await query.edit_message_text(
            "❌ Could not fetch gainers right now.",
            reply_markup=_back_kb(),
        )
        return

    lines = [f"📈 *Top Gainers — Solana DEX*\n", DIV]
    for t in tokens[:12]:
        chg = t.price_change_1h
        arrow = "▲" if chg >= 0 else "▼"
        color = "🟢" if chg >= 0 else "🔴"
        lines.append(
            f"{color} *${t.symbol}*  {arrow} `{abs(chg):.1f}%` 1h  |  Liq {_fmt_usd(t.liquidity_usd)}"
        )
        lines.append(f"  `{t.ca[:8]}...{t.ca[-4:]}`  [{t.dex.upper()}]({t.pair_url})")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=_back_kb(),
    )


# ── callbacks: new pairs ──────────────────────────────────────────────────────

async def cb_new_pairs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Fetching new pairs...")
    await query.edit_message_text("🆕 Fetching newest Solana pairs...")
    tokens = await get_new_pairs()
    if not tokens:
        await query.edit_message_text(
            "❌ Could not fetch new pairs right now.",
            reply_markup=_back_kb(),
        )
        return

    lines = [f"🆕 *New Pairs — Solana DEX*\n", DIV]
    for t in tokens[:12]:
        chg = t.price_change_1h
        chg_str = f"{'▲' if chg >= 0 else '▼'}{abs(chg):.1f}%"
        lines.append(
            f"• *${t.symbol}*  `{chg_str}` 1h  |  Liq {_fmt_usd(t.liquidity_usd)}  |  Vol {_fmt_usd(t.volume_1h)}"
        )
        lines.append(f"  `{t.ca[:8]}...{t.ca[-4:]}`  [{t.dex.upper()}]({t.pair_url})")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=_back_kb(),
    )


# ── callbacks: score CA ───────────────────────────────────────────────────────

async def cb_score_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 *Score Any Token*\n\n"
        "Send me a Solana contract address (CA) and I'll run a full AI analysis on it.\n\n"
        "Example:\n`So11111111111111111111111111111111111111112`\n\n"
        "Or /cancel to go back.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return WAIT_CA


async def receive_ca(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ca = update.message.text.strip()
    if not CA_RE.match(ca):
        await update.message.reply_text(
            "❌ That doesn't look like a valid Solana address.\nSend a valid CA or /cancel.",
        )
        return WAIT_CA

    msg = await update.message.reply_text("🔍 Fetching token data from DexScreener...")
    token = await get_token(ca)
    if not token:
        await msg.edit_text(
            "❌ Token not found on DexScreener.\n\nMight be too new or not listed yet.",
            reply_markup=_back_kb(),
        )
        return ConversationHandler.END

    await msg.edit_text(
        f"🤖 Scoring *${token.symbol}* with DeepInfra AI...",
        parse_mode=ParseMode.MARKDOWN,
    )
    score = await score_token(token)
    text = format_score_card(token, score)
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    await update.message.reply_text("Back to menu:", reply_markup=_main_kb(bool(_wallet_info(ctx))))
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.", reply_markup=_main_kb(bool(_wallet_info(ctx))))
    return ConversationHandler.END


# ── callbacks: wallet ─────────────────────────────────────────────────────────

async def cb_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    wallet = _wallet_info(ctx)

    if not wallet:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Generate New Wallet", callback_data="wallet_gen")],
            [InlineKeyboardButton("« Back", callback_data="home")],
        ])
        await query.edit_message_text(
            "💼 *Wallet*\n\n"
            + DIV + "\n"
            "No wallet connected.\n\n"
            "Generate a new Solana wallet directly in this bot.\n"
            "Your keys are stored in-session — *always save your private key.*\n"
            + DIV,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb,
        )
    else:
        addr = wallet["address"]
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👁 Show Private Key", callback_data="wallet_pk"),
                InlineKeyboardButton("🔄 New Wallet", callback_data="wallet_gen"),
            ],
            [InlineKeyboardButton("« Back", callback_data="home")],
        ])
        await query.edit_message_text(
            f"💼 *My Wallet*\n\n"
            + DIV + "\n"
            f"🔑 Address:\n`{addr}`\n\n"
            f"📋 Short: `{address_short(addr)}`\n"
            + DIV + "\n\n"
            "⚠️ Save your private key in a safe place.\n"
            "_Keys are lost when bot restarts._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb,
        )


async def cb_wallet_gen(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Generating wallet...")
    w = generate_wallet()
    ctx.user_data["wallet"] = w

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👁 Show Private Key", callback_data="wallet_pk"),
            InlineKeyboardButton("🔄 New Wallet", callback_data="wallet_gen"),
        ],
        [InlineKeyboardButton("« Back to Menu", callback_data="home")],
    ])
    await query.edit_message_text(
        f"✅ *New Wallet Generated*\n\n"
        + DIV + "\n"
        f"🔑 *Address:*\n`{w['address']}`\n\n"
        f"📊 Network: *Solana Mainnet*\n"
        + DIV + "\n\n"
        "⚠️ *IMPORTANT:* Tap 'Show Private Key' and save it.\n"
        "_Never share your private key with anyone._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def cb_wallet_pk(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    wallet = _wallet_info(ctx)

    if not wallet:
        await query.answer("No wallet found. Generate one first.", show_alert=True)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Delete This Message", callback_data="wallet_pk_del")],
        [InlineKeyboardButton("« Back to Wallet", callback_data="wallet")],
    ])
    msg = await ctx.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "🔐 *Private Key*\n\n"
            "⚠️ *Do not share this with anyone.*\n"
            "⚠️ *Delete this message after saving.*\n\n"
            + DIV + "\n"
            f"`{wallet['private_key']}`\n"
            + DIV + "\n\n"
            "_Import into Phantom: Settings → Import Wallet → Private Key_"
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )
    ctx.user_data["pk_msg_id"] = msg.message_id


async def cb_wallet_pk_del(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Deleted.")
    try:
        await query.message.delete()
    except Exception:
        pass


# ── callbacks: about ──────────────────────────────────────────────────────────

async def cb_about(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ *How Gryptz Works*\n\n"
        + DIV + "\n"
        "*Data Sources*\n"
        "• DexScreener — real-time Solana DEX data\n"
        "• Filters: min $5K liq, $10K 1h vol, 55%+ buys\n\n"
        "*AI Scoring*\n"
        "• Model: Llama 3.1 70B via DeepInfra\n"
        "• Reads: liquidity, volume, buy ratio, price action\n"
        "• Output: score 0–100, rug risk, verdict\n\n"
        "*Score Guide*\n"
        "• 80–100 → Strong signal\n"
        "• 60–79 → Worth watching\n"
        "• 40–59 → Neutral\n"
        "• 0–39 → Avoid\n\n"
        "*Scan Cycle*\n"
        "• Runs every 2 minutes, 24/7\n"
        "• Auto-alerts if TELEGRAM\\_CHAT\\_ID is set\n"
        + DIV + "\n\n"
        "_Not financial advice. DYOR._"
    )
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=_back_kb())




async def cmd_gainers(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("📈 Fetching top gainers...")
    tokens = await get_top_gainers()
    if not tokens:
        await msg.edit_text("❌ Could not fetch gainers right now.")
        return
    lines = [f"📈 *Top Gainers — Solana DEX*\n", DIV]
    for t in tokens[:12]:
        chg = t.price_change_1h
        arrow = "▲" if chg >= 0 else "▼"
        color = "🟢" if chg >= 0 else "🔴"
        lines.append(f"{color} *${t.symbol}*  {arrow} `{abs(chg):.1f}%` 1h  |  Liq {_fmt_usd(t.liquidity_usd)}")
        lines.append(f"  `{t.ca[:8]}...{t.ca[-4:]}`  [{t.dex.upper()}]({t.pair_url})")
    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def cmd_newpairs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("🆕 Fetching newest pairs...")
    tokens = await get_new_pairs()
    if not tokens:
        await msg.edit_text("❌ Could not fetch new pairs right now.")
        return
    lines = [f"🆕 *New Pairs — Solana DEX*\n", DIV]
    for t in tokens[:12]:
        chg = t.price_change_1h
        chg_str = f"{'▲' if chg >= 0 else '▼'}{abs(chg):.1f}%"
        lines.append(f"• *${t.symbol}*  `{chg_str}` 1h  |  Liq {_fmt_usd(t.liquidity_usd)}")
        lines.append(f"  `{t.ca[:8]}...{t.ca[-4:]}`  [{t.dex.upper()}]({t.pair_url})")
    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def cmd_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    wallet = _wallet_info(ctx)
    if not wallet:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Generate New Wallet", callback_data="wallet_gen")],
            [InlineKeyboardButton("« Back", callback_data="home")],
        ])
        await update.message.reply_text(
            "💼 *Wallet*\n\n" + DIV + "\nNo wallet connected.\n\nGenerate a new Solana wallet below.\n" + DIV,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb,
        )
    else:
        addr = wallet["address"]
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👁 Show Private Key", callback_data="wallet_pk"),
                InlineKeyboardButton("🔄 New Wallet", callback_data="wallet_gen"),
            ],
            [InlineKeyboardButton("« Back", callback_data="home")],
        ])
        await update.message.reply_text(
            f"💼 *My Wallet*\n\n" + DIV + f"\n🔑 Address:\n`{addr}`\n" + DIV,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb,
        )


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_score_start, pattern="^score_ca$")],
        states={WAIT_CA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ca)]},
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", cmd_start)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("score", cmd_score))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("gainers", cmd_gainers))
    app.add_handler(CommandHandler("newpairs", cmd_newpairs))
    app.add_handler(CommandHandler("wallet", cmd_wallet))
    app.add_handler(conv)

    app.add_handler(CallbackQueryHandler(cb_home, pattern="^home$"))
    app.add_handler(CallbackQueryHandler(cb_top, pattern="^top$"))
    app.add_handler(CallbackQueryHandler(cb_all, pattern="^all$"))
    app.add_handler(CallbackQueryHandler(cb_gainers, pattern="^gainers$"))
    app.add_handler(CallbackQueryHandler(cb_new_pairs, pattern="^new_pairs$"))
    app.add_handler(CallbackQueryHandler(cb_wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(cb_wallet_gen, pattern="^wallet_gen$"))
    app.add_handler(CallbackQueryHandler(cb_wallet_pk, pattern="^wallet_pk$"))
    app.add_handler(CallbackQueryHandler(cb_wallet_pk_del, pattern="^wallet_pk_del$"))
    app.add_handler(CallbackQueryHandler(cb_about, pattern="^about$"))

    return app


_BOT_COMMANDS = [
    ("start",    "Your Gryptz AI Scanner dashboard"),
    ("score",    "Score any Solana token — /score <CA>"),
    ("top",      "Top signals from last scan"),
    ("gainers",  "Top gainers on Solana DEX right now"),
    ("newpairs", "Newest pairs listed on Solana DEX"),
    ("wallet",   "Manage your Solana wallet"),
]


async def run_bot() -> None:
    app = build_app()
    await app.initialize()
    await app.bot.set_my_commands(_BOT_COMMANDS)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    log.info("Gryptz bot running")
    await asyncio.Event().wait()
