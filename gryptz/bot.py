from __future__ import annotations

import asyncio
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
from .formatter import format_no_signals, format_score_card
from .scanner import get_token
from .scanner_loop import get_latest

log = logging.getLogger(__name__)

WAIT_CA = 1
CA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Top Signals", callback_data="top"),
            InlineKeyboardButton("🔍 Score CA", callback_data="score_ca"),
        ],
        [
            InlineKeyboardButton("📊 All Scanned", callback_data="all"),
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
        ],
    ])


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🦎 *Gryptz AI Scanner*\n\n"
        "AI-powered Solana token scanner. We score every trending token "
        "on DeepInfra so you ape with data, not hope.\n\n"
        "Choose an action:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_main_menu())


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "*Commands*\n"
        "/start — main menu\n"
        "/score `<CA>` — score any Solana token by contract address\n"
        "/top — top signals from last scan\n"
        "/help — this message\n\n"
        "*How scoring works*\n"
        "Each token gets a Gryptz Score 0–100 based on liquidity, volume, "
        "buy pressure, and AI analysis. Score ≥60 = worth watching."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: `/score <CA>`", parse_mode="Markdown")
        return
    ca = args[0].strip()
    if not CA_RE.match(ca):
        await update.message.reply_text("Invalid Solana address.")
        return
    msg = await update.message.reply_text("🔍 Fetching token data...")
    token = await get_token(ca)
    if not token:
        await msg.edit_text("Could not find token on DexScreener.")
        return
    await msg.edit_text("🤖 Scoring with AI...")
    score = await score_token(token)
    text = format_score_card(token, score)
    await msg.edit_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    results = get_latest()
    top = [(t, s) for t, s in results if s.score >= MIN_GRYPTZ_SCORE]
    if not top:
        await update.message.reply_text(format_no_signals(), parse_mode="Markdown")
        return
    for token, score in top[:5]:
        text = format_score_card(token, score)
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def cb_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    results = get_latest()
    top = [(t, s) for t, s in results if s.score >= MIN_GRYPTZ_SCORE]
    if not top:
        await query.edit_message_text(format_no_signals(), parse_mode="Markdown", reply_markup=_main_menu())
        return
    await query.edit_message_text(f"🔥 *Top {min(len(top), 5)} Signals*\n\nSending...", parse_mode="Markdown")
    for token, score in top[:5]:
        text = format_score_card(token, score)
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )


async def cb_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    results = get_latest()
    if not results:
        await query.edit_message_text("No scan data yet. Wait for the next scan cycle.", reply_markup=_main_menu())
        return
    lines = ["📊 *All Scanned Tokens*\n"]
    for token, score in results[:15]:
        bar = "█" * (score.score // 10) + "░" * (10 - score.score // 10)
        lines.append(f"`{score.score:>3}` [{bar}] *${token.symbol}* — {score.rug_risk} risk")
    await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=_main_menu())


async def cb_about(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text = (
        "🦎 *Gryptz AI Scanner*\n\n"
        "Scans trending Solana tokens every 2 minutes.\n"
        "AI (DeepInfra) scores each token 0–100.\n\n"
        "Score ≥ 60 = signal alert.\n"
        "Score ≥ 80 = strong buy signal.\n\n"
        "_Not financial advice. DYOR._"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_main_menu())


async def cb_score_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 Send me a Solana contract address (CA):")
    return WAIT_CA


async def receive_ca(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ca = update.message.text.strip()
    if not CA_RE.match(ca):
        await update.message.reply_text("Invalid CA. Send a valid Solana address or /start to go back.")
        return WAIT_CA
    msg = await update.message.reply_text("🔍 Fetching token data...")
    token = await get_token(ca)
    if not token:
        await msg.edit_text("Could not find token on DexScreener.")
        return ConversationHandler.END
    await msg.edit_text("🤖 Scoring with AI...")
    score = await score_token(token)
    text = format_score_card(token, score)
    await msg.edit_text(text, parse_mode="Markdown", disable_web_page_preview=True)
    await update.message.reply_text("Back to menu:", reply_markup=_main_menu())
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.", reply_markup=_main_menu())
    return ConversationHandler.END


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_score_start, pattern="^score_ca$")],
        states={WAIT_CA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ca)]},
        fallbacks=[CommandHandler("start", cmd_start), CommandHandler("cancel", cancel)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("score", cmd_score))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(cb_top, pattern="^top$"))
    app.add_handler(CallbackQueryHandler(cb_all, pattern="^all$"))
    app.add_handler(CallbackQueryHandler(cb_about, pattern="^about$"))

    return app


async def run_bot() -> None:
    app = build_app()
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    log.info("Gryptz bot running")
    await asyncio.Event().wait()
