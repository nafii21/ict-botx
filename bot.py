import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════
#  SMART MONEY CONFLUENCE BOT — by Claude
#  Strategi: HTF Bias + Kill Zone + MSS + OB/FVG + ADR
#  Pair   : XAU/USD  |  Entry TF: M5  |  Bias TF: H1
# ═══════════════════════════════════════════════════════

TELEGRAM_TOKEN     = "8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24"
TELEGRAM_CHAT_ID   = "6273206309"
TWELVEDATA_API_KEY = "64d9b87e7c5a4d4f8e625ec95da13b0f"

SYMBOL         = "XAU/USD"
TF_ENTRY       = "5min"    # timeframe entry
TF_BIAS        = "1h"      # timeframe HTF untuk bias
CHECK_INTERVAL = 120       # cek tiap 2 menit (hemat API limit)
LOOKBACK       = 100

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# 1. AMBIL DATA CANDLE
# ═══════════════════════════════════════════════════════
def get_candles(interval=TF_ENTRY, size=LOOKBACK):
    url    = "https://api.twelvedata.com/time_series"
    params = {
        "symbol"    : SYMBOL,
        "interval"  : interval,
        "outputsize": size,
        "apikey"    : TWELVEDATA_API_KEY,
        "format"    : "JSON"
    }
    try:
        r    = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "values" not in data:
            log.error(f"API error ({interval}): {data}")
            return None
        df = pd.DataFrame(data["values"])
        df[["open","high","low","close"]] = df[["open","high","low","close"]].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        log.error(f"Gagal ambil data {interval}: {e}")
        return None


# ═══════════════════════════════════════════════════════
# 2. HTF BIAS (H1)
#    Gunakan EMA 50 di H1 untuk tentukan bias pasar
#    Harga di atas EMA50 H1 = BULLISH BIAS
#    Harga di bawah EMA50 H1 = BEARISH BIAS
# ═══════════════════════════════════════════════════════
def get_htf_bias(df_h1):
    if df_h1 is None or len(df_h1) < 55:
        return "NEUTRAL"

    closes  = df_h1["close"].values
    ema50   = pd.Series(closes).ewm(span=50, adjust=False).mean().values
    price   = closes[-1]
    ema_now = ema50[-1]
    ema_prev= ema50[-3]

    # Bias bullish: harga di atas EMA50 dan EMA50 naik
    if price > ema_now and ema_now > ema_prev:
        return "BULLISH"
    # Bias bearish: harga di bawah EMA50 dan EMA50 turun
    elif price < ema_now and ema_now < ema_prev:
        return "BEARISH"
    else:
        return "NEUTRAL"


# ═══════════════════════════════════════════════════════
# 3. KILL ZONE FILTER
#    Hanya trading saat volatilitas tinggi:
#    - London Session : 14:00 – 18:00 WIB (07:00–11:00 UTC)
#    - New York Session: 19:00 – 23:00 WIB (12:00–16:00 UTC)
#    Di luar jam ini sinyal diabaikan (market sepi)
# ═══════════════════════════════════════════════════════
def in_kill_zone():
    now_utc  = datetime.now(timezone.utc)
    hour_utc = now_utc.hour

    london_kz  = 7  <= hour_utc <= 10   # London open
    newyork_kz = 12 <= hour_utc <= 16   # New York open

    if london_kz:
        return True, "🇬🇧 London Session (14:00–18:00 WIB)"
    elif newyork_kz:
        return True, "🇺🇸 New York Session (19:00–23:00 WIB)"
    else:
        return False, "😴 Di luar Kill Zone"


# ═══════════════════════════════════════════════════════
# 4. ADR FILTER (Average Daily Range)
#    Jika harga sudah bergerak > 80% dari ADR harian,
#    potensi move sudah kecil → skip sinyal
# ═══════════════════════════════════════════════════════
def adr_filter(df_m5, threshold=0.8):
    # Ambil range hari ini dari candle M5
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        today_candles = df_m5[df_m5["datetime"].astype(str).str.startswith(today_str)]
    except Exception:
        today_candles = df_m5.tail(80)

    if len(today_candles) < 5:
        today_candles = df_m5.tail(80)

    day_high  = today_candles["high"].max()
    day_low   = today_candles["low"].min()
    day_range = day_high - day_low

    # Estimasi ADR dari 5 hari terakhir
    adr_estimate = df_m5["high"].tail(200).max() - df_m5["low"].tail(200).min()
    adr_daily    = adr_estimate / 5  # kasar

    if adr_daily == 0:
        return True, day_range, adr_daily

    ratio = day_range / adr_daily
    return ratio < threshold, round(day_range, 2), round(adr_daily, 2)


# ═══════════════════════════════════════════════════════
# 5. SWING HIGH / LOW (level likuiditas)
# ═══════════════════════════════════════════════════════
def get_swing_levels(df, lookback=30):
    h = df["high"].values
    l = df["low"].values
    n = len(df)

    swing_highs, swing_lows = [], []
    start = max(3, n - lookback)

    for i in range(start, n - 3):
        if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
            swing_highs.append(h[i])
        if l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]:
            swing_lows.append(l[i])

    prev_high = max(swing_highs) if swing_highs else None
    prev_low  = min(swing_lows)  if swing_lows  else None
    return prev_high, prev_low


# ═══════════════════════════════════════════════════════
# 6. DETEKSI MSS + LIQUIDITY SWEEP
# ═══════════════════════════════════════════════════════
def detect_mss(df):
    prev_high, prev_low = get_swing_levels(df)
    if not prev_high or not prev_low:
        return None

    c2 = df.iloc[-3]
    c1 = df.iloc[-2]

    # BULLISH MSS: spike bawah prev_low → close kembali di atas
    if (c2["low"] < prev_low or c1["low"] < prev_low) and c1["close"] > prev_low:
        return {
            "direction": "BULLISH",
            "level"    : prev_low,
            "detail"   : f"Sweep Low *{prev_low:.2f}* → Close *{c1['close']:.2f}* di atas level"
        }

    # BEARISH MSS: spike atas prev_high → close kembali di bawah
    if (c2["high"] > prev_high or c1["high"] > prev_high) and c1["close"] < prev_high:
        return {
            "direction": "BEARISH",
            "level"    : prev_high,
            "detail"   : f"Sweep High *{prev_high:.2f}* → Close *{c1['close']:.2f}* di bawah level"
        }

    return None


# ═══════════════════════════════════════════════════════
# 7. DETEKSI ORDER BLOCK
# ═══════════════════════════════════════════════════════
def detect_ob(df, direction):
    n = len(df)
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    current  = c[-1]
    avg_body = np.mean([abs(c[i]-o[i]) for i in range(max(0,n-20), n)])

    for i in range(max(0, n-20), n-2):
        body = abs(c[i] - o[i])
        if body < avg_body:
            continue
        ob_hi, ob_lo = h[i], l[i]

        if direction == "BULLISH" and o[i] > c[i] and ob_lo <= current <= ob_hi:
            return {"zone": (ob_lo, ob_hi), "detail": f"Bullish OB [{ob_lo:.2f} — {ob_hi:.2f}]"}
        if direction == "BEARISH" and c[i] > o[i] and ob_lo <= current <= ob_hi:
            return {"zone": (ob_lo, ob_hi), "detail": f"Bearish OB [{ob_lo:.2f} — {ob_hi:.2f}]"}

    return None


# ═══════════════════════════════════════════════════════
# 8. DETEKSI FVG
# ═══════════════════════════════════════════════════════
def detect_fvg(df, direction):
    n = len(df)
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    current = c[-1]

    for i in range(1, n - 1):
        if direction == "BULLISH" and l[i+1] > h[i-1]:
            flo, fhi = h[i-1], l[i+1]
            if flo <= current <= fhi:
                return {"zone": (flo, fhi), "detail": f"Bullish FVG [{flo:.2f} — {fhi:.2f}]"}
        if direction == "BEARISH" and h[i+1] < l[i-1]:
            fhi, flo = l[i-1], h[i+1]
            if flo <= current <= fhi:
                return {"zone": (flo, fhi), "detail": f"Bearish FVG [{flo:.2f} — {fhi:.2f}]"}

    return None


# ═══════════════════════════════════════════════════════
# 9. HITUNG SCORE & REKOMENDASI TP/SL
# ═══════════════════════════════════════════════════════
def build_signal(mss, ob, fvg, bias, in_kz, kz_name, df):
    direction = mss["direction"]
    price     = df["close"].iloc[-1]
    score     = 0
    reasons   = []

    # Scoring system
    score += 2; reasons.append("✅ MSS terkonfirmasi")

    if bias == direction:
        score += 2; reasons.append("✅ HTF Bias H1 sejajar")
    elif bias == "NEUTRAL":
        score += 1; reasons.append("⚠️ HTF Bias netral")
    else:
        reasons.append("❌ HTF Bias berlawanan")

    if in_kz:
        score += 2; reasons.append(f"✅ Dalam Kill Zone ({kz_name})")
    else:
        reasons.append("⚠️ Di luar Kill Zone")

    if ob:
        score += 2; reasons.append(f"✅ Order Block: {ob['detail']}")
    if fvg:
        score += 2; reasons.append(f"✅ Fair Value Gap: {fvg['detail']}")

    # Label kekuatan
    if score >= 8:
        strength = "🔥 SANGAT KUAT"
        emoji    = "🚨"
    elif score >= 6:
        strength = "💪 KUAT"
        emoji    = "📣"
    elif score >= 4:
        strength = "✅ SEDANG"
        emoji    = "📊"
    else:
        strength = "⚡ LEMAH"
        emoji    = "💤"

    # TP & SL otomatis
    prev_high, prev_low = get_swing_levels(df, lookback=50)
    atr = df["high"].tail(14).values - df["low"].tail(14).values
    atr_val = float(np.mean(atr))

    if direction == "BULLISH":
        sl = round(price - atr_val * 1.5, 2)
        tp = round(price + atr_val * 3.0, 2)
        rr = round((tp - price) / (price - sl), 1) if price > sl else 0
        dir_label = "BUY 📈"
        dir_emoji = "🟢"
    else:
        sl = round(price + atr_val * 1.5, 2)
        tp = round(price - atr_val * 3.0, 2)
        rr = round((price - tp) / (sl - price), 1) if sl > price else 0
        dir_label = "SELL 📉"
        dir_emoji = "🔴"

    return {
        "score"   : score,
        "strength": strength,
        "emoji"   : emoji,
        "dir"     : dir_label,
        "dir_emoji": dir_emoji,
        "reasons" : reasons,
        "sl"      : sl,
        "tp"      : tp,
        "rr"      : rr,
        "atr"     : round(atr_val, 2),
    }


# ═══════════════════════════════════════════════════════
# 10. FORMAT PESAN TELEGRAM
# ═══════════════════════════════════════════════════════
def format_message(sig, mss, ob, fvg, bias, kz_name, df):
    price  = df["close"].iloc[-1]
    hi20   = df["high"].tail(20).max()
    lo20   = df["low"].tail(20).min()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"{sig['emoji']} *SMART MONEY SIGNAL — {SYMBOL}*",
        f"🕐 {now}  |  TF: {TF_ENTRY}",
        f"",
        f"💰 Harga   : *{price:.2f}*",
        f"🎯 Sinyal  : *{sig['dir']}*",
        f"💪 Kekuatan: *{sig['strength']}* (Score: {sig['score']}/10)",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📋 *ANALISA:*",
    ]

    for r in sig["reasons"]:
        lines.append(f"   {r}")

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📌 *SETUP:*",
        f"   🔔 MSS  : {mss['detail']}",
    ]
    if ob:
        lines.append(f"   🟧 OB   : {ob['detail']}")
    if fvg:
        lines.append(f"   🟦 FVG  : {fvg['detail']}")

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📐 *MANAJEMEN RISIKO:*",
        f"   • Entry : sekitar *{price:.2f}*",
        f"   • SL    : *{sig['sl']:.2f}*  (1.5x ATR)",
        f"   • TP    : *{sig['tp']:.2f}*  (3.0x ATR)",
        f"   • R:R   : *1 : {sig['rr']}*",
        f"   • ATR   : {sig['atr']} pips",
        f"",
        f"📊 High 20 candle: {hi20:.2f}",
        f"📊 Low  20 candle: {lo20:.2f}",
        f"🌍 Sesi  : {kz_name}",
        f"📈 Bias H1: {bias}",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"⚠️ _Konfirmasi di chart sebelum entry._",
        f"_Wajib pakai SL! Bot ini bukan saran finansial._",
    ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 11. KIRIM TELEGRAM
# ═══════════════════════════════════════════════════════
def send_telegram(msg):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("✅ Notif terkirim")
        else:
            log.error(f"Gagal: {r.text}")
    except Exception as e:
        log.error(f"Telegram error: {e}")


# ═══════════════════════════════════════════════════════
# 12. MAIN LOOP
# ═══════════════════════════════════════════════════════
sent_cache = set()

def run_bot():
    log.info("🤖 Smart Money Bot mulai...")
    send_telegram(
        f"🤖 *Smart Money Confluence Bot Aktif!*\n\n"
        f"Pair   : *{SYMBOL}*\n"
        f"Entry TF: *{TF_ENTRY}*  |  Bias TF: *{TF_BIAS}*\n\n"
        f"*Strategi:*\n"
        f"✅ HTF Bias (EMA50 H1)\n"
        f"✅ Kill Zone Filter (London & NY)\n"
        f"✅ Liquidity Sweep + MSS\n"
        f"✅ Order Block konfluensi\n"
        f"✅ Fair Value Gap konfluensi\n"
        f"✅ Auto TP/SL berbasis ATR\n\n"
        f"Memantau sinyal 24 jam... 🚀"
    )

    while True:
        try:
            # Ambil data M5 dan H1
            df_m5 = get_candles(TF_ENTRY, LOOKBACK)
            df_h1 = get_candles(TF_BIAS, 60)

            if df_m5 is None or len(df_m5) < 20:
                log.warning("Data M5 tidak cukup")
                time.sleep(CHECK_INTERVAL)
                continue

            # ── Filter 1: HTF Bias
            bias = get_htf_bias(df_h1)

            # ── Filter 2: Kill Zone
            in_kz, kz_name = in_kill_zone()

            # ── Filter 3: ADR (jangan trade kalau range sudah terlalu lebar)
            adr_ok, day_range, adr_est = adr_filter(df_m5)
            if not adr_ok:
                log.info(f"ADR terlalu lebar ({day_range}/{adr_est}), skip.")
                time.sleep(CHECK_INTERVAL)
                continue

            # ── Deteksi MSS
            mss = detect_mss(df_m5)
            if not mss:
                log.info("Tidak ada MSS.")
                time.sleep(CHECK_INTERVAL)
                continue

            direction = mss["direction"]

            # ── Deteksi OB & FVG
            ob  = detect_ob(df_m5, direction)
            fvg = detect_fvg(df_m5, direction)

            # ── Build signal & scoring
            sig = build_signal(mss, ob, fvg, bias, in_kz, kz_name, df_m5)

            # Hanya kirim kalau score minimal 4 (ada MSS + 1 faktor lain)
            if sig["score"] < 4:
                log.info(f"Score terlalu rendah ({sig['score']}), skip.")
                time.sleep(CHECK_INTERVAL)
                continue

            # Hindari duplikat
            key = f"{direction}_{mss['level']}_{df_m5['close'].iloc[-1]:.1f}"
            if key in sent_cache:
                log.info("Sinyal sudah dikirim sebelumnya.")
                time.sleep(CHECK_INTERVAL)
                continue

            msg = format_message(sig, mss, ob, fvg, bias, kz_name, df_m5)
            send_telegram(msg)
            sent_cache.add(key)
            if len(sent_cache) > 50:
                sent_cache.clear()

        except Exception as e:
            log.error(f"Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()
