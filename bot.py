import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════
#  APEX BOT — Adaptive Price-action EXecution
#  Strategi : Liquidity Mapping + Sweep + IFVG + MSS + OB/FVG
#  Pair      : XAU/USD  |  Entry TF: M5  |  Bias TF: H1
#  Versi     : Lite (100% gratis)
# ═══════════════════════════════════════════════════════════════

TELEGRAM_TOKEN     = "8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24"
TELEGRAM_CHAT_ID   = "6273206309"
TWELVEDATA_API_KEY = "64d9b87e7c5a4d4f8e625ec95da13b0f"

SYMBOL         = "XAU/USD"
TF_ENTRY       = "5min"
TF_BIAS        = "1h"
CHECK_INTERVAL = 120    # 2 menit (hemat API limit)
LOOKBACK       = 100

# Level psikologis gold (kelipatan $50)
PSYCH_LEVELS = [3000,3050,3100,3150,3200,3250,3300,3350,3400,3450,3500]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# 1. AMBIL DATA CANDLE
# ═══════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════
# 2. REGIME DETECTOR
#    Trending  : ADX > 25 + harga searah EMA50
#    Ranging   : ADX < 20
#    Volatile  : ATR spike > 2x rata-rata → SKIP
# ═══════════════════════════════════════════════════
def detect_regime(df):
    if len(df) < 30:
        return "UNKNOWN"

    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(df)

    # ATR
    tr  = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1,n)]
    atr = np.mean(tr[-14:])
    atr_long = np.mean(tr[-50:]) if len(tr) >= 50 else atr

    if atr > atr_long * 2.0:
        return "VOLATILE"

    # EMA50
    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values

    # ADX (simplified)
    plus_dm  = [max(h[i]-h[i-1], 0) if (h[i]-h[i-1]) > (l[i-1]-l[i]) else 0 for i in range(1,n)]
    minus_dm = [max(l[i-1]-l[i], 0) if (l[i-1]-l[i]) > (h[i]-h[i-1]) else 0 for i in range(1,n)]
    tr_arr   = np.array(tr)
    pdi = 100 * np.mean(plus_dm[-14:])  / (np.mean(tr_arr[-14:]) + 1e-9)
    mdi = 100 * np.mean(minus_dm[-14:]) / (np.mean(tr_arr[-14:]) + 1e-9)
    dx  = 100 * abs(pdi - mdi) / (pdi + mdi + 1e-9)

    price_now = c[-1]

    if dx > 25:
        if price_now > ema50[-1]:
            return "TRENDING_BULL"
        else:
            return "TRENDING_BEAR"
    elif dx < 20:
        return "RANGING"
    else:
        return "NEUTRAL"


# ═══════════════════════════════════════════════════
# 3. HTF BIAS (H1 EMA50)
# ═══════════════════════════════════════════════════
def get_htf_bias(df_h1):
    if df_h1 is None or len(df_h1) < 55:
        return "NEUTRAL"
    c      = df_h1["close"].values
    ema50  = pd.Series(c).ewm(span=50, adjust=False).mean().values
    price  = c[-1]
    if price > ema50[-1] and ema50[-1] > ema50[-5]:
        return "BULLISH"
    elif price < ema50[-1] and ema50[-1] < ema50[-5]:
        return "BEARISH"
    return "NEUTRAL"


# ═══════════════════════════════════════════════════
# 4. KILL ZONE
#    London : 07:00–11:00 UTC (14:00–18:00 WIB)
#    NY     : 12:00–16:00 UTC (19:00–23:00 WIB)
# ═══════════════════════════════════════════════════
def get_kill_zone():
    h = datetime.now(timezone.utc).hour
    if 7 <= h <= 10:
        return True, "🇬🇧 London (14:00–18:00 WIB)"
    elif 12 <= h <= 15:
        return True, "🇺🇸 New York (19:00–23:00 WIB)"
    return False, "😴 Di luar Kill Zone"


# ═══════════════════════════════════════════════════
# 5. LIQUIDITY MAPPING
#    Kumpulkan semua level likuiditas penting
# ═══════════════════════════════════════════════════
def map_liquidity(df, df_h1=None):
    """
    Mengembalikan list level likuiditas beserta tipenya.
    Format: [{"level": float, "type": str, "side": "BSL"/"SSL"}]
    """
    levels = []
    h  = df["high"].values
    l  = df["low"].values
    n  = len(df)

    # ── A. Previous Session High/Low ─────────────────
    # Estimasi dari candle M5: ambil high/low 60 candle lalu (±5 jam)
    if n >= 80:
        session_slice = df.iloc[-80:-20]
        prev_high = session_slice["high"].max()
        prev_low  = session_slice["low"].min()
        levels.append({"level": prev_high, "type": "Prev Session High", "side": "BSL"})
        levels.append({"level": prev_low,  "type": "Prev Session Low",  "side": "SSL"})

    # ── B. Equal Highs / Equal Lows ──────────────────
    # Level yang disentuh 2x atau lebih dalam 50 candle terakhir
    tolerance = 0.5  # dalam pips (untuk gold ~$0.5)
    recent_h  = h[-50:]
    recent_l  = l[-50:]

    # Equal Highs
    for i in range(len(recent_h)):
        for j in range(i+5, len(recent_h)):
            if abs(recent_h[i] - recent_h[j]) <= tolerance:
                eq_level = (recent_h[i] + recent_h[j]) / 2
                # Cek belum ada level serupa
                if not any(abs(lv["level"] - eq_level) < 1.0 for lv in levels):
                    levels.append({"level": round(eq_level,2), "type": "Equal Highs", "side": "BSL"})
                break

    # Equal Lows
    for i in range(len(recent_l)):
        for j in range(i+5, len(recent_l)):
            if abs(recent_l[i] - recent_l[j]) <= tolerance:
                eq_level = (recent_l[i] + recent_l[j]) / 2
                if not any(abs(lv["level"] - eq_level) < 1.0 for lv in levels):
                    levels.append({"level": round(eq_level,2), "type": "Equal Lows", "side": "SSL"})
                break

    # ── C. Psychological Levels ───────────────────────
    price_now = df["close"].iloc[-1]
    for pl in PSYCH_LEVELS:
        if abs(pl - price_now) < 30:  # hanya yang dekat harga saat ini
            side = "BSL" if pl > price_now else "SSL"
            if not any(abs(lv["level"] - pl) < 1.0 for lv in levels):
                levels.append({"level": float(pl), "type": f"Psych ${pl}", "side": side})

    # ── D. Weekly Open ────────────────────────────────
    # Estimasi dari candle pertama dalam 5 hari terakhir (1440 menit / 5min = 288 candle)
    if n >= 288:
        weekly_open = df["open"].iloc[-288]
        side = "BSL" if weekly_open > price_now else "SSL"
        if not any(abs(lv["level"] - weekly_open) < 1.0 for lv in levels):
            levels.append({"level": round(weekly_open,2), "type": "Weekly Open", "side": side})

    # ── E. Swing High / Low (fallback) ───────────────
    for i in range(3, n-3):
        if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
            if not any(abs(lv["level"] - h[i]) < 1.5 for lv in levels):
                levels.append({"level": round(h[i],2), "type": "Swing High", "side": "BSL"})
        if l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]:
            if not any(abs(lv["level"] - l[i]) < 1.5 for lv in levels):
                levels.append({"level": round(l[i],2), "type": "Swing Low", "side": "SSL"})

    # Filter: hanya level yang dekat harga (dalam 50 pips)
    price_now = df["close"].iloc[-1]
    levels = [lv for lv in levels if abs(lv["level"] - price_now) <= 50]

    return levels


# ═══════════════════════════════════════════════════
# 6. DETEKSI SWEEP
#    Candle spike melewati level likuiditas
# ═══════════════════════════════════════════════════
def detect_sweep(df, levels):
    """
    Cari sweep terbaru dalam 5 candle terakhir.
    Sweep BSL: high melewati level, close kembali di bawah
    Sweep SSL: low melewati level, close kembali di atas
    """
    sweeps = []
    n = len(df)

    for lv in levels:
        level = lv["level"]
        side  = lv["side"]

        for i in range(max(1, n-5), n):
            row = df.iloc[i]
            prev_close = df["close"].iloc[i-1]

            # BSL Sweep: high spike di atas level, close kembali di bawah
            if side == "BSL":
                if row["high"] > level and row["close"] < level and prev_close < level:
                    sweeps.append({
                        "lv_type" : lv["type"],
                        "lv_level": level,
                        "side"    : "BSL",
                        "direction": "BEARISH",
                        "candle_idx": i,
                        "spike_high": row["high"],
                        "detail"  : f"Sweep *{lv['type']}* {level:.2f} (BSL)"
                    })

            # SSL Sweep: low spike di bawah level, close kembali di atas
            elif side == "SSL":
                if row["low"] < level and row["close"] > level and prev_close > level:
                    sweeps.append({
                        "lv_type" : lv["type"],
                        "lv_level": level,
                        "side"    : "SSL",
                        "direction": "BULLISH",
                        "candle_idx": i,
                        "spike_low": row["low"],
                        "detail"  : f"Sweep *{lv['type']}* {level:.2f} (SSL)"
                    })

    return sweeps


# ═══════════════════════════════════════════════════
# 7. DETEKSI MSS SETELAH SWEEP
# ═══════════════════════════════════════════════════
def detect_mss_after_sweep(df, sweep):
    """
    Setelah sweep terkonfirmasi, cek MSS:
    - Bearish MSS: candle close di bawah level yang di-sweep
    - Bullish MSS: candle close di atas level yang di-sweep
    """
    n      = len(df)
    idx    = sweep["candle_idx"]
    level  = sweep["lv_level"]
    direction = sweep["direction"]

    # Cek candle setelah sweep
    for i in range(idx+1, min(idx+4, n)):
        close = df["close"].iloc[i]
        if direction == "BEARISH" and close < level:
            return {"confirmed": True, "candle_idx": i,
                    "detail": f"MSS Bearish — close *{close:.2f}* di bawah *{level:.2f}*"}
        elif direction == "BULLISH" and close > level:
            return {"confirmed": True, "candle_idx": i,
                    "detail": f"MSS Bullish — close *{close:.2f}* di atas *{level:.2f}*"}

    return {"confirmed": False}


# ═══════════════════════════════════════════════════
# 8. DETEKSI IFVG
#    FVG yang terbentuk SAAT impulse spike (sebelum MSS),
#    lalu setelah MSS FVG itu terinversi → IFVG = zona entry
# ═══════════════════════════════════════════════════
def detect_ifvg(df, sweep, mss):
    """
    Cari FVG yang terbentuk antara candle sweep dan MSS.
    Itu adalah IFVG — harga retracement masuk = entry signal.
    """
    ifvgs    = []
    n        = len(df)
    h        = df["high"].values
    l        = df["low"].values
    c        = df["close"].values
    direction = sweep["direction"]
    current   = c[-1]

    # Window: dari 2 candle sebelum sweep sampai MSS
    start = max(1, sweep["candle_idx"] - 2)
    end   = min(mss["candle_idx"] + 1, n - 1)

    for i in range(start, end - 1):
        if i+1 >= n:
            break

        # Bearish IFVG (terbentuk saat spike naik, sekarang jadi resistance)
        if direction == "BEARISH":
            # FVG: high[i+1] < low[i-1] → tidak, saat spike naik terbentuk bullish FVG
            # Bullish FVG: low[i+1] > high[i-1]
            if i > 0 and l[i+1] > h[i-1]:
                fvg_lo = h[i-1]
                fvg_hi = l[i+1]
                # Harga retracement masuk zona ini = IFVG entry SELL
                if fvg_lo <= current <= fvg_hi:
                    ifvgs.append({
                        "type"     : "IFVG",
                        "direction": "BEARISH",
                        "fvg_lo"   : round(fvg_lo, 2),
                        "fvg_hi"   : round(fvg_hi, 2),
                        "detail"   : f"Harga masuk IFVG Bearish [{fvg_lo:.2f} — {fvg_hi:.2f}]"
                    })

        # Bullish IFVG (terbentuk saat spike turun, sekarang jadi support)
        elif direction == "BULLISH":
            if i > 0 and h[i+1] < l[i-1]:
                fvg_hi = l[i-1]
                fvg_lo = h[i+1]
                # Harga retracement masuk zona ini = IFVG entry BUY
                if fvg_lo <= current <= fvg_hi:
                    ifvgs.append({
                        "type"     : "IFVG",
                        "direction": "BULLISH",
                        "fvg_lo"   : round(fvg_lo, 2),
                        "fvg_hi"   : round(fvg_hi, 2),
                        "detail"   : f"Harga masuk IFVG Bullish [{fvg_lo:.2f} — {fvg_hi:.2f}]"
                    })

    return ifvgs


# ═══════════════════════════════════════════════════
# 9. KONFLUENSI: OB + FVG BIASA
# ═══════════════════════════════════════════════════
def detect_ob(df, direction):
    n        = len(df)
    o        = df["open"].values
    h        = df["high"].values
    l        = df["low"].values
    c        = df["close"].values
    current  = c[-1]
    avg_body = np.mean([abs(c[i]-o[i]) for i in range(max(0,n-20), n)])

    for i in range(max(0, n-20), n-2):
        body  = abs(c[i]-o[i])
        if body < avg_body: continue
        ob_hi, ob_lo = h[i], l[i]

        if direction == "BULLISH" and o[i] > c[i] and ob_lo <= current <= ob_hi:
            return {"detail": f"Bullish OB [{ob_lo:.2f} — {ob_hi:.2f}]"}
        if direction == "BEARISH" and c[i] > o[i] and ob_lo <= current <= ob_hi:
            return {"detail": f"Bearish OB [{ob_lo:.2f} — {ob_hi:.2f}]"}
    return None


def detect_fvg(df, direction):
    n       = len(df)
    h       = df["high"].values
    l       = df["low"].values
    c       = df["close"].values
    current = c[-1]

    for i in range(1, n-1):
        if direction == "BULLISH" and l[i+1] > h[i-1]:
            flo, fhi = h[i-1], l[i+1]
            if flo <= current <= fhi:
                return {"detail": f"Bullish FVG [{flo:.2f} — {fhi:.2f}]"}
        if direction == "BEARISH" and h[i+1] < l[i-1]:
            fhi, flo = l[i-1], h[i+1]
            if flo <= current <= fhi:
                return {"detail": f"Bearish FVG [{flo:.2f} — {fhi:.2f}]"}
    return None


# ═══════════════════════════════════════════════════
# 10. SCORING SYSTEM
# ═══════════════════════════════════════════════════
def build_score(sweep, mss, ifvgs, ob, fvg, bias, in_kz, kz_name, regime, df):
    direction = sweep["direction"]
    score     = 0
    reasons   = []

    # IFVG (wajib ada — sudah pasti karena kita cek IFVG dulu)
    score += 3
    reasons.append(f"✅ IFVG terkonfirmasi ({ifvgs[0]['detail']})")

    # Sweep quality
    lv_type = sweep["lv_type"]
    if lv_type in ["Prev Session High", "Prev Session Low"]:
        score += 2; reasons.append(f"✅ Sweep level kuat: {lv_type}")
    elif lv_type in ["Equal Highs", "Equal Lows"]:
        score += 2; reasons.append(f"✅ Sweep Equal H/L: {lv_type}")
    elif "Psych" in lv_type:
        score += 2; reasons.append(f"✅ Sweep Psychological: {lv_type}")
    elif lv_type == "Weekly Open":
        score += 1; reasons.append(f"✅ Sweep Weekly Open")
    else:
        score += 1; reasons.append(f"⚡ Sweep Swing H/L biasa")

    # MSS
    score += 1; reasons.append(f"✅ MSS {direction}: {mss['detail']}")

    # HTF Bias
    if bias == direction:
        score += 2; reasons.append("✅ HTF Bias H1 sejajar")
    elif bias == "NEUTRAL":
        score += 1; reasons.append("⚠️ HTF Bias netral")
    else:
        reasons.append("❌ HTF Bias berlawanan — hati-hati!")

    # Kill Zone
    if in_kz:
        score += 1; reasons.append(f"✅ {kz_name}")
    else:
        reasons.append("⚠️ Di luar Kill Zone")

    # Regime
    if regime in ["TRENDING_BULL","TRENDING_BEAR"]:
        score += 1; reasons.append(f"✅ Market sedang trending")
    elif regime == "RANGING":
        reasons.append("⚠️ Market ranging — TP lebih pendek")
    elif regime == "VOLATILE":
        reasons.append("⚠️ Market volatile — waspada spread lebar")

    # Konfluensi OB & FVG
    if ob:
        score += 1; reasons.append(f"✅ OB konfluensi: {ob['detail']}")
    if fvg:
        score += 1; reasons.append(f"✅ FVG konfluensi: {fvg['detail']}")

    # Label kekuatan
    if score >= 10:
        strength = "🔥 SANGAT KUAT"; emoji = "🚨"
    elif score >= 8:
        strength = "💪 KUAT"; emoji = "📣"
    elif score >= 5:
        strength = "✅ SEDANG"; emoji = "📊"
    else:
        strength = "⚡ LEMAH"; emoji = "💡"

    # TP / SL dinamis berbasis ATR
    h_arr = df["high"].values; l_arr = df["low"].values; c_arr = df["close"].values
    tr    = [max(h_arr[i]-l_arr[i], abs(h_arr[i]-c_arr[i-1]), abs(l_arr[i]-c_arr[i-1])) for i in range(1,len(df))]
    atr   = float(np.mean(tr[-14:]))

    # ATR multiplier: lebih longgar kalau volatile/ranging
    sl_mult = 2.0 if regime in ["VOLATILE","RANGING"] else 1.5
    tp_mult = 2.5 if regime == "RANGING" else 3.0

    price = c_arr[-1]
    if direction == "BULLISH":
        sl = round(price - atr * sl_mult, 2)
        tp = round(price + atr * tp_mult, 2)
    else:
        sl = round(price + atr * sl_mult, 2)
        tp = round(price - atr * tp_mult, 2)

    rr = round(abs(tp-price)/abs(sl-price), 1) if abs(sl-price) > 0 else 0

    return {
        "score"   : score,
        "strength": strength,
        "emoji"   : emoji,
        "direction": direction,
        "dir_label": "BUY 📈" if direction=="BULLISH" else "SELL 📉",
        "reasons" : reasons,
        "sl"      : sl,
        "tp"      : tp,
        "rr"      : rr,
        "atr"     : round(atr, 2),
    }


# ═══════════════════════════════════════════════════
# 11. FORMAT NOTIFIKASI TELEGRAM
# ═══════════════════════════════════════════════════
def format_message(sig, sweep, mss, ifvgs, df, bias, kz_name, regime):
    price  = df["close"].iloc[-1]
    hi20   = df["high"].tail(20).max()
    lo20   = df["low"].tail(20).min()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M")
    ifvg   = ifvgs[0]

    regime_labels = {
        "TRENDING_BULL": "📈 Trending Bullish",
        "TRENDING_BEAR": "📉 Trending Bearish",
        "RANGING"      : "↔️ Ranging",
        "VOLATILE"     : "⚡ Volatile",
        "NEUTRAL"      : "😐 Netral",
    }

    lines = [
        f"{sig['emoji']} *APEX SIGNAL — {SYMBOL}*",
        f"🕐 {now}  |  TF: {TF_ENTRY}",
        f"",
        f"💰 Harga    : *{price:.2f}*",
        f"🎯 Sinyal   : *{sig['dir_label']}*",
        f"💪 Kekuatan : *{sig['strength']}*  (Score: {sig['score']})",
        f"🌍 Regime   : {regime_labels.get(regime, regime)}",
        f"📈 HTF Bias : {bias}",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"🔍 *SETUP:*",
        f"   🔸 Sweep : {sweep['detail']}",
        f"   🔸 MSS   : {mss['detail']}",
        f"   🔸 IFVG  : {ifvg['detail']}",
    ]

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📋 *ANALISA:*",
    ]
    for r in sig["reasons"]:
        lines.append(f"   {r}")

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📐 *MANAJEMEN RISIKO:*",
        f"   • Entry : ~*{price:.2f}*",
        f"   • SL    : *{sig['sl']:.2f}*",
        f"   • TP    : *{sig['tp']:.2f}*",
        f"   • R:R   : *1 : {sig['rr']}*",
        f"   • ATR   : {sig['atr']} pips",
        f"",
        f"📊 High 20: {hi20:.2f}  |  Low 20: {lo20:.2f}",
        f"🕐 Sesi   : {kz_name}",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"⚠️ _Konfirmasi di chart sebelum entry._",
        f"_Wajib pasang SL! Bukan saran finansial._",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# 12. KIRIM TELEGRAM
# ═══════════════════════════════════════════════════
def send_telegram(msg):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("✅ Notif terkirim")
        else:
            log.error(f"Gagal kirim: {r.text}")
    except Exception as e:
        log.error(f"Error Telegram: {e}")


# ═══════════════════════════════════════════════════
# 13. MAIN LOOP
# ═══════════════════════════════════════════════════
sent_cache = set()

def run_bot():
    log.info("🚀 APEX Bot mulai berjalan...")
    send_telegram(
        f"🚀 *APEX Bot Aktif!*\n\n"
        f"Pair    : *{SYMBOL}*\n"
        f"Entry TF: *{TF_ENTRY}*  |  Bias TF: *{TF_BIAS}*\n\n"
        f"*Komponen Aktif:*\n"
        f"✅ Liquidity Mapping (5 jenis level)\n"
        f"✅ Sweep Detection\n"
        f"✅ IFVG Entry Zone\n"
        f"✅ MSS Konfirmasi\n"
        f"✅ OB + FVG Konfluensi\n"
        f"✅ Regime Detector\n"
        f"✅ Kill Zone Filter\n"
        f"✅ HTF Bias H1\n"
        f"✅ Auto TP/SL (ATR)\n\n"
        f"_Memantau sinyal 24 jam..._ 👁️"
    )

    while True:
        try:
            df_m5 = get_candles(TF_ENTRY, LOOKBACK)
            df_h1 = get_candles(TF_BIAS, 60)

            if df_m5 is None or len(df_m5) < 30:
                log.warning("Data tidak cukup")
                time.sleep(CHECK_INTERVAL)
                continue

            # ── 1. Regime check
            regime = detect_regime(df_m5)
            if regime == "VOLATILE":
                log.info("Market volatile — skip")
                time.sleep(CHECK_INTERVAL)
                continue

            # ── 2. HTF Bias & Kill Zone
            bias            = get_htf_bias(df_h1)
            in_kz, kz_name  = get_kill_zone()

            # ── 3. Liquidity Mapping
            liq_levels = map_liquidity(df_m5, df_h1)
            if not liq_levels:
                log.info("Tidak ada level likuiditas terdekat")
                time.sleep(CHECK_INTERVAL)
                continue

            # ── 4. Deteksi Sweep
            sweeps = detect_sweep(df_m5, liq_levels)
            if not sweeps:
                log.info("Tidak ada sweep")
                time.sleep(CHECK_INTERVAL)
                continue

            for sweep in sweeps:
                # ── 5. MSS setelah sweep
                mss = detect_mss_after_sweep(df_m5, sweep)
                if not mss["confirmed"]:
                    continue

                direction = sweep["direction"]

                # ── 6. Deteksi IFVG (wajib ada)
                ifvgs = detect_ifvg(df_m5, sweep, mss)
                if not ifvgs:
                    continue  # tidak ada IFVG = tidak kirim notif

                # ── 7. Cari konfluensi OB & FVG
                ob  = detect_ob(df_m5, direction)
                fvg = detect_fvg(df_m5, direction)

                # ── 8. Build score
                sig = build_score(sweep, mss, ifvgs, ob, fvg,
                                  bias, in_kz, kz_name, regime, df_m5)

                # ── 9. Hindari duplikat
                key = f"{direction}_{sweep['lv_level']}_{df_m5['close'].iloc[-1]:.1f}"
                if key in sent_cache:
                    continue

                # ── 10. Kirim notif
                msg = format_message(sig, sweep, mss, ifvgs, df_m5, bias, kz_name, regime)
                send_telegram(msg)
                sent_cache.add(key)
                if len(sent_cache) > 50:
                    sent_cache.clear()

                log.info(f"✅ Signal: {direction} | Score: {sig['score']} | {sweep['detail']}")

        except Exception as e:
            log.error(f"Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()
