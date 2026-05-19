import os
import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# ─────────────────────────────────────────────
# KONFIGURASI — isi sebelum menjalankan bot
# ─────────────────────────────────────────────
TELEGRAM_TOKEN = "8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24"   # dari @BotFather
TELEGRAM_CHAT_ID = "6273206309"             # dari @userinfobot
TWELVEDATA_API_KEY = "64d9b87e7c5a4d4f8e625ec95da13b0f"     # gratis di twelvedata.com

SYMBOL = "XAU/USD"
TIMEFRAME = "5min"       # gunakan "1min" atau "5min"
CHECK_INTERVAL = 60      # cek setiap 60 detik
LOOKBACK = 100           # jumlah candle yang diambil

# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# 1. AMBIL DATA CANDLE
# ══════════════════════════════════════════════
def get_candles(symbol=SYMBOL, interval=TIMEFRAME, outputsize=LOOKBACK):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVEDATA_API_KEY,
        "format": "JSON"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "values" not in data:
            log.error(f"API error: {data}")
            return None
        df = pd.DataFrame(data["values"])
        df = df.rename(columns={"datetime": "time", "open": "open", "high": "high",
                                 "low": "low", "close": "close", "volume": "volume"})
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)  # urutkan dari lama ke baru
        return df
    except Exception as e:
        log.error(f"Gagal ambil data: {e}")
        return None


# ══════════════════════════════════════════════
# 2. DETEKSI BREAK OF STRUCTURE (BOS) & CHoCH
# ══════════════════════════════════════════════
def detect_bos_choch(df):
    signals = []
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    # Cari swing high & swing low sederhana (3-candle pivot)
    for i in range(2, n - 1):
        # Swing High
        if highs[i - 1] > highs[i - 2] and highs[i - 1] > highs[i]:
            prev_swing_high = highs[i - 1]
            # BOS Bullish: harga close menembus swing high sebelumnya
            if closes[-1] > prev_swing_high:
                signals.append({
                    "type": "BOS",
                    "direction": "BULLISH 🟢",
                    "detail": f"Harga menembus Swing High {prev_swing_high:.2f}"
                })
                break

        # Swing Low
        if lows[i - 1] < lows[i - 2] and lows[i - 1] < lows[i]:
            prev_swing_low = lows[i - 1]
            # BOS Bearish: harga close menembus swing low sebelumnya
            if closes[-1] < prev_swing_low:
                signals.append({
                    "type": "BOS",
                    "direction": "BEARISH 🔴",
                    "detail": f"Harga menembus Swing Low {prev_swing_low:.2f}"
                })
                break

    # CHoCH: deteksi perubahan struktur (berlawanan dari tren sebelumnya)
    recent = df.tail(20)
    trend_up = recent["close"].iloc[-1] > recent["close"].iloc[0]
    last_high = recent["high"].max()
    last_low = recent["low"].min()

    if trend_up and closes[-1] < last_low:
        signals.append({
            "type": "CHoCH",
            "direction": "BEARISH 🔴",
            "detail": f"Perubahan struktur — harga tembus Low {last_low:.2f}"
        })
    elif not trend_up and closes[-1] > last_high:
        signals.append({
            "type": "CHoCH",
            "direction": "BULLISH 🟢",
            "detail": f"Perubahan struktur — harga tembus High {last_high:.2f}"
        })

    return signals


# ══════════════════════════════════════════════
# 3. DETEKSI ORDER BLOCK (OB)
# ══════════════════════════════════════════════
def detect_order_block(df):
    signals = []
    n = len(df)
    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values

    # Cari candle bearish besar yang diikuti candle bullish (Bullish OB)
    for i in range(n - 5, n - 1):
        if i < 1:
            continue
        body = abs(closes[i] - opens[i])
        avg_body = np.mean([abs(closes[j] - opens[j]) for j in range(max(0, i - 10), i)])

        # Bullish OB: candle bearish besar sebelum gerakan naik
        if opens[i] > closes[i] and body > avg_body * 1.2:
            ob_high = highs[i]
            ob_low = lows[i]
            current_price = closes[-1]
            # Harga kembali ke zona OB
            if ob_low <= current_price <= ob_high:
                signals.append({
                    "type": "Order Block",
                    "direction": "BULLISH 🟢",
                    "detail": f"Harga masuk zona Bullish OB [{ob_low:.2f} - {ob_high:.2f}]"
                })

        # Bearish OB: candle bullish besar sebelum gerakan turun
        if closes[i] > opens[i] and body > avg_body * 1.2:
            ob_high = highs[i]
            ob_low = lows[i]
            current_price = closes[-1]
            if ob_low <= current_price <= ob_high:
                signals.append({
                    "type": "Order Block",
                    "direction": "BEARISH 🔴",
                    "detail": f"Harga masuk zona Bearish OB [{ob_low:.2f} - {ob_high:.2f}]"
                })

    return signals


# ══════════════════════════════════════════════
# 4. DETEKSI FAIR VALUE GAP (FVG)
# ══════════════════════════════════════════════
def detect_fvg(df):
    signals = []
    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    for i in range(1, n - 1):
        # Bullish FVG: low[i+1] > high[i-1]
        if lows[i + 1] > highs[i - 1]:
            fvg_low = highs[i - 1]
            fvg_high = lows[i + 1]
            current_price = closes[-1]
            if fvg_low <= current_price <= fvg_high:
                signals.append({
                    "type": "Fair Value Gap",
                    "direction": "BULLISH 🟢",
                    "detail": f"Harga mengisi Bullish FVG [{fvg_low:.2f} - {fvg_high:.2f}]"
                })

        # Bearish FVG: high[i+1] < low[i-1]
        if highs[i + 1] < lows[i - 1]:
            fvg_high = lows[i - 1]
            fvg_low = highs[i + 1]
            current_price = closes[-1]
            if fvg_low <= current_price <= fvg_high:
                signals.append({
                    "type": "Fair Value Gap",
                    "direction": "BEARISH 🔴",
                    "detail": f"Harga mengisi Bearish FVG [{fvg_low:.2f} - {fvg_high:.2f}]"
                })

    return signals


# ══════════════════════════════════════════════
# 5. DETEKSI LIQUIDITY SWEEP
# ══════════════════════════════════════════════
def detect_liquidity_sweep(df):
    signals = []
    recent = df.tail(30)
    highs = recent["high"].values
    lows = recent["low"].values
    closes = recent["close"].values
    n = len(highs)

    # Ambil equal highs / equal lows (likuiditas)
    prev_high = max(highs[:-3])
    prev_low = min(lows[:-3])
    current_high = highs[-1]
    current_low = lows[-1]
    current_close = closes[-1]

    # Bullish sweep: harga spike ke bawah prev_low lalu kembali naik
    if current_low < prev_low and current_close > prev_low:
        signals.append({
            "type": "Liquidity Sweep",
            "direction": "BULLISH 🟢",
            "detail": f"Sweep BSL — spike ke bawah {prev_low:.2f} lalu reversal naik"
        })

    # Bearish sweep: harga spike ke atas prev_high lalu kembali turun
    if current_high > prev_high and current_close < prev_high:
        signals.append({
            "type": "Liquidity Sweep",
            "direction": "BEARISH 🔴",
            "detail": f"Sweep SSL — spike ke atas {prev_high:.2f} lalu reversal turun"
        })

    return signals


# ══════════════════════════════════════════════
# 6. KIRIM NOTIFIKASI TELEGRAM
# ══════════════════════════════════════════════
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("✅ Notifikasi terkirim")
        else:
            log.error(f"Gagal kirim: {r.text}")
    except Exception as e:
        log.error(f"Error Telegram: {e}")


SIGNAL_GUIDE = {
    ("Order Block", "BULLISH 🟢"): {
        "aksi": "Pertimbangkan BUY",
        "sl": "Pasang SL di bawah zona Order Block",
        "tp": "Target TP di resistance / High terdekat",
        "tips": "Tunggu candle bullish konfirmasi (engulfing/pin bar) sebelum entry"
    },
    ("Order Block", "BEARISH 🔴"): {
        "aksi": "Pertimbangkan SELL",
        "sl": "Pasang SL di atas zona Order Block",
        "tp": "Target TP di support / Low terdekat",
        "tips": "Tunggu candle bearish konfirmasi (engulfing/pin bar) sebelum entry"
    },
    ("Fair Value Gap", "BULLISH 🟢"): {
        "aksi": "Pertimbangkan BUY",
        "sl": "Pasang SL di bawah FVG (beberapa pips di bawah gap)",
        "tp": "Target TP di High sebelum gap terbentuk",
        "tips": "Entry saat harga masuk gap dan mulai rejection ke atas"
    },
    ("Fair Value Gap", "BEARISH 🔴"): {
        "aksi": "Pertimbangkan SELL",
        "sl": "Pasang SL di atas FVG (beberapa pips di atas gap)",
        "tp": "Target TP di Low sebelum gap terbentuk",
        "tips": "Entry saat harga masuk gap dan mulai rejection ke bawah"
    },
    ("BOS", "BULLISH 🟢"): {
        "aksi": "Pertimbangkan BUY",
        "sl": "Pasang SL di bawah Low terakhir sebelum BOS",
        "tp": "Target TP di resistance / High berikutnya",
        "tips": "Tunggu retest struktur yang baru ditembus sebelum entry"
    },
    ("BOS", "BEARISH 🔴"): {
        "aksi": "Pertimbangkan SELL",
        "sl": "Pasang SL di atas High terakhir sebelum BOS",
        "tp": "Target TP di support / Low berikutnya",
        "tips": "Tunggu retest struktur yang baru ditembus sebelum entry"
    },
    ("CHoCH", "BULLISH 🟢"): {
        "aksi": "Pertimbangkan BUY — tren bisa berbalik naik",
        "sl": "Pasang SL di bawah Low yang baru terbentuk",
        "tp": "Target TP di High sebelumnya",
        "tips": "CHoCH = sinyal awal pembalikan, konfirmasi dulu di chart sebelum entry"
    },
    ("CHoCH", "BEARISH 🔴"): {
        "aksi": "Pertimbangkan SELL — tren bisa berbalik turun",
        "sl": "Pasang SL di atas High yang baru terbentuk",
        "tp": "Target TP di Low sebelumnya",
        "tips": "CHoCH = sinyal awal pembalikan, konfirmasi dulu di chart sebelum entry"
    },
    ("Liquidity Sweep", "BULLISH 🟢"): {
        "aksi": "Pertimbangkan BUY — harga sudah ambil likuiditas bawah",
        "sl": "Pasang SL di bawah spike / Low yang baru terbentuk",
        "tp": "Target TP di High sebelum sweep terjadi",
        "tips": "Pastikan harga sudah reversal dan tutup di atas Low lama sebelum entry"
    },
    ("Liquidity Sweep", "BEARISH 🔴"): {
        "aksi": "Pertimbangkan SELL — harga sudah ambil likuiditas atas",
        "sl": "Pasang SL di atas spike / High yang baru terbentuk",
        "tp": "Target TP di Low sebelum sweep terjadi",
        "tips": "Pastikan harga sudah reversal dan tutup di bawah High lama sebelum entry"
    },
}

def format_signal_message(signals, df):
    current_price = df["close"].iloc[-1]
    high_5 = df["high"].tail(20).max()
    low_5 = df["low"].tail(20).min()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 *ICT SIGNAL — {SYMBOL}*",
        f"🕐 {now} | TF: {TIMEFRAME}",
        f"💰 Harga saat ini: *{current_price:.2f}*",
        f"📈 High 20 candle: {high_5:.2f} | 📉 Low 20 candle: {low_5:.2f}",
        "━━━━━━━━━━━━━━━━━━━━━"
    ]

    for s in signals:
        guide = SIGNAL_GUIDE.get((s["type"], s["direction"]), None)
        lines.append(f"\n🔔 *{s['type']}* — {s['direction']}")
        lines.append(f"   ↳ {s['detail']}")
        if guide:
            lines.append(f"\n   📌 *Rekomendasi:*")
            lines.append(f"   • Aksi   : {guide['aksi']}")
            lines.append(f"   • SL     : {guide['sl']}")
            lines.append(f"   • TP     : {guide['tp']}")
            lines.append(f"   • 💡 Tips: _{guide['tips']}_")
        lines.append("─────────────────────")

    lines.append("\n⚠️ _Konfirmasi di chart sebelum entry. Selalu pakai SL!_")
    lines.append("_Bot ini hanya sinyal, bukan saran finansial._")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# 7. MAIN LOOP
# ══════════════════════════════════════════════
sent_signals = set()  # hindari notifikasi duplikat

def run_bot():
    log.info(f"🤖 Bot ICT {SYMBOL} mulai berjalan...")
    send_telegram(f"🤖 *Bot ICT {SYMBOL} aktif!*\nMemantau sinyal di timeframe {TIMEFRAME}...")

    while True:
        try:
            df = get_candles()
            if df is None or len(df) < 10:
                log.warning("Data tidak tersedia, coba lagi...")
                time.sleep(CHECK_INTERVAL)
                continue

            all_signals = []
            all_signals += detect_bos_choch(df)
            all_signals += detect_order_block(df)
            all_signals += detect_fvg(df)
            all_signals += detect_liquidity_sweep(df)

            if all_signals:
                # Buat key unik untuk hindari duplikat
                signal_key = str([(s["type"], s["direction"]) for s in all_signals])
                if signal_key not in sent_signals:
                    message = format_signal_message(all_signals, df)
                    send_telegram(message)
                    sent_signals.add(signal_key)
                    # Bersihkan cache lama agar tidak menumpuk
                    if len(sent_signals) > 50:
                        sent_signals.clear()
            else:
                log.info("Tidak ada sinyal saat ini.")

        except Exception as e:
            log.error(f"Error di main loop: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()
