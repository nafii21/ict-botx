import aiohttp
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TWELVEDATA_BASE = "https://api.twelvedata.com"

# Symbol mapping untuk TwelveData
SYMBOL_MAP = {
    "XAU/USD": "XAU/USD",
    "NDX/USD": "NDX",
}

async def fetch_candles(symbol: str, interval: str, api_key: str, outputsize: int = 100) -> list:
    """Fetch OHLC candles dari TwelveData."""
    mapped = SYMBOL_MAP.get(symbol, symbol)
    url = f"{TWELVEDATA_BASE}/time_series"
    params = {
        "symbol": mapped,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            if "values" not in data:
                logger.warning(f"No data for {symbol} {interval}: {data.get('message', 'unknown error')}")
                return []
            candles = data["values"]
            # Return as list of dict dengan float values, urutan dari lama ke baru
            return [
                {
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "datetime": c["datetime"]
                }
                for c in reversed(candles)
            ]

def find_swing_highs_lows(candles: list, lookback: int = 5) -> dict:
    """Identifikasi swing highs dan swing lows."""
    highs = []
    lows = []

    for i in range(lookback, len(candles) - lookback):
        window_highs = [candles[j]["high"] for j in range(i - lookback, i + lookback + 1)]
        window_lows = [candles[j]["low"] for j in range(i - lookback, i + lookback + 1)]

        if candles[i]["high"] == max(window_highs):
            highs.append({"index": i, "price": candles[i]["high"], "datetime": candles[i]["datetime"]})

        if candles[i]["low"] == min(window_lows):
            lows.append({"index": i, "price": candles[i]["low"], "datetime": candles[i]["datetime"]})

    return {"highs": highs, "lows": lows}

def identify_irl_erl(swings: dict, candles: list) -> dict:
    """
    IRL (Internal Range Liquidity): liquidity inside the range (FVG, order blocks).
    ERL (External Range Liquidity): liquidity beyond swing highs/lows (stop hunts).
    
    Return ERL levels (swing high/low yang belum di-sweep) dan bias.
    """
    highs = swings["highs"]
    lows = swings["lows"]
    current_price = candles[-1]["close"]

    if not highs or not lows:
        return {"bias": None, "erl_high": None, "erl_low": None}

    # ERL High = highest unswept swing high
    # ERL Low = lowest unswept swing low
    recent_highs = sorted(highs[-5:], key=lambda x: x["price"], reverse=True)
    recent_lows = sorted(lows[-5:], key=lambda x: x["price"])

    erl_high = recent_highs[0]["price"] if recent_highs else None
    erl_low = recent_lows[0]["price"] if recent_lows else None

    # Bias: jika harga lebih dekat ke ERL Low → bias bullish (target ERL High)
    #        jika harga lebih dekat ke ERL High → bias bearish (target ERL Low)
    bias = None
    if erl_high and erl_low:
        dist_to_high = abs(current_price - erl_high)
        dist_to_low = abs(current_price - erl_low)
        if dist_to_low < dist_to_high:
            bias = "BULLISH"
        else:
            bias = "BEARISH"

    return {"bias": bias, "erl_high": erl_high, "erl_low": erl_low, "current": current_price}

def detect_mss(candles: list, bias: str) -> Optional[dict]:
    """
    Market Structure Shift (MSS):
    - BULLISH MSS: setelah lower low, harga break di atas previous swing high (BOS bullish)
    - BEARISH MSS: setelah higher high, harga break di bawah previous swing low (BOS bearish)
    
    Return MSS candle jika terdeteksi di 3 candle terakhir.
    """
    if len(candles) < 10:
        return None

    recent = candles[-10:]
    last_candle = recent[-1]

    if bias == "BULLISH":
        # Cari previous swing high dalam 10 candle terakhir
        prev_highs = [c["high"] for c in recent[:-3]]
        if not prev_highs:
            return None
        last_swing_high = max(prev_highs)

        # MSS konfirmasi: close candle terakhir di atas previous swing high
        if last_candle["close"] > last_swing_high:
            return {
                "confirmed": True,
                "direction": "BUY",
                "mss_level": last_swing_high,
                "candle": last_candle
            }

    elif bias == "BEARISH":
        prev_lows = [c["low"] for c in recent[:-3]]
        if not prev_lows:
            return None
        last_swing_low = min(prev_lows)

        if last_candle["close"] < last_swing_low:
            return {
                "confirmed": True,
                "direction": "SELL",
                "mss_level": last_swing_low,
                "candle": last_candle
            }

    return None

def calculate_entry_sl_tp(direction: str, candles_m15: list, irl_erl: dict) -> Optional[dict]:
    """
    Hitung Entry, SL, TP berdasarkan arah dan struktur.
    Entry: current close (market order / konfirmasi candle close)
    SL: below/above recent swing (IRL level)
    TP: ERL target
    """
    last = candles_m15[-1]
    entry = round(last["close"], 5)

    # Cari recent swing untuk SL
    recent_lows = [c["low"] for c in candles_m15[-10:]]
    recent_highs = [c["high"] for c in candles_m15[-10:]]

    if direction == "BUY":
        sl = round(min(recent_lows) * 0.9998, 5)  # sedikit buffer
        tp = round(irl_erl["erl_high"] * 0.9999, 5) if irl_erl["erl_high"] else round(entry * 1.003, 5)
    else:
        sl = round(max(recent_highs) * 1.0002, 5)
        tp = round(irl_erl["erl_low"] * 1.0001, 5) if irl_erl["erl_low"] else round(entry * 0.997, 5)

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 1) if risk > 0 else 0

    # Minimum RR 1:1.5
    if rr < 1.5:
        return None

    return {"entry": entry, "sl": sl, "tp": tp, "rr": rr}

async def analyze_pair(pair: str, api_key: str) -> Optional[dict]:
    """
    Main analysis: gabungin H1 (bias/ERL) + M15 (MSS + entry).
    """
    logger.info(f"📊 Analyzing {pair}...")

    # Fetch candles H1 dan M15 secara parallel
    h1_candles, m15_candles = await asyncio.gather(
        fetch_candles(pair, "1h", api_key, 100),
        fetch_candles(pair, "15min", api_key, 100)
    )

    if not h1_candles or not m15_candles:
        logger.warning(f"⚠️ Insufficient data for {pair}")
        return None

    # H1: Tentukan bias lewat IRL/ERL
    h1_swings = find_swing_highs_lows(h1_candles, lookback=5)
    irl_erl = identify_irl_erl(h1_swings, h1_candles)

    if not irl_erl["bias"]:
        logger.info(f"⚖️ No clear bias for {pair}")
        return None

    logger.info(f"🧭 {pair} Bias: {irl_erl['bias']} | ERL High: {irl_erl['erl_high']} | ERL Low: {irl_erl['erl_low']}")

    # M15: Detect MSS sesuai bias
    mss = detect_mss(m15_candles, irl_erl["bias"])

    if not mss or not mss["confirmed"]:
        logger.info(f"⏳ No MSS confirmation for {pair}")
        return None

    logger.info(f"✅ MSS confirmed for {pair}: {mss['direction']}")

    # Hitung Entry, SL, TP
    levels = calculate_entry_sl_tp(mss["direction"], m15_candles, irl_erl)

    if not levels:
        logger.info(f"⚠️ RR tidak memenuhi minimum untuk {pair}")
        return None

    return {
        "pair": pair,
        "direction": mss["direction"],
        "entry": levels["entry"],
        "sl": levels["sl"],
        "tp": levels["tp"],
        "rr": levels["rr"],
        "bias": irl_erl["bias"],
        "datetime": m15_candles[-1]["datetime"]
    }
