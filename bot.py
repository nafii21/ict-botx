import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# ─────────────────────────────────────────────
# KONFIGURASI — isi sebelum menjalankan bot
# ─────────────────────────────────────────────
TELEGRAM_TOKEN     = "8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24"
TELEGRAM_CHAT_ID   = "6273206309"
TWELVEDATA_API_KEY = "64d9b87e7c5a4d4f8e625ec95da13b0f"

SYMBOL         = "XAU/USD"
TIMEFRAME      = "5min"
CHECK_INTERVAL = 60    # cek setiap 60 detik
LOOKBACK       = 100   # jumlah candle yang diambil

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# 1. AMBIL DATA CANDLE
# ══════════════════════════════════════════════
def get_candles():
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol"    : SYMBOL,
        "interval"  : TIMEFRAME,
        "outputsize": LOOKBACK,
        "apikey"    : TWELVEDATA_API_KEY,
        "format"    : "JSON"
    }
    try:
        r    = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "values" not in data:
            log.error(f"API error: {data}")
            return None
        df = pd.DataFrame(data["values"])
        df[["open","high","low","close"]] = df[["open","high","low","close"]].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)  # lama → baru
        return df
    except Exception as e:
        log.error(f"Gagal ambil data: {e}")
        return None


# ══════════════════════════════════════════════
# 2. CARI PREVIOUS HIGH & LOW (level likuiditas)
#    Diambil dari swing high/low dalam 20-50 candle terakhir
# ══════════════════════════════════════════════
def get_prev_levels(df, lookback=30):
    """
    Cari swing high & swing low sebagai level likuiditas.
    Swing valid jika menonjol di antara 3 candle kiri & kanan.
    """
    highs = df["high"].values
    lows  = df["low"].values
    n     = len(df)

    swing_highs = []
    swing_lows  = []

    start = max(3, n - lookback)
    for i in range(start, n - 3):
        if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i-3] and
                highs[i] > highs[i+1] and highs[i] > highs[i+2] and highs[i] > highs[i+3]):
            swing_highs.append(highs[i])

        if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i-3] and
                lows[i] < lows[i+1] and lows[i] < lows[i+2] and lows[i] < lows[i+3]):
            swing_lows.append(lows[i])

    prev_high = max(swing_highs) if swing_highs else None
    prev_low  = min(swing_lows)  if swing_lows  else None

    return prev_high, prev_low


# ══════════════════════════════════════════════
# 3. DETEKSI LIQUIDITY SWEEP + MSS
#
#  BULLISH MSS:
#    - Candle spike ke BAWAH previous low (sweep liquidity bawah)
#    - Candle berikutnya close KEMBALI DI ATAS previous low
#    → Struktur bergeser bullish
#
#  BEARISH MSS:
#    - Candle spike ke ATAS previous high (sweep liquidity atas)
#    - Candle berikutnya close KEMBALI DI BAWAH previous high
#    → Struktur bergeser bearish
# ══════════════════════════════════════════════
def detect_mss(df):
    signals    = []
    prev_high, prev_low = get_prev_levels(df)

    if prev_high is None or prev_low is None:
        return signals

    # Candle terakhir dan sebelumnya
    c2 = df.iloc[-3]  # candle sweep (spike)
    c1 = df.iloc[-2]  # candle MSS konfirmasi
    c0 = df.iloc[-1]  # candle terkini

    # ── BULLISH MSS ──────────────────────────────
    # Syarat 1: Ada candle yang spike ke bawah previous low (sweep)
    # Syarat 2: Candle konfirmasi close di ATAS previous low
    sweep_bull = (c2["low"] < prev_low or c1["low"] < prev_low)
    mss_bull   = c1["close"] > prev_low and c0["close"] > prev_low

    if sweep_bull and mss_bull:
        signals.append({
            "type"     : "MSS",
            "direction": "BULLISH 🟢",
            "sweep_lvl": prev_low,
            "detail"   : (f"Sweep Previous Low *{prev_low:.2f}* ✓\n"
                          f"   Close konfirmasi *{c1['close']:.2f}* kembali di atas level")
        })

    # ── BEARISH MSS ──────────────────────────────
    # Syarat 1: Ada candle yang spike ke atas previous high (sweep)
    # Syarat 2: Candle konfirmasi close di BAWAH previous high
    sweep_bear = (c2["high"] > prev_high or c1["high"] > prev_high)
    mss_bear   = c1["close"] < prev_high and c0["close"] < prev_high

    if sweep_bear and mss_bear:
        signals.append({
            "type"     : "MSS",
            "direction": "BEARISH 🔴",
            "sweep_lvl": prev_high,
            "detail"   : (f"Sweep Previous High *{prev_high:.2f}* ✓\n"
                          f"   Close konfirmasi *{c1['close']:.2f}* kembali di bawah level")
        })

    return signals


# ══════════════════════════════════════════════
# 4. DETEKSI ORDER BLOCK (OB)
#    Setelah MSS terkonfirmasi, cari OB relevan:
#    Bullish OB  = candle bearish besar sebelum impulse naik
#    Bearish OB  = candle bullish besar sebelum impulse turun
# ══════════════════════════════════════════════
def detect_ob(df, direction):
    signals = []
    n       = len(df)
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    avg_body = np.mean([abs(c[i]-o[i]) for i in range(max(0,n-20), n)])
    current  = c[-1]

    for i in range(max(0, n-20), n-2):
        body = abs(c[i] - o[i])
        if body < avg_body * 1.0:
            continue

        ob_hi = h[i]
        ob_lo = l[i]

        # Bullish OB: candle bearish (open > close) → harga retracement masuk zona
        if direction == "BULLISH 🟢" and o[i] > c[i]:
            if ob_lo <= current <= ob_hi:
                signals.append({
                    "type"     : "Order Block",
                    "direction": "BULLISH 🟢",
                    "detail"   : f"Harga masuk Bullish OB [{ob_lo:.2f} — {ob_hi:.2f}]"
                })

        # Bearish OB: candle bullish (close > open) → harga retracement masuk zona
        if direction == "BEARISH 🔴" and c[i] > o[i]:
            if ob_lo <= current <= ob_hi:
                signals.append({
                    "type"     : "Order Block",
                    "direction": "BEARISH 🔴",
                    "detail"   : f"Harga masuk Bearish OB [{ob_lo:.2f} — {ob_hi:.2f}]"
                })

    return signals


# ══════════════════════════════════════════════
# 5. DETEKSI FAIR VALUE GAP (FVG)
#    Bullish FVG : low[i+1] > high[i-1]  (gap ke atas)
#    Bearish FVG : high[i+1] < low[i-1]  (gap ke bawah)
#    Harga retracement masuk ke zona gap = konfluensi entry
# ══════════════════════════════════════════════
def detect_fvg(df, direction):
    signals = []
    n = len(df)
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    current = c[-1]

    for i in range(1, n - 1):
        # Bullish FVG
        if direction == "BULLISH 🟢" and l[i+1] > h[i-1]:
            fvg_lo = h[i-1]
            fvg_hi = l[i+1]
            if fvg_lo <= current <= fvg_hi:
                signals.append({
                    "type"     : "Fair Value Gap",
                    "direction": "BULLISH 🟢",
                    "detail"   : f"Harga mengisi Bullish FVG [{fvg_lo:.2f} — {fvg_hi:.2f}]"
                })

        # Bearish FVG
        if direction == "BEARISH 🔴" and h[i+1] < l[i-1]:
            fvg_hi = l[i-1]
            fvg_lo = h[i+1]
            if fvg_lo <= current <= fvg_hi:
                signals.append({
                    "type"     : "Fair Value Gap",
                    "direction": "BEARISH 🔴",
                    "detail"   : f"Harga mengisi Bearish FVG [{fvg_lo:.2f} — {fvg_hi:.2f}]"
                })

    return signals


# ══════════════════════════════════════════════
# 6. FORMAT PESAN NOTIFIKASI
# ══════════════════════════════════════════════
GUIDE = {
    ("MSS", "BULLISH 🟢"): {
        "aksi": "Waspadai peluang BUY — struktur bergeser naik",
        "sl"  : "SL di bawah candle sweep (low yang baru terbentuk)",
        "tp"  : "TP di Previous High / resistance terdekat",
        "tips": "Tunggu harga retracement masuk zona OB atau FVG dulu sebelum entry"
    },
    ("MSS", "BEARISH 🔴"): {
        "aksi": "Waspadai peluang SELL — struktur bergeser turun",
        "sl"  : "SL di atas candle sweep (high yang baru terbentuk)",
        "tp"  : "TP di Previous Low / support terdekat",
        "tips": "Tunggu harga retracement masuk zona OB atau FVG dulu sebelum entry"
    },
    ("Order Block", "BULLISH 🟢"): {
        "aksi": "Pertimbangkan BUY — harga di zona OB",
        "sl"  : "SL beberapa pips di bawah zona OB",
        "tp"  : "TP di high sebelum MSS / resistance terdekat",
        "tips": "Entry saat ada candle bullish konfirmasi (engulfing / pin bar)"
    },
    ("Order Block", "BEARISH 🔴"): {
        "aksi": "Pertimbangkan SELL — harga di zona OB",
        "sl"  : "SL beberapa pips di atas zona OB",
        "tp"  : "TP di low sebelum MSS / support terdekat",
        "tips": "Entry saat ada candle bearish konfirmasi (engulfing / pin bar)"
    },
    ("Fair Value Gap", "BULLISH 🟢"): {
        "aksi": "Pertimbangkan BUY — harga mengisi FVG",
        "sl"  : "SL di bawah FVG",
        "tp"  : "TP di high sebelum gap terbentuk",
        "tips": "Entry saat harga masuk FVG dan mulai rejection ke atas"
    },
    ("Fair Value Gap", "BEARISH 🔴"): {
        "aksi": "Pertimbangkan SELL — harga mengisi FVG",
        "sl"  : "SL di atas FVG",
        "tp"  : "TP di low sebelum gap terbentuk",
        "tips": "Entry saat harga masuk FVG dan mulai rejection ke bawah"
    },
}

def format_message(mss, confluences, df):
    price  = df["close"].iloc[-1]
    hi20   = df["high"].tail(20).max()
    lo20   = df["low"].tail(20).min()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M")
    all_s  = mss + confluences
    total  = len(all_s)

    if total >= 3:
        strength = "🔥 KUAT (3 konfluensi)"
    elif total == 2:
        strength = "✅ SEDANG (2 konfluensi)"
    else:
        strength = "⚡ LEMAH (MSS saja, tunggu OB/FVG)"

    direction = mss[0]["direction"]

    lines = [
        f"📊 *MSS SIGNAL — {SYMBOL}*",
        f"🕐 {now}  |  TF: {TIMEFRAME}",
        f"💰 Harga: *{price:.2f}*",
        f"📈 High 20: {hi20:.2f}   📉 Low 20: {lo20:.2f}",
        f"💪 Kekuatan: {strength}",
        f"🎯 Arah: {direction}",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    for s in all_s:
        g = GUIDE.get((s["type"], s["direction"]))
        lines.append(f"\n🔔 *{s['type']}* — {s['direction']}")
        lines.append(f"   ↳ {s['detail']}")
        if g:
            lines.append(f"\n   📌 *Rekomendasi:*")
            lines.append(f"   • Aksi : {g['aksi']}")
            lines.append(f"   • SL   : {g['sl']}")
            lines.append(f"   • TP   : {g['tp']}")
            lines.append(f"   • 💡   : _{g['tips']}_")
        lines.append("─────────────────────")

    lines.append("\n⚠️ _Konfirmasi di chart sebelum entry. Wajib pakai SL!_")
    lines.append("_Bot ini hanya sinyal, bukan saran finansial._")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# 7. KIRIM TELEGRAM
# ══════════════════════════════════════════════
def send_telegram(msg):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("✅ Notifikasi terkirim")
        else:
            log.error(f"Gagal kirim: {r.text}")
    except Exception as e:
        log.error(f"Error Telegram: {e}")


# ══════════════════════════════════════════════
# 8. MAIN LOOP
# ══════════════════════════════════════════════
sent_cache = set()

def run_bot():
    log.info(f"🤖 Bot MSS {SYMBOL} mulai berjalan...")
    send_telegram(
        f"🤖 *Bot MSS aktif!*\n"
        f"Pair: *{SYMBOL}* | TF: *{TIMEFRAME}*\n"
        f"Strategi: MSS + OB + FVG\n"
        f"Memantau sinyal 24 jam..."
    )

    while True:
        try:
            df = get_candles()
            if df is None or len(df) < 20:
                log.warning("Data tidak cukup, coba lagi...")
                time.sleep(CHECK_INTERVAL)
                continue

            # Step 1 — Deteksi MSS
            mss_signals = detect_mss(df)

            if mss_signals:
                direction = mss_signals[0]["direction"]

                # Step 2 — Cari OB & FVG sesuai arah MSS
                ob_signals  = detect_ob(df, direction)
                fvg_signals = detect_fvg(df, direction)
                confluences = ob_signals + fvg_signals

                # Hindari notif duplikat
                key = str([(s["type"], s["detail"]) for s in mss_signals + confluences])
                if key not in sent_cache:
                    msg = format_message(mss_signals, confluences, df)
                    send_telegram(msg)
                    sent_cache.add(key)
                    if len(sent_cache) > 50:
                        sent_cache.clear()
            else:
                log.info("Tidak ada sinyal MSS saat ini.")

        except Exception as e:
            log.error(f"Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()
