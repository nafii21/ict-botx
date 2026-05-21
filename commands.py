"""
Handler command Telegram untuk update hasil trade & lihat stats.
Jalanin ini sebagai polling bot (bisa digabung di bot.py atau run terpisah).

Commands:
  /stats          - lihat win rate keseluruhan
  /stats XAUUSD   - stats untuk pair tertentu
  /win <id>       - tandai trade WIN
  /loss <id>      - tandai trade LOSS
  /be <id>        - tandai trade Breakeven
  /recent         - 5 trade terbaru
  /journal        - link download journal CSV
"""

import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from journal import get_stats, update_trade_result, get_recent_trades

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))

def is_authorized(update: Update) -> bool:
    return update.effective_chat.id == CHAT_ID

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    pair = context.args[0].upper() if context.args else None
    stats = get_stats(pair=pair)

    header = f"📊 *Stats — {pair}*" if pair else "📊 *Stats — All Pairs*"
    msg = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📈 Total Signals: `{stats['total']}`\n"
        f"✅ Win: `{stats['win']}`\n"
        f"❌ Loss: `{stats['loss']}`\n"
        f"⚖️ BE: `{stats['be']}`\n"
        f"⏳ Pending: `{stats['pending']}`\n"
        f"🏆 Win Rate: `{stats['win_rate']}%`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /win <trade_id>")
        return
    trade_id = int(context.args[0])
    ok = update_trade_result(trade_id, "WIN")
    await update.message.reply_text(f"✅ Trade #{trade_id} ditandai *WIN*" if ok else f"❌ Trade #{trade_id} tidak ditemukan", parse_mode="Markdown")

async def cmd_loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /loss <trade_id>")
        return
    trade_id = int(context.args[0])
    ok = update_trade_result(trade_id, "LOSS")
    await update.message.reply_text(f"❌ Trade #{trade_id} ditandai *LOSS*" if ok else f"❌ Trade #{trade_id} tidak ditemukan", parse_mode="Markdown")

async def cmd_be(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /be <trade_id>")
        return
    trade_id = int(context.args[0])
    ok = update_trade_result(trade_id, "BE")
    await update.message.reply_text(f"⚖️ Trade #{trade_id} ditandai *BE*" if ok else f"❌ Trade #{trade_id} tidak ditemukan", parse_mode="Markdown")

async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    trades = get_recent_trades(5)
    if not trades:
        await update.message.reply_text("📭 Belum ada trade.")
        return

    lines = ["📋 *5 Trade Terbaru*\n━━━━━━━━━━━━━━━━"]
    for t in reversed(trades):
        emoji = {"WIN": "✅", "LOSS": "❌", "BE": "⚖️", "PENDING": "⏳"}.get(t["result"], "❓")
        lines.append(
            f"{emoji} `#{t['id']}` *{t['pair']}* {t['direction']}\n"
            f"   Entry: `{t['entry']}` | TP: `{t['tp']}` | SL: `{t['sl']}`\n"
            f"   RR: `1:{t['rr']}` | Status: `{t['result']}`"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

def run_command_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("win", cmd_win))
    app.add_handler(CommandHandler("loss", cmd_loss))
    app.add_handler(CommandHandler("be", cmd_be))
    app.add_handler(CommandHandler("recent", cmd_recent))
    logger.info("🎮 Command bot polling started...")
    app.run_polling()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_command_bot()
