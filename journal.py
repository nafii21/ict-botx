import csv
import os
from datetime import datetime
from typing import Optional

JOURNAL_FILE = "journal.csv"
FIELDNAMES = ["id", "datetime", "pair", "direction", "entry", "sl", "tp", "rr", "result", "pnl_pips", "notes"]

def _init_journal():
    if not os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()

def _get_next_id() -> int:
    _init_journal()
    with open(JOURNAL_FILE, "r") as f:
        rows = list(csv.DictReader(f))
    return len(rows) + 1

def save_trade(signal: dict) -> int:
    """Simpan sinyal baru ke journal dengan status PENDING."""
    _init_journal()
    trade_id = _get_next_id()
    row = {
        "id": trade_id,
        "datetime": signal.get("datetime", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
        "pair": signal["pair"],
        "direction": signal["direction"],
        "entry": signal["entry"],
        "sl": signal["sl"],
        "tp": signal["tp"],
        "rr": signal["rr"],
        "result": "PENDING",
        "pnl_pips": "",
        "notes": ""
    }
    with open(JOURNAL_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(row)
    return trade_id

def update_trade_result(trade_id: int, result: str, pnl_pips: Optional[float] = None, notes: str = "") -> bool:
    """
    Update hasil trade: WIN / LOSS / BE (breakeven).
    result: 'WIN' | 'LOSS' | 'BE'
    """
    _init_journal()
    rows = []
    updated = False

    with open(JOURNAL_FILE, "r") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        if int(row["id"]) == trade_id:
            row["result"] = result.upper()
            row["pnl_pips"] = pnl_pips if pnl_pips is not None else ""
            row["notes"] = notes
            updated = True
            break

    if updated:
        with open(JOURNAL_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    return updated

def get_stats(pair: Optional[str] = None) -> dict:
    """Hitung statistik win rate dari journal."""
    _init_journal()

    with open(JOURNAL_FILE, "r") as f:
        rows = list(csv.DictReader(f))

    if pair:
        rows = [r for r in rows if r["pair"] == pair]

    closed = [r for r in rows if r["result"] in ("WIN", "LOSS", "BE")]
    wins = [r for r in closed if r["result"] == "WIN"]
    losses = [r for r in closed if r["result"] == "LOSS"]
    be = [r for r in closed if r["result"] == "BE"]
    pending = [r for r in rows if r["result"] == "PENDING"]

    total_closed = len(closed)
    win_rate = round((len(wins) / total_closed * 100), 1) if total_closed > 0 else 0.0

    return {
        "total": len(rows),
        "closed": total_closed,
        "win": len(wins),
        "loss": len(losses),
        "be": len(be),
        "pending": len(pending),
        "win_rate": win_rate
    }

def get_recent_trades(limit: int = 10) -> list:
    """Ambil N trade terbaru."""
    _init_journal()
    with open(JOURNAL_FILE, "r") as f:
        rows = list(csv.DictReader(f))
    return rows[-limit:]

def get_all_trades() -> list:
    _init_journal()
    with open(JOURNAL_FILE, "r") as f:
        return list(csv.DictReader(f))
