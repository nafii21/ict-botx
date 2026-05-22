import time, json, logging, os, requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════
#  APEX BOT — Liquidity Concept + Auto Execute MT5 via MetaAPI
#  Flow  : H1 Bias → M15 ERL/IRL → M15 Sweep
#          → M5 IFVG+MSS → Tunggu candle M5 close konfirmasi
#          → Execute MT5 (1 trade at a time)
# ═══════════════════════════════════════════════════════════════

TELEGRAM_TOKEN     = "8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24"
TELEGRAM_CHAT_ID   = "6273206309"
TWELVEDATA_API_KEY = "64d9b87e7c5a4d4f8e625ec95da13b0f"

META_API_TOKEN     = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJfaWQiOiI0ZGFhNDUxMWZmNDk5N2FmMWQxMzk5MTk5MDExZGE4ZiIsImFjY2Vzc1J1bGVzIjpbeyJpZCI6InRyYWRpbmctYWNjb3VudC1tYW5hZ2VtZW50LWFwaSIsIm1ldGhvZHMiOlsidHJhZGluZy1hY2NvdW50LW1hbmFnZW1lbnQtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiXSwicmVzb3VyY2VzIjpbImFjY291bnQ6JFVTRVJfSUQkOmNjMTIyMWM2LWY5YjAtNDg3OC04OWVkLWJhNzExM2Y2OGJjZSJdfSx7ImlkIjoibWV0YWFwaS1yZXN0LWFwaSIsIm1ldGhvZHMiOlsibWV0YWFwaS1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiYWNjb3VudDokVVNFUl9JRCQ6Y2MxMjIxYzYtZjliMC00ODc4LTg5ZWQtYmE3MTEzZjY4YmNlIl19LHsiaWQiOiJtZXRhYXBpLXJwYy1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOndzOnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyJhY2NvdW50OiRVU0VSX0lEJDpjYzEyMjFjNi1mOWIwLTQ4NzgtODllZC1iYTcxMTNmNjhiY2UiXX0seyJpZCI6Im1ldGFhcGktcmVhbC10aW1lLXN0cmVhbWluZy1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOndzOnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyJhY2NvdW50OiRVU0VSX0lEJDpjYzEyMjFjNi1mOWIwLTQ4NzgtODllZC1iYTcxMTNmNjhiY2UiXX0seyJpZCI6Im1ldGFzdGF0cy1hcGkiLCJtZXRob2RzIjpbIm1ldGFzdGF0cy1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciJdLCJyZXNvdXJjZXMiOlsiYWNjb3VudDokVVNFUl9JRCQ6Y2MxMjIxYzYtZjliMC00ODc4LTg5ZWQtYmE3MTEzZjY4YmNlIl19LHsiaWQiOiJyaXNrLW1hbmFnZW1lbnQtYXBpIiwibWV0aG9kcyI6WyJyaXNrLW1hbmFnZW1lbnQtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiXSwicmVzb3VyY2VzIjpbImFjY291bnQ6JFVTRVJfSUQkOmNjMTIyMWM2LWY5YjAtNDg3OC04OWVkLWJhNzExM2Y2OGJjZSJdfV0sImlnbm9yZVJhdGVMaW1pdHMiOmZhbHNlLCJ0b2tlbklkIjoiMjAyMTAyMTMiLCJpbXBlcnNvbmF0ZWQiOmZhbHNlLCJyZWFsVXNlcklkIjoiNGRhYTQ1MTFmZjQ5OTdhZjFkMTM5OTE5OTAxMWRhOGYiLCJpYXQiOjE3Nzk0MTIxMjAsImV4cCI6MTc4NzE4ODEyMH0.dNWSN41MclDkK4nMNxbdEv0UEO9G4WqYYTV543gCq22XuVQ2v819vAsJLYuyLALhkOKSUIpiUbvqgBdbH6ugeQZARxjDsNqdqyBosQgPP2lVPVgSJXQBJfTUo43waLZqugO-pbix7akIjGwdRufU2aaxmvgDBrIxOHsFv2YR7e2Dckv_iH48AGDj8_kWTTWrKVcDU_OITfzsrF6B0rvwt_Pv40-yyUpJ6xWQ1US4R8fgTwa7jY8yD7kjNbSd37o86xYYlFLrCnrKTZCWZsXYMGUGPpbgdwvEgo8EgG1Ewt2AR_7Se1PDDuTCesSMq6ntbF_kw-EU7kL3EbdvnTci-KaILcJ58EnBhCktX0sKOlp0DKSu2SOUb9e0uAZYZj1ubAK_mkZljgSmp-8xMQaF91G2Z1ygJeKnjIwfZfZR5QeEmUTpWUFcRA1UGXfigV3e-oAsJulKlZckzLNMOrejcbpqzRCcFK83kkXONy0_cvgLJiFK3rYw6WG7eS1jfQs3TK5S5Bf9aysR_QrR10L48rEzyM-SYc7gv1Uj-r1nL7K4HgZ3r87opLbKsTxZF6beTDyJbbgQPR8TnXjNmsjnVwuKcsRiurxCjhB4Qq8UJCWD4ccquQJ_fo-wWCFbGvc9oLZP2_aZF-SgzXFXMPRqJjBjxg9QRugh3rc8SFp_lC4"
META_ACCOUNT_ID    = "cc1221c6-f9b0-4878-89ed-ba7113f68bce"
META_API_URL       = "https://mt-client-api-v1.london.agiliumtrade.ai"

LOT_SIZE           = 0.01
SYMBOL_MT5         = "XAUUSD"
SYMBOL             = "XAU/USD"
TF_H1              = "1h"
TF_M15             = "15min"
TF_M5              = "5min"
CHECK_INTERVAL     = 60        # cek tiap 60 detik
JOURNAL_FILE       = "journal.json"
SL_BUFFER          = 0.5
MIN_RR             = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. AMBIL DATA CANDLE
# ═══════════════════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════════════════
# 2. H1 BIAS
# ═══════════════════════════════════════════════════════════════
def get_h1_bias(df_h1):
    if df_h1 is None or len(df_h1) < 20:
        return "NEUTRAL"
    h = df_h1["high"].values
    l = df_h1["low"].values
    c = df_h1["close"].values
    n = len(df_h1)
    swing_h, swing_l = [], []
    for i in range(2, n-2):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i+1] and h[i]>h[i+2]:
            swing_h.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i+1] and l[i]<l[i+2]:
            swing_l.append(l[i])
    if len(swing_h) >= 2 and len(swing_l) >= 2:
        if swing_h[-1]>swing_h[-2] and swing_l[-1]>swing_l[-2]: return "BULLISH"
        if swing_h[-1]<swing_h[-2] and swing_l[-1]<swing_l[-2]: return "BEARISH"
    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
    if c[-1]>ema50[-1] and ema50[-1]>ema50[-5]: return "BULLISH"
    if c[-1]<ema50[-1] and ema50[-1]<ema50[-5]: return "BEARISH"
    return "NEUTRAL"


# ═══════════════════════════════════════════════════════════════
# 3. MAPPING ERL & IRL di M15
# ═══════════════════════════════════════════════════════════════
def map_erl_irl(df_m15):
    h = df_m15["high"].values
    l = df_m15["low"].values
    c = df_m15["close"].values
    o = df_m15["open"].values
    n = len(df_m15)
    price = c[-1]
    erl, irl = [], []

    # ERL: Swing High/Low
    for i in range(3, n-3):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i-3] and \
           h[i]>h[i+1] and h[i]>h[i+2] and h[i]>h[i+3]:
            if not any(abs(e["level"]-h[i])<1.5 for e in erl):
                erl.append({"level":round(h[i],2),"type":"BSL (Swing High M15)","side":"BSL","idx":i})
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i-3] and \
           l[i]<l[i+1] and l[i]<l[i+2] and l[i]<l[i+3]:
            if not any(abs(e["level"]-l[i])<1.5 for e in erl):
                erl.append({"level":round(l[i],2),"type":"SSL (Swing Low M15)","side":"SSL","idx":i})

    # ERL: Equal Highs/Lows
    tol = 1.0
    for i in range(max(0,n-50), n-5):
        for j in range(i+4, min(i+20,n-1)):
            if abs(h[i]-h[j])<=tol:
                eq=round((h[i]+h[j])/2,2)
                if not any(abs(e["level"]-eq)<1.5 for e in erl):
                    erl.append({"level":eq,"type":"Equal Highs (BSL)","side":"BSL","idx":j})
                break
        for j in range(i+4, min(i+20,n-1)):
            if abs(l[i]-l[j])<=tol:
                eq=round((l[i]+l[j])/2,2)
                if not any(abs(e["level"]-eq)<1.5 for e in erl):
                    erl.append({"level":eq,"type":"Equal Lows (SSL)","side":"SSL","idx":j})
                break

    # ERL: Prev Session High/Low
    if n >= 50:
        sess = df_m15.iloc[-50:-8]
        ph   = round(sess["high"].max(),2)
        pl   = round(sess["low"].min(), 2)
        if not any(abs(e["level"]-ph)<1.5 for e in erl):
            erl.append({"level":ph,"type":"Prev Session High (BSL)","side":"BSL","idx":n-50})
        if not any(abs(e["level"]-pl)<1.5 for e in erl):
            erl.append({"level":pl,"type":"Prev Session Low (SSL)","side":"SSL","idx":n-50})

    # IRL: FVG M15
    for i in range(1, n-1):
        if l[i+1]>h[i-1]:
            flo,fhi=h[i-1],l[i+1]; mid=round((flo+fhi)/2,2)
            if not any(abs(ir["level"]-mid)<1.0 for ir in irl):
                irl.append({"level":mid,"zone_lo":round(flo,2),"zone_hi":round(fhi,2),
                            "type":"Bullish FVG (IRL)","dir":"BULLISH","idx":i})
        if h[i+1]<l[i-1]:
            fhi2,flo2=l[i-1],h[i+1]; mid2=round((flo2+fhi2)/2,2)
            if not any(abs(ir["level"]-mid2)<1.0 for ir in irl):
                irl.append({"level":mid2,"zone_lo":round(flo2,2),"zone_hi":round(fhi2,2),
                            "type":"Bearish FVG (IRL)","dir":"BEARISH","idx":i})

    # IRL: OB M15
    avg_body = np.mean([abs(c[i]-o[i]) for i in range(max(0,n-20),n)])+1e-9
    for i in range(max(0,n-20), n-2):
        body = abs(c[i]-o[i])
        if body < avg_body*1.1: continue
        mid_ob = round((h[i]+l[i])/2,2)
        if not any(abs(ir["level"]-mid_ob)<2.0 for ir in irl):
            if o[i]>c[i]:
                irl.append({"level":mid_ob,"zone_lo":round(l[i],2),"zone_hi":round(h[i],2),
                            "type":"Bullish OB (IRL)","dir":"BULLISH","idx":i})
            elif c[i]>o[i]:
                irl.append({"level":mid_ob,"zone_lo":round(l[i],2),"zone_hi":round(h[i],2),
                            "type":"Bearish OB (IRL)","dir":"BEARISH","idx":i})

    erl = [e for e in erl if abs(e["level"]-price)<=80]
    irl = [ir for ir in irl if abs(ir["level"]-price)<=80]
    return erl, irl


# ═══════════════════════════════════════════════════════════════
# 4. DETEKSI SWEEP ERL di M15
# ═══════════════════════════════════════════════════════════════
def detect_m15_sweep(df_m15, erl):
    sweeps = []
    n = len(df_m15)
    for lv in erl:
        level = lv["level"]
        side  = lv["side"]
        for i in range(max(1,n-4), n):
            row  = df_m15.iloc[i]
            prev = df_m15.iloc[i-1]
            if side=="BSL" and row["high"]>level and row["close"]<level and prev["close"]<=level:
                sweeps.append({
                    "lv_type":"BSL","lv_level":level,"side":"BSL","direction":"BEARISH","idx":i,
                    "wick_hi":round(row["high"],2),"wick_lo":round(row["low"],2),
                    "detail":f"M15 Sweep BSL *{lv['type']}* @ {level:.2f}"
                })
            elif side=="SSL" and row["low"]<level and row["close"]>level and prev["close"]>=level:
                sweeps.append({
                    "lv_type":"SSL","lv_level":level,"side":"SSL","direction":"BULLISH","idx":i,
                    "wick_hi":round(row["high"],2),"wick_lo":round(row["low"],2),
                    "detail":f"M15 Sweep SSL *{lv['type']}* @ {level:.2f}"
                })
    return sweeps


# ═══════════════════════════════════════════════════════════════
# 5. CEK IFVG + MSS DI M5
# ═══════════════════════════════════════════════════════════════
def find_m5_setup(df_m5, direction):
    """
    Cari IFVG dan MSS di M5.
    Return ifvg, mss — keduanya bisa None.
    """
    n       = len(df_m5)
    h       = df_m5["high"].values
    l       = df_m5["low"].values
    c       = df_m5["close"].values
    current = c[-1]
    ifvg    = None
    mss     = None

    # IFVG
    for i in range(max(1,n-40), n-1):
        if i+1 >= n: break
        if direction == "BEARISH":
            if l[i+1] > h[i-1]:
                flo, fhi = h[i-1], l[i+1]
                if flo <= current <= fhi:
                    ifvg = {"type":"IFVG","zone_lo":round(flo,2),"zone_hi":round(fhi,2),
                            "detail":f"M5 IFVG Bearish [{flo:.2f}–{fhi:.2f}]"}
                    break
        elif direction == "BULLISH":
            if h[i+1] < l[i-1]:
                fhi2, flo2 = l[i-1], h[i+1]
                if flo2 <= current <= fhi2:
                    ifvg = {"type":"IFVG","zone_lo":round(flo2,2),"zone_hi":round(fhi2,2),
                            "detail":f"M5 IFVG Bullish [{flo2:.2f}–{fhi2:.2f}]"}
                    break

    # MSS
    for i in range(3, n-3):
        is_sh = h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i+1] and h[i]>h[i+2]
        is_sl = l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i+1] and l[i]<l[i+2]
        if direction=="BEARISH" and is_sl:
            sw = l[i]
            if c[-2] >= sw and current < sw:
                mss = {"type":"MSS","level":round(sw,2),
                       "detail":f"M5 MSS Bearish — close {current:.2f} < {sw:.2f}"}
                break
        if direction=="BULLISH" and is_sh:
            sw = h[i]
            if c[-2] <= sw and current > sw:
                mss = {"type":"MSS","level":round(sw,2),
                       "detail":f"M5 MSS Bullish — close {current:.2f} > {sw:.2f}"}
                break

    return ifvg, mss


# ═══════════════════════════════════════════════════════════════
# 6. TUNGGU KONFIRMASI CANDLE M5 BERIKUTNYA
#    Setelah IFVG/MSS terdeteksi, tunggu candle M5 close
#    sebagai konfirmasi rejection di zona
# ═══════════════════════════════════════════════════════════════
def confirm_m5_candle(df_m5, direction, zone_lo, zone_hi):
    """
    Cek candle M5 terakhir (yang sudah close):
    - BEARISH: candle masuk zona IFVG dan close BEARISH (open > close)
               atau close di bawah zona
    - BULLISH: candle masuk zona IFVG dan close BULLISH (close > open)
               atau close di atas zona
    Return: True jika konfirmasi valid
    """
    # Ambil candle kedua dari belakang (candle yang sudah close)
    if len(df_m5) < 2:
        return False

    candle = df_m5.iloc[-2]  # candle yang sudah close
    o = candle["open"]
    c = candle["close"]
    h = candle["high"]
    l = candle["low"]

    if direction == "BEARISH":
        # Candle masuk zona dan close bearish (penolakan ke bawah dari IFVG)
        touched_zone = h >= zone_lo
        bearish_close = c < o
        closed_below_zone = c < zone_lo
        return touched_zone and (bearish_close or closed_below_zone)

    elif direction == "BULLISH":
        # Candle masuk zona dan close bullish (penolakan ke atas dari IFVG)
        touched_zone = l <= zone_hi
        bullish_close = c > o
        closed_above_zone = c > zone_hi
        return touched_zone and (bullish_close or closed_above_zone)

    return False


# ═══════════════════════════════════════════════════════════════
# 7. HITUNG SL & TP
# ═══════════════════════════════════════════════════════════════
def calc_sl_tp(sweep, entry_price, direction, irl):
    if direction == "BEARISH":
        sl   = round(sweep["wick_hi"] + SL_BUFFER, 2)
        risk = abs(sl - entry_price)
        tp_default = round(entry_price - risk * MIN_RR, 2)
        irl_targets = sorted(
            [ir for ir in irl if ir["level"] < entry_price - risk],
            key=lambda x: x["level"], reverse=True
        )
        if irl_targets:
            tp_irl = irl_targets[0]["zone_lo"]
            rr_irl = round(abs(entry_price - tp_irl) / risk, 1) if risk > 0 else 0
            if rr_irl >= MIN_RR:
                return sl, round(tp_irl,2), round(risk,2), rr_irl, irl_targets[0]["type"]
        return sl, tp_default, round(risk,2), MIN_RR, "1:2 Default"
    else:
        sl   = round(sweep["wick_lo"] - SL_BUFFER, 2)
        risk = abs(entry_price - sl)
        tp_default = round(entry_price + risk * MIN_RR, 2)
        irl_targets = sorted(
            [ir for ir in irl if ir["level"] > entry_price + risk],
            key=lambda x: x["level"]
        )
        if irl_targets:
            tp_irl = irl_targets[0]["zone_hi"]
            rr_irl = round(abs(tp_irl - entry_price) / risk, 1) if risk > 0 else 0
            if rr_irl >= MIN_RR:
                return sl, round(tp_irl,2), round(risk,2), rr_irl, irl_targets[0]["type"]
        return sl, tp_default, round(risk,2), MIN_RR, "1:2 Default"


# ═══════════════════════════════════════════════════════════════
# 8. CEK APAKAH ADA TRADE RUNNING
# ═══════════════════════════════════════════════════════════════
def has_running_trade(journal):
    """
    Return True jika masih ada trade PENDING di journal.
    Bot tidak akan buka trade baru selama ini True.
    """
    for sig in journal["signals"]:
        if "PENDING" in sig["result"]:
            return True
    return False


def get_running_trade(journal):
    """Ambil detail trade yang sedang running"""
    for sig in journal["signals"]:
        if "PENDING" in sig["result"]:
            return sig
    return None


# ═══════════════════════════════════════════════════════════════
# 9. EXECUTE ORDER KE MT5 VIA METAAPI
# ═══════════════════════════════════════════════════════════════
def execute_order(direction, sl, tp):
    url     = f"{META_API_URL}/users/current/accounts/{META_ACCOUNT_ID}/trade"
    headers = {"auth-token": META_API_TOKEN, "Content-Type": "application/json"}
    action  = "ORDER_TYPE_BUY" if direction=="BULLISH" else "ORDER_TYPE_SELL"
    payload = {
        "actionType": action,
        "symbol"    : SYMBOL_MT5,
        "volume"    : LOT_SIZE,
        "stopLoss"  : sl,
        "takeProfit": tp,
        "comment"   : "APEX Bot"
    }
    try:
        r    = requests.post(url, json=payload, headers=headers, timeout=15)
        data = r.json()
        if r.status_code in [200, 201]:
            order_id = data.get("orderId") or data.get("positionId") or "N/A"
            return True, str(order_id), "OK"
        else:
            msg = data.get("message") or str(data)
            return False, None, msg
    except Exception as e:
        return False, None, str(e)


def close_all_positions():
    url     = f"{META_API_URL}/users/current/accounts/{META_ACCOUNT_ID}/positions"
    headers = {"auth-token": META_API_TOKEN}
    try:
        r         = requests.get(url, headers=headers, timeout=10)
        positions = r.json()
        if not isinstance(positions, list): return 0
        for pos in positions:
            pos_id = pos.get("id")
            requests.delete(
                f"{META_API_URL}/users/current/accounts/{META_ACCOUNT_ID}/positions/{pos_id}",
                headers=headers,
                json={"actionType":"POSITION_CLOSE_ID","positionId":pos_id},
                timeout=10
            )
        return len(positions)
    except Exception as e:
        log.error(f"Close error: {e}"); return 0


def get_account_info():
    url     = f"{META_API_URL}/users/current/accounts/{META_ACCOUNT_ID}/account-information"
    headers = {"auth-token": META_API_TOKEN}
    try:
        return requests.get(url, headers=headers, timeout=10).json()
    except:
        return None


# ═══════════════════════════════════════════════════════════════
# 10. SCORING
# ═══════════════════════════════════════════════════════════════
def calc_score(sweep, ifvg, mss, bias, rr):
    score = 0
    if ifvg and mss: score += 4
    elif ifvg:       score += 2
    elif mss:        score += 2
    lv = sweep["lv_type"]
    if "Equal" in lv:  score += 3
    elif "Prev" in lv: score += 3
    elif "Swing" in lv:score += 2
    else:              score += 1
    direction = sweep["direction"]
    if (direction=="BEARISH" and bias=="BEARISH") or \
       (direction=="BULLISH" and bias=="BULLISH"): score += 2
    elif bias=="NEUTRAL": score += 1
    if rr >= 3.0:   score += 2
    elif rr >= 2.0: score += 1
    return score


# ═══════════════════════════════════════════════════════════════
# 11. FORMAT PESAN
# ═══════════════════════════════════════════════════════════════
def format_signal(sweep, ifvg, mss, sl, tp, risk, rr, tp_type,
                  bias, score, order_id, entry_price):
    now       = datetime.now().strftime("%Y-%m-%d %H:%M")
    direction = sweep["direction"]
    dir_lbl   = "SELL 📉" if direction=="BEARISH" else "BUY 📈"

    if score>=9:   emoji,strength="🚨","🔥 SANGAT KUAT"
    elif score>=7: emoji,strength="📣","💪 KUAT"
    elif score>=5: emoji,strength="📊","✅ SEDANG"
    else:          emoji,strength="💡","⚡ LEMAH"

    entry_conf = []
    if ifvg: entry_conf.append(f"   ✅ {ifvg['detail']}")
    if mss:  entry_conf.append(f"   ✅ {mss['detail']}")

    lines = [
        f"{emoji} *APEX SIGNAL — {SYMBOL}*",
        f"🕐 {now}  |  H1→M15→M5",
        f"",
        f"🎯 Sinyal    : *{dir_lbl}*",
        f"💪 Kekuatan  : *{strength}* (Score: {score})",
        f"📈 H1 Bias   : *{bias}*",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"🔍 *SETUP:*",
        f"   🔸 Sweep M15 : {sweep['detail']}",
        f"      Wick      : {sweep['wick_lo']:.2f} — {sweep['wick_hi']:.2f}",
        f"   🔸 Konfirmasi M5:",
        *entry_conf,
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📐 *MANAJEMEN RISIKO:*",
        f"   • Lot    : *{LOT_SIZE}*",
        f"   • Entry  : *{entry_price:.2f}*",
        f"   • SL     : *{sl:.2f}*  ← wick M15 + {SL_BUFFER}",
        f"   • TP     : *{tp:.2f}*  ← {tp_type}",
        f"   • Risk   : {risk:.1f} pips",
        f"   • R:R    : *1:{rr}* ✅",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━",
    ]

    if order_id:
        lines += [
            f"🤖 *AUTO EXECUTE MT5:*",
            f"   ✅ Order tereksekusi!",
            f"   📋 Order ID : `{order_id}`",
            f"   🔒 SL & TP otomatis terpasang",
            f"",
            f"_⏸ Bot tidak akan entry baru sampai trade ini selesai._",
        ]
    else:
        lines += [
            f"⚠️ *AUTO EXECUTE GAGAL!*",
            f"   Silakan entry manual di MT5.",
            f"",
            f"_⏸ Bot tetap memantau TP/SL untuk journal._",
        ]

    lines.append(f"_📓 Dicatat di journal otomatis._")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 12. AUTO JOURNAL
# ═══════════════════════════════════════════════════════════════
def load_journal():
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE,"r") as f: return json.load(f)
        except: pass
    return {"signals":[],"stats":{
        "total":0,"win":0,"loss":0,"pending":0,
        "total_pips_win":0.0,"total_pips_loss":0.0
    }}

def save_journal(j):
    with open(JOURNAL_FILE,"w") as f: json.dump(j,f,indent=2)

def log_to_journal(journal, sig_id, sweep, entry, sl, tp,
                   risk, rr, ifvg, mss, bias, score, order_id):
    et = []
    if ifvg: et.append("IFVG")
    if mss:  et.append("MSS")
    journal["signals"].append({
        "id"        : sig_id,
        "time"      : datetime.now().strftime("%Y-%m-%d %H:%M"),
        "direction" : sweep["direction"],
        "sweep_type": sweep["lv_type"],
        "entry_type": "+".join(et),
        "entry"     : entry, "sl":sl, "tp":tp,
        "risk_pips" : risk,  "rr":rr,
        "bias"      : bias,  "score":score,
        "order_id"  : order_id or "manual",
        "result"    : "PENDING ⏳",
        "pnl_pips"  : 0.0,
        "close_time": ""
    })
    journal["stats"]["total"]   += 1
    journal["stats"]["pending"] += 1
    save_journal(journal)

def update_results(journal, df_m5):
    hi = df_m5["high"].iloc[-1]
    lo = df_m5["low"].iloc[-1]
    updated = False
    for sig in journal["signals"]:
        if "PENDING" not in sig["result"]: continue
        d=sig["direction"]; tp=sig["tp"]; sl=sig["sl"]
        entry=sig["entry"]; risk=abs(entry-sl)
        result=None; pnl=0.0
        if d=="BEARISH":
            if lo<=tp:
                result="WIN ✅"; pnl=round(entry-tp,2)
                journal["stats"]["win"]+=1; journal["stats"]["total_pips_win"]+=pnl
            elif hi>=sl:
                result="LOSS ❌"; pnl=round(entry-sl,2)
                journal["stats"]["loss"]+=1; journal["stats"]["total_pips_loss"]+=abs(pnl)
        else:
            if hi>=tp:
                result="WIN ✅"; pnl=round(tp-entry,2)
                journal["stats"]["win"]+=1; journal["stats"]["total_pips_win"]+=pnl
            elif lo<=sl:
                result="LOSS ❌"; pnl=round(sl-entry,2)
                journal["stats"]["loss"]+=1; journal["stats"]["total_pips_loss"]+=abs(pnl)
        if result:
            sig["result"]=result; sig["pnl_pips"]=pnl
            sig["close_time"]=datetime.now().strftime("%Y-%m-%d %H:%M")
            journal["stats"]["pending"]-=1
            updated=True
            send_result_notif(sig)
    if updated: save_journal(journal)
    return journal

def send_result_notif(sig):
    won   = "WIN" in sig["result"]
    emoji = "✅" if won else "❌"
    pnl   = abs(sig["pnl_pips"])
    rr_a  = round(pnl/sig["risk_pips"],1) if sig["risk_pips"]>0 else 0
    msg = (
        f"{emoji} *TRADE SELESAI — {SYMBOL}*\n\n"
        f"🎯 Arah    : *{sig['direction']}*\n"
        f"📋 Setup   : {sig['entry_type']} | {sig['sweep_type']}\n"
        f"📈 Bias H1 : {sig['bias']}\n\n"
        f"💰 Entry   : {sig['entry']:.2f}\n"
        f"{'✅ TP' if won else '❌ SL'}    : {sig['tp'] if won else sig['sl']:.2f}\n\n"
        f"📊 Hasil   : *{'+' if won else '-'}{pnl:.1f} pips*\n"
        f"📐 R:R     : *1:{rr_a}*\n"
        f"🕐 Buka    : {sig['time']}\n"
        f"🕐 Tutup   : {sig['close_time']}\n\n"
        f"🟢 *Bot siap mencari sinyal berikutnya!*\n"
        f"_📓 Ketik /journal untuk statistik._"
    )
    send_telegram(msg)

def get_stats_message(journal):
    s=journal["stats"]; total=s["total"]; win=s["win"]; loss=s["loss"]
    pending=s["pending"]; closed=total-pending
    wr=round(win/closed*100,1) if closed>0 else 0
    net=round(s["total_pips_win"]-s["total_pips_loss"],1)
    breakdown={}
    for sig in journal["signals"]:
        t=sig["sweep_type"]
        if t not in breakdown: breakdown[t]={"w":0,"l":0}
        if "WIN"  in sig["result"]: breakdown[t]["w"]+=1
        if "LOSS" in sig["result"]: breakdown[t]["l"]+=1
    bdown="\n".join([
        f"   • {k}: {v['w']}W/{v['l']}L ({round(v['w']/max(v['w']+v['l'],1)*100)}%)"
        for k,v in sorted(breakdown.items(),key=lambda x:-(x[1]['w']+x[1]['l']))
        if v['w']+v['l']>0
    ]) or "   Belum ada data"

    running = get_running_trade(journal)
    run_txt = ""
    if running:
        run_txt = (
            f"\n⏳ *Trade Running:*\n"
            f"   {running['direction']} | Entry:{running['entry']:.2f} "
            f"SL:{running['sl']:.2f} TP:{running['tp']:.2f}\n"
        )

    return (
        f"📓 *APEX JOURNAL — {SYMBOL}*\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{run_txt}\n"
        f"📊 *Statistik:*\n"
        f"   Total   : {total} sinyal\n"
        f"   WIN     : {win} ✅  (+{s['total_pips_win']:.1f} pips)\n"
        f"   LOSS    : {loss} ❌  (-{s['total_pips_loss']:.1f} pips)\n"
        f"   Pending : {pending} ⏳\n"
        f"   Winrate : *{wr}%*\n"
        f"   Net P&L : *{'+' if net>=0 else ''}{net} pips*\n\n"
        f"📈 *Per Sweep Type:*\n{bdown}\n\n"
        f"_/journal /status /account /closeall_"
    )


# ═══════════════════════════════════════════════════════════════
# 13. TELEGRAM
# ═══════════════════════════════════════════════════════════════
def send_telegram(msg):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id":TELEGRAM_CHAT_ID,"text":msg,"parse_mode":"Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200: log.error(f"Telegram error: {r.text}")
    except Exception as e: log.error(f"Send error: {e}")

def check_commands(journal):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
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
                        f"Entry  : {t['entry']:.2f}\n"
                        f"SL     : {t['sl']:.2f}\n"
                        f"TP     : {t['tp']:.2f}\n"
                        f"Setup  : {t['entry_type']} | {t['sweep_type']}\n"
                        f"Waktu  : {t['time']}\n\n"
                        f"_Bot tidak akan entry baru sampai selesai._"
                    )
                else:
                    send_telegram("✅ Tidak ada trade running.\nBot siap mencari sinyal.")
            elif txt=="/account":
                info=get_account_info()
                if info:
                    send_telegram(
                        f"💰 *Info Akun MT5*\n\n"
                        f"Balance : ${info.get('balance',0):.2f}\n"
                        f"Equity  : ${info.get('equity',0):.2f}\n"
                        f"Lot     : {LOT_SIZE}"
                    )
            elif txt=="/closeall":
                send_telegram("⚠️ Menutup semua posisi...")
                n=close_all_positions()
                send_telegram(f"✅ {n} posisi ditutup.")
    except: pass


# ═══════════════════════════════════════════════════════════════
# 14. STATE: PENDING SETUP
#     Simpan setup yang menunggu konfirmasi candle M5
# ═══════════════════════════════════════════════════════════════
pending_setup = None  # setup yang menunggu konfirmasi candle M5 berikutnya


# ═══════════════════════════════════════════════════════════════
# 15. MAIN LOOP
# ═══════════════════════════════════════════════════════════════
journal    = load_journal()
loop_count = 0

def run_bot():
    global loop_count, journal, pending_setup

    log.info("🚀 APEX Bot mulai...")
    info = get_account_info()
    if info and "balance" in info:
        send_telegram(
            f"🚀 *APEX Bot Aktif + MT5 Terkoneksi!*\n\n"
            f"💰 Balance : ${info.get('balance',0):.2f}\n"
            f"📊 Equity  : ${info.get('equity',0):.2f}\n"
            f"📦 Lot     : {LOT_SIZE} per trade\n\n"
            f"*Flow:*\n"
            f"H1 Bias → M15 Sweep (ERL)\n"
            f"→ M5 IFVG+MSS\n"
            f"→ Tunggu konfirmasi candle M5\n"
            f"→ Execute MT5 (1 trade at a time)\n\n"
            f"*Commands:*\n"
            f"/journal → statistik\n"
            f"/status  → trade running\n"
            f"/account → info akun\n"
            f"/closeall → tutup semua ‼️\n\n"
            f"_Memantau 24 jam..._ 👁️"
        )
    else:
        send_telegram(
            f"🚀 *APEX Bot Aktif*\n"
            f"⚠️ MetaAPI belum terkoneksi!\n"
            f"Cek META_API_TOKEN dan META_ACCOUNT_ID."
        )

    while True:
        try:
            loop_count += 1
            if loop_count % 5  == 0: check_commands(journal)
            if loop_count % 180== 0 and journal["stats"]["total"]>0:
                send_telegram(get_stats_message(journal))

            # Ambil data
            df_h1  = get_candles(TF_H1,  100)
            df_m15 = get_candles(TF_M15, 100)
            df_m5  = get_candles(TF_M5,  100)

            if any(df is None for df in [df_h1, df_m15, df_m5]):
                time.sleep(CHECK_INTERVAL); continue
            if any(len(df)<20 for df in [df_h1, df_m15, df_m5]):
                time.sleep(CHECK_INTERVAL); continue

            # Update hasil trade pending
            journal = update_results(journal, df_m5)

            # ── BLOK: Jika ada trade running, skip cari sinyal baru ──
            if has_running_trade(journal):
                running = get_running_trade(journal)
                log.info(f"Trade masih running: {running['direction']} "
                         f"Entry:{running['entry']:.2f} — skip sinyal baru")
                time.sleep(CHECK_INTERVAL); continue

            # ── STEP A: Cek apakah ada pending setup menunggu konfirmasi M5 ──
            if pending_setup is not None:
                ps        = pending_setup
                direction = ps["sweep"]["direction"]
                zone_lo   = ps["ifvg"]["zone_lo"] if ps["ifvg"] else ps["mss"]["level"] - 1
                zone_hi   = ps["ifvg"]["zone_hi"] if ps["ifvg"] else ps["mss"]["level"] + 1

                confirmed = confirm_m5_candle(df_m5, direction, zone_lo, zone_hi)

                if confirmed:
                    log.info("✅ Konfirmasi candle M5 valid — execute order!")
                    entry_price = df_m5["close"].iloc[-2]  # harga close candle konfirmasi
                    sweep = ps["sweep"]
                    ifvg  = ps["ifvg"]
                    mss   = ps["mss"]
                    irl   = ps["irl"]
                    bias  = ps["bias"]
                    score = ps["score"]

                    sl, tp, risk, rr, tp_type = calc_sl_tp(sweep, entry_price, direction, irl)

                    if rr >= MIN_RR:
                        success, order_id, exec_msg = execute_order(direction, sl, tp)
                        msg = format_signal(sweep, ifvg, mss, sl, tp, risk, rr,
                                            tp_type, bias, score, order_id, entry_price)
                        send_telegram(msg)

                        sig_id = f"{datetime.now().strftime('%Y%m%d%H%M')}_{direction[:4]}"
                        log_to_journal(journal, sig_id, sweep, entry_price,
                                       sl, tp, risk, rr, ifvg, mss, bias, score, order_id)
                        log.info(f"✅ Executed: {direction} | RR:{rr} | OrderID:{order_id}")
                    else:
                        log.info(f"RR {rr} < {MIN_RR} setelah konfirmasi — skip")
                        send_telegram(
                            f"⚠️ Setup dibatalkan — RR {rr} < {MIN_RR} setelah konfirmasi candle M5."
                        )

                    pending_setup = None  # reset

                else:
                    # Candle M5 tidak konfirmasi — batalkan setup
                    log.info("❌ Candle M5 tidak konfirmasi — setup dibatalkan")
                    pending_setup = None

                time.sleep(CHECK_INTERVAL); continue

            # ── STEP B: Cari sinyal baru ──────────────────────────────────
            bias = get_h1_bias(df_h1)
            log.info(f"H1 Bias: {bias}")

            erl, irl = map_erl_irl(df_m15)
            if not erl:
                log.info("Tidak ada ERL level")
                time.sleep(CHECK_INTERVAL); continue

            sweeps = detect_m15_sweep(df_m15, erl)
            if not sweeps:
                log.info("Tidak ada sweep M15")
                time.sleep(CHECK_INTERVAL); continue

            for sweep in sweeps:
                direction = sweep["direction"]

                # Skip jika bias berlawanan
                if bias != "NEUTRAL":
                    if direction=="BEARISH" and bias=="BULLISH": continue
                    if direction=="BULLISH" and bias=="BEARISH": continue

                # Cek IFVG + MSS di M5
                ifvg, mss = find_m5_setup(df_m5, direction)
                if not ifvg and not mss:
                    log.info(f"Tidak ada IFVG/MSS M5 — skip")
                    continue

                # Hitung score & RR sementara
                entry_est = df_m5["close"].iloc[-1]
                sl_est, tp_est, risk_est, rr_est, _ = calc_sl_tp(sweep, entry_est, direction, irl)
                if rr_est < MIN_RR:
                    log.info(f"RR estimasi {rr_est} < {MIN_RR} — skip"); continue

                score = calc_score(sweep, ifvg, mss, bias, rr_est)

                # Simpan sebagai pending setup — tunggu konfirmasi candle M5 berikutnya
                key = f"{direction}_{sweep['lv_level']}"
                if pending_setup is None:
                    pending_setup = {
                        "sweep": sweep, "ifvg": ifvg, "mss": mss,
                        "irl"  : irl,   "bias": bias, "score": score,
                        "key"  : key
                    }
                    log.info(f"⏳ Setup terdeteksi: {direction} | {sweep['lv_type']} "
                             f"— menunggu konfirmasi candle M5...")
                    send_telegram(
                        f"⏳ *Setup Terdeteksi — Menunggu Konfirmasi M5*\n\n"
                        f"🎯 Arah   : *{'SELL 📉' if direction=='BEARISH' else 'BUY 📈'}*\n"
                        f"🔸 Sweep  : {sweep['detail']}\n"
                        f"🔸 M5     : {ifvg['detail'] if ifvg else ''} "
                        f"{mss['detail'] if mss else ''}\n\n"
                        f"_Menunggu konfirmasi candle M5 berikutnya..._"
                    )
                    break  # tunggu 1 setup dulu

        except Exception as e:
            log.error(f"Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_bot()
