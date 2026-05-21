import os
import asyncio
import logging
from datetime import datetime
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from strategy import analyze_pair
from journal import save_trade, get_stats

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24")
CHAT_ID = os.getenv("6273206309")
TWELVEDATA_KEY = os.getenv("64d9b87e7c5a4d4f8e625ec95da13b0f")

PAIRS = ["XAU/USD", "NDX/USD"]

async def scan_and_notify():
    bot = Bot(token=TELEGRAM_TOKEN)
    logger.info(f"🔍 Scanning pairs: {PAIRS}")

    for pair in PAIRS:
        try:
            signal = await analyze_pair(pair, TWELVEDATA_KEY)
            if signal:
                msg = format_signal(signal)
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
                save_trade(signal)
                logger.info(f"✅ Signal sent for {pair}")
        except Exception as e:
            logger.error(f"❌ Error scanning {pair}: {e}")

def format_signal(signal: dict) -> str:
    direction_emoji = "🟢" if signal['direction'] == "BUY" else "🔴"
    pair_emoji = "🥇" if "XAU" in signal['pair'] else "💻"

    return (
        f"{pair_emoji} *{signal['pair']}* | {direction_emoji} *{signal['direction']}*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📍 *Entry:* `{signal['entry']}`\n"
        f"🛑 *SL:* `{signal['sl']}`\n"
        f"🎯 *TP:* `{signal['tp']}`\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 RR: `1:{signal['rr']}`\n"
        f"🕐 TF: `M15 + H1`\n"
        f"🧠 Setup: `IRL/ERL + MSS`\n"
        f"⏰ `{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC`"
    )

async def send_daily_stats():
    bot = Bot(token=TELEGRAM_TOKEN)
    stats = get_stats()
    if stats['total'] == 0:
        return

    msg = (
        f"📈 *Daily Journal Summary*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 Total Trades: `{stats['total']}`\n"
        f"✅ Win: `{stats['win']}`\n"
        f"❌ Loss: `{stats['loss']}`\n"
        f"⏳ Pending: `{stats['pending']}`\n"
        f"🏆 Win Rate: `{stats['win_rate']}%`\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📅 `{datetime.utcnow().strftime('%Y-%m-%d')} UTC`"
    )
    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

async def main():
    logger.info("🤖 Bot starting...")
    scheduler = AsyncIOScheduler()

    # Scan every 15 minutes during forex hours (Mon-Fri, 00:00-22:00 UTC)
    scheduler.add_job(scan_and_notify, 'cron', minute='0,15,30,45',
                      hour='0-21', day_of_week='mon-fri')

    # Daily stats at 22:00 UTC
    scheduler.add_job(send_daily_stats, 'cron', hour=22, minute=0, day_of_week='mon-fri')

    scheduler.start()
    logger.info("✅ Scheduler started. Bot is running...")

    # Run once on startup
    await scan_and_notify()

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
