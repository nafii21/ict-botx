# 🤖 Forex Signal Bot — IRL/ERL + MSS Strategy

Bot Telegram untuk sinyal trading **XAUUSD** dan **NASDAQ** dengan strategi IRL/ERL + MSS konfirmasi di M15 & H1.

---

## 📦 Stack (All Free)
| Tool | Fungsi |
|------|--------|
| **TwelveData** | Market data API (free tier: 800 req/day) |
| **python-telegram-bot** | Telegram bot framework |
| **Railway** | Deploy & hosting (free tier) |
| **GitHub** | Source code & auto-deploy |

---

## 🚀 Setup Step-by-Step

### 1. Buat Telegram Bot
1. Chat ke [@BotFather](https://t.me/BotFather) di Telegram
2. Ketik `/newbot` → kasih nama bot lo
3. Copy **TOKEN** yang dikasih BotFather
4. Dapetin **CHAT_ID** lo: chat ke [@userinfobot](https://t.me/userinfobot)

### 2. Dapet API Key TwelveData
1. Daftar di [twelvedata.com](https://twelvedata.com)
2. Masuk ke dashboard → copy **API Key**
3. Free tier: **800 requests/day** (cukup buat scan tiap 15 menit)

### 3. Push ke GitHub
```bash
git init
git add .
git commit -m "initial bot"
git branch -M main
git remote add origin https://github.com/USERNAME/forex-bot.git
git push -u origin main
```

### 4. Deploy ke Railway
1. Buka [railway.app](https://railway.app) → login pakai GitHub
2. Klik **New Project** → **Deploy from GitHub repo**
3. Pilih repo `forex-bot` lo
4. Masuk ke tab **Variables**, tambahkan:

| Variable | Value |
|----------|-------|
| `TELEGRAM_TOKEN` | token dari BotFather |
| `CHAT_ID` | chat ID lo |
| `TWELVEDATA_KEY` | API key TwelveData |

5. Railway otomatis build & deploy dari Dockerfile ✅

---

## 📲 Commands Bot

| Command | Fungsi |
|---------|--------|
| `/stats` | Win rate semua pair |
| `/stats XAUUSD` | Stats khusus XAUUSD |
| `/stats NDX/USD` | Stats khusus NASDAQ |
| `/win 3` | Tandai trade #3 sebagai WIN |
| `/loss 3` | Tandai trade #3 sebagai LOSS |
| `/be 3` | Tandai trade #3 sebagai Breakeven |
| `/recent` | 5 sinyal terbaru + statusnya |

---

## 📊 Format Sinyal

```
🥇 XAU/USD | 🟢 BUY
━━━━━━━━━━━━━━━━
📍 Entry: 2345.50
🛑 SL:    2338.20
🎯 TP:    2367.80
━━━━━━━━━━━━━━━━
📊 RR: 1:3.0
🕐 TF: M15 + H1
🧠 Setup: IRL/ERL + MSS
⏰ 2025-01-15 14:30 UTC
```

---

## 🧠 Cara Kerja Strategi

```
H1 → Identifikasi IRL/ERL
   ↓
   Tentukan BIAS (Bullish/Bearish)
   ↓
M15 → Tunggu MSS konfirmasi sesuai bias
   ↓
   Entry di close candle MSS
   SL di bawah/atas swing terdekat
   TP di ERL target (swing high/low)
   ↓
   Minimum RR 1:1.5 (kalau kurang, sinyal diskip)
```

---

## 📁 Struktur File

```
forex-bot/
├── bot.py          # Main scheduler & notif
├── strategy.py     # Logic IRL/ERL + MSS
├── journal.py      # Trade logging & stats
├── commands.py     # Telegram command handlers
├── requirements.txt
├── Dockerfile
└── journal.csv     # Auto-dibuat saat pertama jalan
```

---

## ⚠️ Catatan Penting

- Bot scan otomatis **tiap 15 menit** (Senin-Jumat, 00:00–22:00 UTC)
- TwelveData free tier: **800 req/day** → scan 2 pair x 2 timeframe = 4 req per scan → **~200 scan/day** (lebih dari cukup)
- Journal disimpan di `journal.csv` di dalam Railway container
- **Update hasil trade manual** lewat command `/win`, `/loss`, `/be` + nomor trade ID
- Railway free tier: 500 jam/bulan (cukup untuk 1 bot)

---

## 🔄 Update Bot

Push ke GitHub → Railway otomatis redeploy. Sesimple itu! ✅
