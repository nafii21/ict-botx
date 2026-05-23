import time, json, logging, os, requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════
#  APEX FIBONACCI BOT — Telegram Notif Only
#  Strategi : EMA 200 Trend Filter + Fibonacci 61.8% H1
#
#  Trend BULLISH (harga > EMA200) → hanya cari setup BUY
#  Trend BEARISH (harga < EMA200) → hanya cari setup SELL
#
#  BUY  : Swing Low (A) → Swing High (B) → retrace 61.8% → BUY
#  SELL : Swing High (A) → Swing Low (B) → retrace 61.8% → SELL
#  SL   : Di atas/bawah Swing A + buffer
#  TP   : Minimal 1:2 dari SL
# ═══════════════════════════════════════════════════════════════

TELEGRAM_TOKEN     = "8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24"
TELEGRAM_CHAT_ID   = "6273206309"
TWELVEDATA_API_KEY = "64d9b87e7c5a4d4f8e625ec95da13b0f"

SYMBOL             = "XAU/USD"
TF                 = "1h"
CHECK_INTERVAL     = 120
JOURNAL_FILE       = "journal.json"
EMA_PERIOD         = 200
FIB_LEVEL          = 0.618
FIB_ZONE           = 0.010     # toleransi zona ±1%
SL_BUFFER          = 0.5
MIN_RR             = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. AMBIL DATA CANDLE H1
# ═══════════════════════════════════════════════════════════════
def get_candles(size=250):
    url    = "https://api.twelvedata.com/time_series"
    params = {
        "symbol"    : SYMBOL,
        "interval"  : TF,
        "outputsize": size,
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
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        log.error(f"Gagal ambil data: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# 2. TREND FILTER — EMA 200
#    Harga > EMA200 → BULLISH → hanya cari BUY
#    Harga < EMA200 → BEARISH → hanya cari SELL
# ═══════════════════════════════════════════════════════════════
def get_trend(df):
    if len(df) < EMA_PERIOD + 5:
        return "NEUTRAL", 0.0

    closes  = df["close"].values
    ema200  = pd.Series(closes).ewm(span=EMA_PERIOD, adjust=False).mean().values
    price   = closes[-1]
    ema_now = ema200[-1]
    ema_prev= ema200[-5]

    if price > ema_now:
        trend = "BULLISH"
    elif price < ema_now:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return trend, round(ema_now, 2)


# ═══════════════════════════════════════════════════════════════
# 3. DETEKSI SWING HIGH & SWING LOW
# ═══════════════════════════════════════════════════════════════
def find_swings(df, strength=3):
    h = df["high"].values
    l = df["low"].values
    n = len(df)
    swings = []

    for i in range(strength, n - strength):
        if all(h[i] > h[i-k] for k in range(1, strength+1)) and \
           all(h[i] > h[i+k] for k in range(1, strength+1)):
            swings.append({"type":"HIGH", "idx":i, "price":round(h[i],2)})

        if all(l[i] < l[i-k] for k in range(1, strength+1)) and \
           all(l[i] < l[i+k] for k in range(1, strength+1)):
            swings.append({"type":"LOW", "idx":i, "price":round(l[i],2)})

    swings.sort(key=lambda x: x["idx"])
    return swings


# ═══════════════════════════════════════════════════════════════
# 4. DETEKSI SETUP FIBONACCI 61.8%
#    Hanya cari setup yang sesuai dengan trend EMA200
# ═══════════════════════════════════════════════════════════════
def detect_fib_setup(df, trend):
    if trend == "NEUTRAL":
        return None

    swings        = find_swings(df, strength=3)
    current_price = df["close"].iloc[-1]
    n             = len(df)

    if len(swings) < 2:
        return None

    for i in range(len(swings)-1, 0, -1):
        B = swings[i]
        A = swings[i-1]

        # Tidak terlalu lama (maks 60 candle)
        if n - B["idx"] > 60:
            break

        swing_range = abs(A["price"] - B["price"])
        if swing_range < 5:
            continue

        # ── SELL Setup: A=HIGH, B=LOW (hanya jika trend BEARISH) ──
        if trend == "BEARISH" and A["type"] == "HIGH" and B["type"] == "LOW":
            fib_618 = round(B["price"] + (A["price"] - B["price"]) * FIB_LEVEL, 2)
            zone_lo = round(B["price"] + (A["price"] - B["price"]) * (FIB_LEVEL - FIB_ZONE), 2)
            zone_hi = round(B["price"] + (A["price"] - B["price"]) * (FIB_LEVEL + FIB_ZONE), 2)
            sl      = round(A["price"] + SL_BUFFER, 2)
            risk    = round(abs(fib_618 - sl), 2)
            tp      = round(fib_618 - risk * MIN_RR, 2)
            rr      = round(abs(fib_618 - tp) / risk, 1) if risk > 0 else MIN_RR

            if zone_lo <= current_price <= zone_hi and current_price < A["price"]:
                return {
                    "direction"  : "BEARISH",
                    "dir_label"  : "SELL 📉",
                    "trend"      : "BEARISH 📉",
                    "swing_A"    : A,
                    "swing_B"    : B,
                    "fib_618"    : fib_618,
                    "zone_lo"    : zone_lo,
                    "zone_hi"    : zone_hi,
                    "sl"         : sl,
                    "tp"         : tp,
                    "risk"       : risk,
                    "rr"         : rr,
                    "swing_range": swing_range,
                }

        # ── BUY Setup: A=LOW, B=HIGH (hanya jika trend BULLISH) ──
        elif trend == "BULLISH" and A["type"] == "LOW" and B["type"] == "HIGH":
            fib_618 = round(B["price"] - (B["price"] - A["price"]) * FIB_LEVEL, 2)
            zone_lo = round(B["price"] - (B["price"] - A["price"]) * (FIB_LEVEL + FIB_ZONE), 2)
            zone_hi = round(B["price"] - (B["price"] - A["price"]) * (FIB_LEVEL - FIB_ZONE), 2)
            sl      = round(A["price"] - SL_BUFFER, 2)
            risk    = round(abs(fib_618 - sl), 2)
            tp      = round(fib_618 + risk * MIN_RR, 2)
            rr      = round(abs(tp - fib_618) / risk, 1) if risk > 0 else MIN_RR

            if zone_lo <= current_price <= zone_hi and current_price > A["price"]:
                return {
                    "direction"  : "BULLISH",
                    "dir_label"  : "BUY 📈",
                    "trend"      : "BULLISH 📈",
                    "swing_A"    : A,
                    "swing_B"    : B,
                    "fib_618"    : fib_618,
                    "zone_lo"    : zone_lo,
                    "zone_hi"    : zone_hi,
                    "sl"         : sl,
                    "tp"         : tp,
                    "risk"       : risk,
                    "rr"         : rr,
                    "swing_range": swing_range,
                }

    return None


# ═══════════════════════════════════════════════════════════════
# 5. FORMAT PESAN SINYAL
# ═══════════════════════════════════════════════════════════════
def format_signal(setup, ema200, entry_price):
    now       = datetime.now().strftime("%Y-%m-%d %H:%M")
    A         = setup["swing_A"]
    B         = setup["swing_B"]
    direction = setup["direction"]

    lines = [
        f"📐 *APEX FIB SIGNAL — {SYMBOL}*",
        f"🕐 {now}  |  TF: H1",
        f"",
        f"🎯 Sinyal    : *{setup['dir_label']}*",
        f"📊 Trend H1  : *{setup['trend']}*",
        f"〽️ EMA 200   : *{ema200:.2f}*",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📈 *FIBONACCI SETUP:*",
        f"   {'🔴 Swing High' if A['type']=='HIGH' else '🟢 Swing Low'} A : *{A['price']:.2f}*",
        f"   {'🟢 Swing Low'  if B['type']=='LOW'  else '🔴 Swing High'} B : *{B['price']:.2f}*",
        f"   📏 Range Swing   : {setup['swing_range']:.2f} pips",
        f"   🎯 Level 61.8%  : *{setup['fib_618']:.2f}*",
        f"   📦 Zona Entry    : {setup['zone_lo']:.2f} — {setup['zone_hi']:.2f}",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📐 *MANAJEMEN RISIKO:*",
        f"   • Entry : *{entry_price:.2f}*",
        f"   • SL    : *{setup['sl']:.2f}*",
        f"     ↳ {'Di atas Swing High A' if direction=='BEARISH' else 'Di bawah Swing Low A'}",
        f"   • TP    : *{setup['tp']:.2f}*",
        f"     ↳ Minimal 1:{int(MIN_RR)} dari SL",
        f"   • Risk  : {setup['risk']:.1f} pips",
        f"   • R:R   : *1:{setup['rr']}* ✅",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"⚠️ _Konfirmasi di chart sebelum entry._",
        f"_Wajib pasang SL! Bukan saran finansial._",
        f"_📓 Dicatat otomatis di journal._",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 6. AUTO JOURNAL
# ═══════════════════════════════════════════════════════════════
def load_journal():
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE,"r") as f: return json.load(f)
        except: pass
    return {"signals":[],"stats":{
        "total":0,"win":0,"loss":0,"pending":0,
        "pips_win":0.0,"pips_loss":0.0
    }}

def save_journal(j):
    with open(JOURNAL_FILE,"w") as f: json.dump(j,f,indent=2)

def log_to_journal(journal, sig_id, setup, entry):
    journal["signals"].append({
        "id"        : sig_id,
        "time"      : datetime.now().strftime("%Y-%m-%d %H:%M"),
        "direction" : setup["direction"],
        "trend"     : setup["trend"],
        "entry"     : entry,
        "sl"        : setup["sl"],
        "tp"        : setup["tp"],
        "risk_pips" : setup["risk"],
        "rr"        : setup["rr"],
        "fib_618"   : setup["fib_618"],
        "swing_A"   : setup["swing_A"]["price"],
        "swing_B"   : setup["swing_B"]["price"],
        "result"    : "PENDING ⏳",
        "pnl_pips"  : 0.0,
        "close_time": ""
    })
    journal["stats"]["total"]   += 1
    journal["stats"]["pending"] += 1
    save_journal(journal)

def update_results(journal, df):
    hi = df["high"].iloc[-1]
    lo = df["low"].iloc[-1]
    updated = False
    for sig in journal["signals"]:
        if "PENDING" not in sig["result"]: continue
        d=sig["direction"]; tp=sig["tp"]; sl=sig["sl"]
        entry=sig["entry"]; risk=abs(entry-sl)
        result=None; pnl=0.0
        if d=="BEARISH":
            if lo<=tp:
                result="WIN ✅"; pnl=round(entry-tp,2)
                journal["stats"]["win"]+=1; journal["stats"]["pips_win"]+=pnl
            elif hi>=sl:
                result="LOSS ❌"; pnl=round(entry-sl,2)
                journal["stats"]["loss"]+=1; journal["stats"]["pips_loss"]+=abs(pnl)
        else:
            if hi>=tp:
                result="WIN ✅"; pnl=round(tp-entry,2)
                journal["stats"]["win"]+=1; journal["stats"]["pips_win"]+=pnl
            elif lo<=sl:
                result="LOSS ❌"; pnl=round(sl-entry,2)
                journal["stats"]["loss"]+=1; journal["stats"]["pips_loss"]+=abs(pnl)
        if result:
            sig["result"]=result; sig["pnl_pips"]=pnl
            sig["close_time"]=datetime.now().strftime("%Y-%m-%d %H:%M")
            journal["stats"]["pending"]-=1
            updated=True; send_result_notif(sig)
    if updated: save_journal(journal)
    return journal

def send_result_notif(sig):
    won=("WIN" in sig["result"]); emoji="✅" if won else "❌"
    pnl=abs(sig["pnl_pips"])
    rr_a=round(pnl/sig["risk_pips"],1) if sig["risk_pips"]>0 else 0
    msg=(
        f"{emoji} *TRADE SELESAI — {SYMBOL}*\n\n"
        f"🎯 Arah   : *{sig['direction']}*\n"
        f"📊 Trend  : {sig['trend']}\n"
        f"📐 Fib    : A={sig['swing_A']:.2f} → B={sig['swing_B']:.2f} → 61.8%={sig['fib_618']:.2f}\n\n"
        f"💰 Entry  : {sig['entry']:.2f}\n"
        f"{'✅ TP' if won else '❌ SL'}   : {sig['tp'] if won else sig['sl']:.2f}\n\n"
        f"📊 Hasil  : *{'+' if won else '-'}{pnl:.1f} pips*\n"
        f"📐 R:R    : *1:{rr_a}*\n"
        f"🕐 Buka   : {sig['time']}\n"
        f"🕐 Tutup  : {sig['close_time']}\n\n"
        f"🟢 *Bot siap mencari sinyal berikutnya!*\n"
        f"_Ketik /journal untuk statistik._"
    )
    send_telegram(msg)

def has_running_trade(journal):
    return any("PENDING" in s["result"] for s in journal["signals"])

def get_running_trade(journal):
    for s in journal["signals"]:
        if "PENDING" in s["result"]: return s
    return None

def get_stats_message(journal):
    s=journal["stats"]; total=s["total"]; win=s["win"]; loss=s["loss"]
    pending=s["pending"]; closed=total-pending
    wr=round(win/closed*100,1) if closed>0 else 0
    net=round(s["pips_win"]-s["pips_loss"],1)

    running=get_running_trade(journal)
    run_txt=""
    if running:
        run_txt=(
            f"\n⏳ *Trade Running:*\n"
            f"   {running['direction']} | Entry:{running['entry']:.2f} "
            f"SL:{running['sl']:.2f} TP:{running['tp']:.2f}\n"
        )

    recent=[s for s in journal["signals"] if "PENDING" not in s["result"]][-5:]
    history=""
    if recent:
        history="\n📋 *5 Trade Terakhir:*\n"
        for t in reversed(recent):
            icon="✅" if "WIN" in t["result"] else "❌"
            pips=f"{'+' if 'WIN' in t['result'] else '-'}{abs(t['pnl_pips']):.1f}"
            history+=f"   {icon} {t['direction']} | {pips} pips | {t['close_time']}\n"

    return (
        f"📓 *APEX FIB JOURNAL — {SYMBOL}*\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{run_txt}\n"
        f"📊 *Statistik:*\n"
        f"   Total   : {total} sinyal\n"
        f"   WIN     : {win} ✅  (+{s['pips_win']:.1f} pips)\n"
        f"   LOSS    : {loss} ❌  (-{s['pips_loss']:.1f} pips)\n"
        f"   Pending : {pending} ⏳\n"
        f"   Winrate : *{wr}%*\n"
        f"   Net P&L : *{'+' if net>=0 else ''}{net} pips*\n"
        f"{history}\n"
        f"_/journal /status_"
    )


# ═══════════════════════════════════════════════════════════════
# 7. TELEGRAM
# ═══════════════════════════════════════════════════════════════
def send_telegram(msg):
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload={"chat_id":TELEGRAM_CHAT_ID,"text":msg,"parse_mode":"Markdown"}
    try:
        r=requests.post(url,json=payload,timeout=10)
        if r.status_code!=200: log.error(f"Telegram error: {r.text}")
    except Exception as e: log.error(f"Send error: {e}")

def check_commands(journal):
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r=requests.get(url,timeout=5); data=r.json()
        if not data.get("ok"): return
        for upd in data.get("result",[])[-5:]:
            txt=upd.get("message",{}).get("text","").strip()
            if txt=="/journal":
                send_telegram(get_stats_message(journal))
            elif txt=="/status":
                t=get_running_trade(journal)
                if t:
                    send_telegram(
                        f"⏳ *Trade Running:*\n\n"
                        f"Arah   : *{t['direction']}*\n"
                        f"Trend  : {t['trend']}\n"
                        f"61.8%  : {t['fib_618']:.2f}\n"
                        f"Entry  : {t['entry']:.2f}\n"
                        f"SL     : {t['sl']:.2f}\n"
                        f"TP     : {t['tp']:.2f}\n"
                        f"Waktu  : {t['time']}\n\n"
                        f"_Bot tidak entry baru sampai selesai._"
                    )
                else:
                    send_telegram("✅ Tidak ada trade running.\nBot siap mencari sinyal baru.")
    except: pass


# ═══════════════════════════════════════════════════════════════
# 8. MAIN LOOP
# ═══════════════════════════════════════════════════════════════
journal    = load_journal()
loop_count = 0
sent_cache = set()

def run_bot():
    global loop_count, journal

    log.info("🚀 APEX Fibonacci Bot mulai...")
    send_telegram(
        f"🚀 *APEX Fibonacci Bot Aktif!*\n\n"
        f"*Pair      :* {SYMBOL}\n"
        f"*Timeframe :* H1 Only\n\n"
        f"*Strategi:*\n"
        f"〽️ EMA 200 → tentukan trend\n"
        f"📈 Trend Bullish → cari setup BUY 61.8% only\n"
        f"📉 Trend Bearish → cari setup SELL 61.8% only\n"
        f"📐 SL = di atas/bawah Swing A\n"
        f"✅ TP = minimal 1:{int(MIN_RR)} dari SL\n\n"
        f"*Commands:*\n"
        f"/journal → statistik\n"
        f"/status  → trade running\n\n"
        f"_Memantau 24 jam..._ 👁️"
    )

    while True:
        try:
            loop_count += 1

            if loop_count % 5   == 0: check_commands(journal)
            if loop_count % 180 == 0 and journal["stats"]["total"] > 0:
                send_telegram(get_stats_message(journal))

            # ── Ambil data H1
            df = get_candles(250)
            if df is None or len(df) < EMA_PERIOD + 10:
                log.warning("Data tidak cukup untuk EMA200")
                time.sleep(CHECK_INTERVAL); continue

            # ── Update hasil trade pending
            journal = update_results(journal, df)

            # ── Blok jika ada trade running
            if has_running_trade(journal):
                running = get_running_trade(journal)
                log.info(f"Trade running: {running['direction']} "
                         f"Entry:{running['entry']:.2f} — skip")
                time.sleep(CHECK_INTERVAL); continue

            # ── Step 1: Cek Trend via EMA 200
            trend, ema200 = get_trend(df)
            price = df["close"].iloc[-1]
            log.info(f"Trend: {trend} | EMA200: {ema200:.2f} | Harga: {price:.2f}")

            if trend == "NEUTRAL":
                log.info("Trend NEUTRAL — skip")
                time.sleep(CHECK_INTERVAL); continue

            # ── Step 2: Cari setup Fibonacci 61.8% sesuai trend
            setup = detect_fib_setup(df, trend)

            if setup is None:
                log.info(f"Tidak ada setup 61.8% untuk trend {trend}")
                time.sleep(CHECK_INTERVAL); continue

            # ── Hindari duplikat
            key = f"{setup['direction']}_{setup['fib_618']}_{setup['swing_A']['price']}"
            if key in sent_cache:
                log.info("Setup sudah dikirim — skip")
                time.sleep(CHECK_INTERVAL); continue

            entry_price = df["close"].iloc[-1]
            log.info(f"✅ Setup: {setup['direction']} | "
                     f"Trend: {trend} | EMA200: {ema200:.2f} | "
                     f"Fib 61.8% = {setup['fib_618']}")

            # ── Step 3: Kirim notif Telegram
            msg = format_signal(setup, ema200, entry_price)
            send_telegram(msg)

            # ── Step 4: Catat journal
            sig_id = f"{datetime.now().strftime('%Y%m%d%H%M')}_{setup['direction'][:4]}"
            log_to_journal(journal, sig_id, setup, entry_price)

            sent_cache.add(key)
            if len(sent_cache) > 100: sent_cache.clear()

        except Exception as e:
            log.error(f"Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()
