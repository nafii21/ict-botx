import os
import time
import requests
import pandas as pd
import csv
from datetime import datetime

# ==========================================
# 1. KONFIGURASI API (Dari Environment Railway)
# ==========================================
TWELVEDATA_API_KEY = os.environ.get("64d9b87e7c5a4d4f8e625ec95da13b0f")
TELEGRAM_BOT_TOKEN = os.environ.get("8919806833:AAHJZdzA0qwsky2862y062MJskK7kLmIG24")
TELEGRAM_CHAT_ID = os.environ.get("6273206309")

SYMBOL = "NDX" # Simbol Nasdaq
INTERVAL = "15min" # Timeframe

# ==========================================
# 2. FUNGSI AMBIL DATA (TWELVE DATA)
# ==========================================
def get_data():
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&apikey={TWELVEDATA_API_KEY}&outputsize=100"
    try:
        response = requests.get(url).json()
        if "values" not in response:
            print("Error ngambil data:", response)
            return None

        # Convert ke Pandas DataFrame & urutin dari data terlama ke terbaru
        df = pd.DataFrame(response['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.astype({'open': float, 'high': float, 'low': float, 'close': float})
        df = df.sort_values('datetime').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Koneksi error ngab: {e}")
        return None

# ==========================================
# 3. LOGIKA STRATEGI FRACTAL ERL -> IRL (FVG)
# ==========================================
def check_strategy(df):
    # a. Deteksi Fractal 5-Candle untuk Swing High & Swing Low
    # Swing divalidasi di candle ke i-2 (tengah dari 5 candle)
    df['Swing_High'] = (df['high'].shift(2) > df['high'].shift(1)) & \
                       (df['high'].shift(2) > df['high']) & \
                       (df['high'].shift(2) > df['high'].shift(3)) & \
                       (df['high'].shift(2) > df['high'].shift(4))
                       
    df['Swing_Low'] = (df['low'].shift(2) < df['low'].shift(1)) & \
                      (df['low'].shift(2) < df['low']) & \
                      (df['low'].shift(2) < df['low'].shift(3)) & \
                      (df['low'].shift(2) < df['low'].shift(4))

    # b. Tarik garis ERL dari Swing terakhir yang valid (Forward Fill)
    df['ERL_High'] = df['high'].shift(2).where(df['Swing_High']).ffill()
    df['ERL_Low'] = df['low'].shift(2).where(df['Swing_Low']).ffill()

    # Kita pake 3 candle terakhir buat ngecek konfirmasi Sweep + FVG
    c1 = df.iloc[-3]
    c2 = df.iloc[-2] # Candle yang biasanya nge-sweep
    c3 = df.iloc[-1] # Candle yang baru aja close (konfirmasi FVG)

    # Ambil level ERL sebelum 3 candle ini terbentuk biar fair
    current_erl_high = df['ERL_High'].iloc[-4]
    current_erl_low = df['ERL_Low'].iloc[-4]

    signal = None
    reason = ""

    # --- LOGIKA BUY ---
    # 1. Harga nge-sweep ERL Low (Bisa dari ekor candle c2 atau c3)
    sweep_low = (c2['low'] < current_erl_low) or (c3['low'] < current_erl_low)
    # 2. Terbentuk Bullish FVG (Low C3 > High C1)
    bullish_fvg = c3['low'] > c1['high'] 
    
    if sweep_low and bullish_fvg:
        signal = "BUY"
        reason = "Sweep ERL Low & Valid Bullish IRL (FVG)"

    # --- LOGIKA SELL ---
    # 1. Harga nge-sweep ERL High
    sweep_high = (c2['high'] > current_erl_high) or (c3['high'] > current_erl_high)
    # 2. Terbentuk Bearish FVG (High C3 < Low C1)
    bearish_fvg = c3['high'] < c1['low']

    if sweep_high and bearish_fvg:
        signal = "SELL"
        reason = "Sweep ERL High & Valid Bearish IRL (FVG)"

    # --- KALKULASI TP & SL ---
    if signal:
        entry_price = c3['close']
        
        # Stop loss ditaruh di ujung ekor candle sweep
        if signal == "BUY":
            sl = min(c2['low'], c3['low']) - 2.0 # Kasih buffer dikit 2 point
        else:
            sl = max(c2['high'], c3['high']) + 2.0 
            
        risk = abs(entry_price - sl)
        tp = entry_price + (risk * 2) if signal == "BUY" else entry_price - (risk * 2)

        return {
            "action": signal,
            "price": round(entry_price, 2),
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "reason": reason,
            "time": str(c3['datetime'])
        }
    return None

# ==========================================
# 4. FUNGSI NOTIFIKASI & JOURNALING
# ==========================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Gagal ngirim tele:", e)

def write_journal(trade_data):
    # Path diarahin ke folder volume Railway biar file gak ilang pas restart
    journal_path = "/app/data/journal.csv"
    
    # Kalo lu test di lokal (laptop), file bakal nyimpen di folder yang sama
    if not os.path.exists("/app/data"):
        journal_path = "journal.csv"

    file_exists = os.path.isfile(journal_path)
    
    try:
        with open(journal_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            if not file_exists:
                # Bikin header kalo file baru pertama kali dibuat
                writer.writerow(["Time", "Action", "Entry Price", "Stop Loss", "Take Profit", "Reason"]) 
            writer.writerow([trade_data['time'], trade_data['action'], trade_data['price'], trade_data['sl'], trade_data['tp'], trade_data['reason']])
    except Exception as e:
        print("Gagal nulis jurnal:", e)

# ==========================================
# 5. MAIN LOOP SCHEDULER
# ==========================================
def main():
    print("🚀 Bot udah jalan ngab! Mantau market...")
    while True:
        # Cek menit sekarang
        current_minute = datetime.now().minute
        current_second = datetime.now().second
        
        # Eksekusi persis pas candle M15 close (menit 0, 15, 30, 45) + delay 2 detik biar data 12Data update
        if current_minute % 15 == 0 and current_second == 2:
            print(f"[{datetime.now()}] Ngecek formasi candle terakhir...")
            df = get_data()
            
            if df is not None:
                trade_signal = check_strategy(df)
                
                if trade_signal:
                    msg = f"🚨 **SIGNAL {SYMBOL}** 🚨\n\n" \
                          f"**Action:** {trade_signal['action']} 🟢\n" \
                          f"**Entry:** {trade_signal['price']}\n" \
                          f"**TP:** {trade_signal['tp']}\n" \
                          f"**SL:** {trade_signal['sl']}\n\n" \
                          f"💡 *Logic:* {trade_signal['reason']}"
                    
                    send_telegram(msg)
                    write_journal(trade_signal)
                    print(f"💰 Sinyal {trade_signal['action']} ke-trigger & dikirim ke Tele!")
            
            # Tidur 60 detik biar gak kepanggil double di menit yang sama
            time.sleep(60) 
        else:
            # Pengecekan dilakuin tiap 1 detik
            time.sleep(1)

if __name__ == "__main__":
    main()
