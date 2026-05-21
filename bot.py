import time, json, logging, os, requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════
#  APEX BOT — Top-Down Analysis
#  Flow: H1 Bias → H1 Sweep → M5 IFVG/MSS → Entry
#  SL  : Wick sweep candle H1
#  TP  : Minimal 1:2 dari SL
# ═══════════════════════════════════════════════════════

TELEGRAM_TOKEN     = "8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24"
TELEGRAM_CHAT_ID   = "6273206309"
TWELVEDATA_API_KEY = "64d9b87e7c5a4d4f8e625ec95da13b0f"

SYMBOL         = "XAU/USD"
TF_H1          = "1h"
TF_M5          = "5min"
CHECK_INTERVAL = 120        # cek tiap 2 menit
JOURNAL_FILE   = "journal.json"
SL_BUFFER      = 0.5        # buffer di atas/bawah wick sweep (pips)
MIN_RR         = 2.0        # minimum Risk:Reward

PSYCH_LEVELS   = list(range(2800, 3800, 50))  # $2800–$3750, kelipatan $50

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# 1. AMBIL DATA CANDLE
# ═══════════════════════════════════════════════════════
def get_candles(interval, size=100):
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
        log.error(f"Gagal ambil {interval}: {e}")
        return None


# ═══════════════════════════════════════════════════════
# 2. H1 BIAS
#    Baca struktur market H1: HH/HL = Bullish, LH/LL = Bearish
#    Fallback: EMA50
# ═══════════════════════════════════════════════════════
def get_h1_bias(df_h1):
    if df_h1 is None or len(df_h1) < 20:
        return "NEUTRAL"

    h = df_h1["high"].values
    l = df_h1["low"].values
    c = df_h1["close"].values
    n = len(df_h1)

    # Cari swing points terakhir
    swings = []
    for i in range(2, n-2):
        if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
            swings.append(("HH_candidate", i, h[i]))
        if l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]:
            swings.append(("LL_candidate", i, l[i]))

    if len(swings) >= 4:
        recent = swings[-4:]
        highs_recent = [s[2] for s in recent if "HH" in s[0]]
        lows_recent  = [s[2] for s in recent if "LL" in s[0]]

        if len(highs_recent) >= 2 and len(lows_recent) >= 2:
            hh = highs_recent[-1] > highs_recent[-2]  # Higher High
            hl = lows_recent[-1]  > lows_recent[-2]   # Higher Low
            lh = highs_recent[-1] < highs_recent[-2]  # Lower High
            ll = lows_recent[-1]  < lows_recent[-2]   # Lower Low

            if hh and hl: return "BULLISH"
            if lh and ll: return "BEARISH"

    # Fallback EMA50
    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
    if c[-1] > ema50[-1] and ema50[-1] > ema50[-5]: return "BULLISH"
    if c[-1] < ema50[-1] and ema50[-1] < ema50[-5]: return "BEARISH"
    return "NEUTRAL"


# ═══════════════════════════════════════════════════════
# 3. LIQUIDITY MAPPING di H1
#    Level-level penting yang bisa di-sweep
# ═══════════════════════════════════════════════════════
def map_liquidity_h1(df_h1):
    levels = []
    h = df_h1["high"].values
    l = df_h1["low"].values
    n = len(df_h1)
    price_now = df_h1["close"].iloc[-1]

    # A. Previous Session High/Low (sesi 8-24 jam lalu)
    if n >= 30:
        s = df_h1.iloc[-30:-6]
        ph = s["high"].max()
        pl = s["low"].min()
        levels.append({"level": round(ph,2), "type": "Prev Session High", "side": "BSL"})
        levels.append({"level": round(pl,2), "type": "Prev Session Low",  "side": "SSL"})

    # B. Equal Highs / Equal Lows (toleransi 1 pips)
    tol = 1.0
    for i in range(len(h)-20, len(h)-1):
        for j in range(i+3, len(h)-1):
            if abs(h[i]-h[j]) <= tol:
                eq = round((h[i]+h[j])/2, 2)
                if not any(abs(x["level"]-eq) < 2 for x in levels):
                    levels.append({"level": eq, "type": "Equal Highs", "side": "BSL"})
                break
        for j in range(i+3, len(l)-1):
            if abs(l[i]-l[j]) <= tol:
                eq = round((l[i]+l[j])/2, 2)
                if not any(abs(x["level"]-eq) < 2 for x in levels):
                    levels.append({"level": eq, "type": "Equal Lows", "side": "SSL"})
                break

    # C. Psychological Levels (kelipatan $50)
    for pl in PSYCH_LEVELS:
        if abs(pl - price_now) <= 60:
            side = "BSL" if pl > price_now else "SSL"
            if not any(abs(x["level"]-pl) < 2 for x in levels):
                levels.append({"level": float(pl), "type": f"Psych ${pl}", "side": side})

    # D. Weekly Open
    if n >= 120:
        wo = round(df_h1["open"].iloc[-120], 2)
        side = "BSL" if wo > price_now else "SSL"
        if not any(abs(x["level"]-wo) < 2 for x in levels):
            levels.append({"level": wo, "type": "Weekly Open", "side": side})

    # E. Swing High/Low H1
    for i in range(2, n-2):
        if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
            if not any(abs(x["level"]-h[i]) < 2 for x in levels):
                if abs(h[i]-price_now) <= 80:
                    levels.append({"level": round(h[i],2), "type": "H1 Swing High", "side": "BSL"})
        if l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]:
            if not any(abs(x["level"]-l[i]) < 2 for x in levels):
                if abs(l[i]-price_now) <= 80:
                    levels.append({"level": round(l[i],2), "type": "H1 Swing Low", "side": "SSL"})

    return [lv for lv in levels if abs(lv["level"]-price_now) <= 80]


# ═══════════════════════════════════════════════════════
# 4. DETEKSI SWEEP di H1
#    BSL Sweep: high spike di atas level, close kembali di bawah
#    SSL Sweep: low spike di bawah level, close kembali di atas
#    Return: sweep + wick candle (untuk SL)
# ═══════════════════════════════════════════════════════
def detect_h1_sweep(df_h1, levels):
    sweeps = []
    n = len(df_h1)

    for lv in levels:
        level = lv["level"]
        side  = lv["side"]

        # Cek 3 candle H1 terakhir
        for i in range(max(1, n-3), n):
            row  = df_h1.iloc[i]
            prev = df_h1.iloc[i-1]

            if side == "BSL":
                if row["high"] > level and row["close"] < level and prev["close"] < level:
                    sweeps.append({
                        "lv_type"   : lv["type"],
                        "lv_level"  : level,
                        "side"      : "BSL",
                        "direction" : "BEARISH",
                        "candle_idx": i,
                        "wick_high" : row["high"],   # SL di atas wick ini
                        "wick_low"  : row["low"],
                        "detail"    : f"H1 Sweep *{lv['type']}* {level:.2f}"
                    })
            elif side == "SSL":
                if row["low"] < level and row["close"] > level and prev["close"] > level:
                    sweeps.append({
                        "lv_type"   : lv["type"],
                        "lv_level"  : level,
                        "side"      : "SSL",
                        "direction" : "BULLISH",
                        "candle_idx": i,
                        "wick_high" : row["high"],
                        "wick_low"  : row["low"],    # SL di bawah wick ini
                        "detail"    : f"H1 Sweep *{lv['type']}* {level:.2f}"
                    })

    return sweeps


# ═══════════════════════════════════════════════════════
# 5. CEK M5: IFVG ATAU MSS
#    Setelah sweep H1, turun ke M5 untuk cari entry
# ═══════════════════════════════════════════════════════
def find_m5_entry(df_m5, direction):
    """
    Cari IFVG atau MSS di M5 setelah sweep H1.
    Return zona entry jika ditemukan.
    """
    n       = len(df_m5)
    h       = df_m5["high"].values
    l       = df_m5["low"].values
    c       = df_m5["close"].values
    o       = df_m5["open"].values
    current = c[-1]
    entries = []

    # ── A. IFVG di M5 ───────────────────────────────
    # Cari FVG dalam 30 candle terakhir yang sudah terinversi
    for i in range(max(1, n-30), n-1):
        # Bearish IFVG: bullish FVG yang sekarang harga masuk dari atas (resistance)
        if direction == "BEARISH" and i+1 < n:
            if l[i+1] > h[i-1]:              # FVG bullish terbentuk
                flo, fhi = h[i-1], l[i+1]
                # Sudah terinversi jika harga pernah close di bawah flo
                # dan sekarang retracement kembali ke zona
                if flo <= current <= fhi:
                    entries.append({
                        "type"   : "IFVG",
                        "zone_lo": round(flo, 2),
                        "zone_hi": round(fhi, 2),
                        "detail" : f"M5 IFVG Bearish [{flo:.2f} — {fhi:.2f}]"
                    })

        # Bullish IFVG: bearish FVG yang sekarang harga masuk dari bawah (support)
        if direction == "BULLISH" and i+1 < n:
            if h[i+1] < l[i-1]:              # FVG bearish terbentuk
                fhi, flo = l[i-1], h[i+1]
                if flo <= current <= fhi:
                    entries.append({
                        "type"   : "IFVG",
                        "zone_lo": round(flo, 2),
                        "zone_hi": round(fhi, 2),
                        "detail" : f"M5 IFVG Bullish [{flo:.2f} — {fhi:.2f}]"
                    })

    # ── B. MSS di M5 ────────────────────────────────
    # Cari swing high/low M5 yang baru ditembus
    for i in range(2, n-2):
        is_swing_h = h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]
        is_swing_l = l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]

        # MSS Bearish: harga close di bawah swing low M5
        if direction == "BEARISH" and is_swing_l:
            swing_low = l[i]
            if c[-2] >= swing_low and current < swing_low:
                entries.append({
                    "type"   : "MSS",
                    "zone_lo": round(swing_low - 1.0, 2),
                    "zone_hi": round(swing_low + 1.0, 2),
                    "detail" : f"M5 MSS Bearish — close {current:.2f} < swing low {swing_low:.2f}"
                })

        # MSS Bullish: harga close di atas swing high M5
        if direction == "BULLISH" and is_swing_h:
            swing_high = h[i]
            if c[-2] <= swing_high and current > swing_high:
                entries.append({
                    "type"   : "MSS",
                    "zone_lo": round(swing_high - 1.0, 2),
                    "zone_hi": round(swing_high + 1.0, 2),
                    "detail" : f"M5 MSS Bullish — close {current:.2f} > swing high {swing_high:.2f}"
                })

    # Prioritaskan IFVG, lalu MSS
    ifvg_entries = [e for e in entries if e["type"] == "IFVG"]
    mss_entries  = [e for e in entries if e["type"] == "MSS"]
    return (ifvg_entries + mss_entries)[:1]  # ambil yang pertama saja


# ═══════════════════════════════════════════════════════
# 6. HITUNG SL & TP
#    SL = wick sweep H1 + buffer
#    TP = entry ± (SL distance × MIN_RR)
# ═══════════════════════════════════════════════════════
def calc_sl_tp(sweep, entry_price, direction):
    if direction == "BEARISH":
        sl = round(sweep["wick_high"] + SL_BUFFER, 2)   # SL di atas wick
        risk   = abs(sl - entry_price)
        tp     = round(entry_price - risk * MIN_RR, 2)  # TP ke bawah
    else:
        sl   = round(sweep["wick_low"] - SL_BUFFER, 2)  # SL di bawah wick
        risk = abs(entry_price - sl)
        tp   = round(entry_price + risk * MIN_RR, 2)    # TP ke atas

    rr = round(abs(tp - entry_price) / risk, 1) if risk > 0 else 0
    return sl, tp, round(risk, 2), rr


# ═══════════════════════════════════════════════════════
# 7. AUTO JOURNAL
# ═══════════════════════════════════════════════════════
def load_journal():
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "r") as f:
            return json.load(f)
    return {"signals": [], "stats": {"total":0,"win":0,"loss":0,"pending":0}}


def save_journal(journal):
    with open(JOURNAL_FILE, "w") as f:
        json.dump(journal, f, indent=2)


def log_signal(journal, signal_id, direction, entry, sl, tp, sweep_type, entry_type, score):
    journal["signals"].append({
        "id"        : signal_id,
        "time"      : datetime.now().strftime("%Y-%m-%d %H:%M"),
        "direction" : direction,
        "entry"     : entry,
        "sl"        : sl,
        "tp"        : tp,
        "risk"      : round(abs(entry-sl), 2),
        "sweep_type": sweep_type,
        "entry_type": entry_type,
        "score"     : score,
        "result"    : "PENDING",
        "pnl_pips"  : 0
    })
    journal["stats"]["total"]   += 1
    journal["stats"]["pending"] += 1
    save_journal(journal)


def update_results(journal, df_m5):
    """Cek sinyal PENDING — apakah sudah hit TP atau SL"""
    current_price = df_m5["close"].iloc[-1]
    current_high  = df_m5["high"].iloc[-1]
    current_low   = df_m5["low"].iloc[-1]
    updated = False

    for sig in journal["signals"]:
        if sig["result"] != "PENDING":
            continue

        direction = sig["direction"]
        tp = sig["tp"]; sl = sig["sl"]; entry = sig["entry"]

        if direction == "BEARISH":
            if current_low <= tp:
                sig["result"]   = "WIN ✅"
                sig["pnl_pips"] = round(entry - tp, 2)
                journal["stats"]["win"]     += 1
                journal["stats"]["pending"] -= 1
                updated = True
                notify_result(sig)
            elif current_high >= sl:
                sig["result"]   = "LOSS ❌"
                sig["pnl_pips"] = round(entry - sl, 2)
                journal["stats"]["loss"]    += 1
                journal["stats"]["pending"] -= 1
                updated = True
                notify_result(sig)
        else:
            if current_high >= tp:
                sig["result"]   = "WIN ✅"
                sig["pnl_pips"] = round(tp - entry, 2)
                journal["stats"]["win"]     += 1
                journal["stats"]["pending"] -= 1
                updated = True
                notify_result(sig)
            elif current_low <= sl:
                sig["result"]   = "LOSS ❌"
                sig["pnl_pips"] = round(sl - entry, 2)
                journal["stats"]["loss"]    += 1
                journal["stats"]["pending"] -= 1
                updated = True
                notify_result(sig)

    if updated:
        save_journal(journal)

    return journal


def notify_result(sig):
    """Kirim notif hasil trade ke Telegram"""
    won    = "WIN" in sig["result"]
    emoji  = "✅" if won else "❌"
    pnl    = abs(sig["pnl_pips"])
    msg = (
        f"{emoji} *TRADE SELESAI — {SYMBOL}*\n\n"
        f"Sinyal  : *{sig['direction']}* ({sig['entry_type']})\n"
        f"Hasil   : *{sig['result']}*\n"
        f"Entry   : {sig['entry']}  |  {'TP' if won else 'SL'}: {sig['tp'] if won else sig['sl']}\n"
        f"Pips    : *{'+' if won else '-'}{pnl:.1f} pips*\n"
        f"Waktu   : {sig['time']}\n\n"
        f"📓 _Tercatat di journal otomatis_"
    )
    send_telegram(msg)


def get_stats_message(journal):
    s       = journal["stats"]
    total   = s["total"]
    win     = s["win"]
    loss    = s["loss"]
    pending = s["pending"]
    winrate = round((win/max(total-pending,1))*100, 1) if total > 0 else 0

    # Breakdown per sweep type
    by_type = {}
    for sig in journal["signals"]:
        t = sig["sweep_type"]
        if t not in by_type:
            by_type[t] = {"total":0,"win":0}
        by_type[t]["total"] += 1
        if "WIN" in sig.get("result",""):
            by_type[t]["win"] += 1

    breakdown = "\n".join([
        f"   • {k}: {v['win']}/{v['total']} ({round(v['win']/max(v['total'],1)*100)}%)"
        for k,v in sorted(by_type.items(), key=lambda x: -x[1]['total'])
    ]) or "   Belum ada data"

    return (
        f"📓 *APEX JOURNAL — {SYMBOL}*\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"📊 *Statistik Keseluruhan:*\n"
        f"   Total   : {total} sinyal\n"
        f"   WIN     : {win} ✅\n"
        f"   LOSS    : {loss} ❌\n"
        f"   Pending : {pending} ⏳\n"
        f"   Winrate : *{winrate}%*\n\n"
        f"📈 *Winrate per Sweep Type:*\n"
        f"{breakdown}\n\n"
        f"_Ketik /journal untuk update terbaru_"
    )


# ═══════════════════════════════════════════════════════
# 8. FORMAT SINYAL
# ═══════════════════════════════════════════════════════
def format_signal(sweep, entry_zone, sl, tp, risk, rr, bias, score, df_m5):
    price   = df_m5["close"].iloc[-1]
    now     = datetime.now().strftime("%Y-%m-%d %H:%M")
    dir_lbl = "SELL 📉" if sweep["direction"]=="BEARISH" else "BUY 📈"
    emoji   = "🚨" if score >= 8 else "📣" if score >= 5 else "📊"

    strength = "🔥 KUAT" if score >= 8 else "✅ SEDANG" if score >= 5 else "⚡ LEMAH"

    lines = [
        f"{emoji} *APEX SIGNAL — {SYMBOL}*",
        f"🕐 {now}  |  H1→M5",
        f"",
        f"🎯 Sinyal   : *{dir_lbl}*",
        f"💪 Kekuatan : *{strength}* (Score: {score})",
        f"📈 H1 Bias  : *{bias}*",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"🔍 *SETUP:*",
        f"   🔸 H1 Sweep : {sweep['detail']}",
        f"      Wick High: {sweep['wick_high']:.2f}  |  Wick Low: {sweep['wick_low']:.2f}",
        f"   🔸 M5 Entry : {entry_zone['detail']}",
        f"   🔸 Zona     : [{entry_zone['zone_lo']:.2f} — {entry_zone['zone_hi']:.2f}]",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📐 *MANAJEMEN RISIKO:*",
        f"   • Entry : ~*{price:.2f}*",
        f"   • SL    : *{sl:.2f}*  ← wick sweep H1 + buffer",
        f"   • TP    : *{tp:.2f}*",
        f"   • Risk  : {risk:.1f} pips",
        f"   • R:R   : *1 : {rr}* {'✅' if rr >= MIN_RR else '⚠️'}",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"⚠️ _Konfirmasi di chart sebelum entry._",
        f"_SL wajib dipasang di level yang tertera!_",
        f"_📓 Sinyal ini dicatat di journal otomatis._",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 9. SCORING
# ═══════════════════════════════════════════════════════
def calc_score(sweep, entry_zone, bias, rr):
    score   = 0
    direction = sweep["direction"]

    # Entry type
    if entry_zone["type"] == "IFVG":
        score += 3
    else:
        score += 2  # MSS

    # Sweep level quality
    lv = sweep["lv_type"]
    if lv in ["Prev Session High","Prev Session Low"]: score += 3
    elif lv in ["Equal Highs","Equal Lows"]:           score += 3
    elif "Psych" in lv:                                score += 2
    elif lv == "Weekly Open":                          score += 2
    else:                                              score += 1

    # HTF Bias alignment
    if (direction == "BEARISH" and bias == "BEARISH") or \
       (direction == "BULLISH" and bias == "BULLISH"):
        score += 2
    elif bias == "NEUTRAL":
        score += 1

    # RR bonus
    if rr >= 3.0: score += 2
    elif rr >= 2.0: score += 1

    return score


# ═══════════════════════════════════════════════════════
# 10. TELEGRAM
# ═══════════════════════════════════════════════════════
def send_telegram(msg):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            log.error(f"Telegram error: {r.text}")
    except Exception as e:
        log.error(f"Send error: {e}")


def check_telegram_commands(journal):
    """Cek command /journal dari user"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r    = requests.get(url, timeout=5)
        data = r.json()
        if not data.get("ok"): return
        for update in data.get("result",[])[-5:]:
            msg = update.get("message",{}).get("text","")
            if msg.strip() == "/journal":
                send_telegram(get_stats_message(journal))
    except: pass


# ═══════════════════════════════════════════════════════
# 11. MAIN LOOP
# ═══════════════════════════════════════════════════════
sent_cache  = set()
journal     = load_journal()
loop_count  = 0

def run_bot():
    global loop_count, journal

    log.info("🚀 APEX Bot (Top-Down) mulai...")
    send_telegram(
        f"🚀 *APEX Bot Aktif!*\n\n"
        f"*Flow Analisa:*\n"
        f"H1 Bias → H1 Sweep (5 level) → M5 IFVG/MSS\n\n"
        f"*Risk Management:*\n"
        f"SL = Wick sweep candle H1\n"
        f"TP = Minimal 1:{int(MIN_RR)} dari SL\n\n"
        f"*Auto Journal:* ✅ Aktif\n"
        f"Ketik */journal* untuk lihat statistik\n\n"
        f"_Memantau {SYMBOL} 24 jam..._ 👁️"
    )

    while True:
        try:
            loop_count += 1

            # Cek command user setiap 5 loop
            if loop_count % 5 == 0:
                check_telegram_commands(journal)

            # Kirim statistik setiap 6 jam (180 loop × 2 menit)
            if loop_count % 180 == 0 and journal["stats"]["total"] > 0:
                send_telegram(get_stats_message(journal))

            # ── Ambil data
            df_h1 = get_candles(TF_H1, 100)
            df_m5 = get_candles(TF_M5, 100)

            if df_h1 is None or df_m5 is None:
                time.sleep(CHECK_INTERVAL); continue
            if len(df_h1) < 30 or len(df_m5) < 30:
                time.sleep(CHECK_INTERVAL); continue

            # ── Update hasil trade yang pending
            journal = update_results(journal, df_m5)

            # ── Step 1: H1 Bias
            bias = get_h1_bias(df_h1)
            log.info(f"H1 Bias: {bias}")

            # ── Step 2: Liquidity Mapping H1
            liq_levels = map_liquidity_h1(df_h1)
            if not liq_levels:
                log.info("Tidak ada level likuiditas"); time.sleep(CHECK_INTERVAL); continue

            # ── Step 3: Deteksi Sweep H1
            sweeps = detect_h1_sweep(df_h1, liq_levels)
            if not sweeps:
                log.info("Tidak ada sweep H1"); time.sleep(CHECK_INTERVAL); continue

            for sweep in sweeps:
                direction = sweep["direction"]

                # Skip kalau bias berlawanan (opsional — bisa dinonaktifkan)
                if bias != "NEUTRAL" and bias != direction:
                    log.info(f"Bias ({bias}) berlawanan dengan sweep ({direction}) — skip")
                    continue

                # ── Step 4: Cek M5 untuk IFVG atau MSS
                entry_zones = find_m5_entry(df_m5, direction)
                if not entry_zones:
                    log.info(f"Tidak ada entry M5 untuk {direction}")
                    continue

                entry_zone  = entry_zones[0]
                entry_price = df_m5["close"].iloc[-1]

                # ── Step 5: Hitung SL dari wick H1, TP minimal 1:2
                sl, tp, risk, rr = calc_sl_tp(sweep, entry_price, direction)

                # Skip kalau RR kurang dari minimum
                if rr < MIN_RR:
                    log.info(f"RR {rr} < {MIN_RR} — skip"); continue

                # ── Step 6: Scoring
                score = calc_score(sweep, entry_zone, bias, rr)

                # ── Step 7: Hindari duplikat
                key = f"{direction}_{sweep['lv_level']}_{entry_price:.1f}"
                if key in sent_cache: continue

                # ── Step 8: Kirim sinyal
                msg = format_signal(sweep, entry_zone, sl, tp, risk, rr, bias, score, df_m5)
                send_telegram(msg)

                # ── Step 9: Catat ke journal
                sig_id = f"{datetime.now().strftime('%Y%m%d%H%M')}_{direction[:4]}"
                log_signal(journal, sig_id, direction, entry_price, sl, tp,
                           sweep["lv_type"], entry_zone["type"], score)

                sent_cache.add(key)
                if len(sent_cache) > 100: sent_cache.clear()

                log.info(f"✅ Signal: {direction} | {entry_zone['type']} | Score:{score} | RR:{rr}")

        except Exception as e:
            log.error(f"Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()
