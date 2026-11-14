
"""
Financial ETL Pipeline — Production Grade
Author: Sergey Osyka
Fetches live FX rates, validates (reject don't guess), loads to warehouse.

Run: python pipeline.py
"""
import os
import sys
import time
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import requests
from dotenv import load_dotenv
from notify import build_summary, send_telegram

load_dotenv()

# --- Config from .env ---
API_URL = os.getenv("API_URL", "https://open.er-api.com/v6/latest/USD")
BASE_CURRENCY = os.getenv("BASE_CURRENCY", "USD")
CURRENCIES_RAW = os.getenv("CURRENCIES", "EUR,GBP,CAD,JPY,CHF,AUD")
TARGET_CURRENCIES = [c.strip().upper() for c in CURRENCIES_RAW.split(",") if c.strip()]
DB_PATH = os.getenv("DB_PATH", "./data/financial_warehouse.db")
LOG_PATH = os.getenv("LOG_PATH", "./data/etl_pipeline.log")

# --- Logging ---
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("etl")

MAX_RETRIES = 3
TIMEOUT = 15

def fetch_rates() -> Dict[str, float]:
    """Extract: Fetch rates with retry + backoff. Returns rates dict."""
    last_err = None
    for attempt in range(1, MAX_RETRIES+1):
        try:
            log.info(f"Fetching {BASE_CURRENCY} base from {API_URL} (attempt {attempt}/{MAX_RETRIES})...")
            resp = requests.get(API_URL, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            # open.er-api.com format: {"result":"success","rates":{...}} or {"rates":...}
            rates = data.get("rates") or data.get("conversion_rates") or data
            if not isinstance(rates, dict):
                # handle nested
                if "rates" in data:
                    rates = data["rates"]
                else:
                    raise ValueError(f"Unexpected API format: {list(data.keys())[:5]}")
            log.info(f"Got {len(rates)} currencies from API")
            return rates
        except Exception as e:
            last_err = e
            log.warning(f"Fetch failed: {e}, retrying in {attempt*2}s...")
            time.sleep(attempt*2)
    log.error(f"All fetch attempts failed: {last_err}")
    raise RuntimeError(f"Failed to fetch after {MAX_RETRIES} tries: {last_err}")

def transform_rates(all_rates: Dict[str, float]) -> Tuple[List[Dict], List[Dict]]:
    """
    Transform: Validate & filter.
    Returns (clean_rows, rejected_rows)
    Reject Don't Guess:
    - missing -> reject
    - zero / negative -> reject
    - non-numeric -> reject
    """
    clean = []
    rejected = []
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    for cur in TARGET_CURRENCIES:
        if cur == BASE_CURRENCY:
            continue
        if cur not in all_rates:
            rejected.append({"currency": cur, "reason": "missing", "raw": None})
            log.warning(f"Rejected {cur}: missing -> logged")
            continue
        raw = all_rates[cur]
        # validate numeric
        try:
            rate = float(raw)
        except Exception:
            rejected.append({"currency": cur, "reason": f"non-numeric ({raw})", "raw": raw})
            log.warning(f"Rejected {cur}: non-numeric {raw}")
            continue
        if rate == 0:
            rejected.append({"currency": cur, "reason": "zero", "raw": raw})
            log.warning(f"Rejected {cur}: zero value")
            continue
        if rate < 0:
            rejected.append({"currency": cur, "reason": "negative", "raw": raw})
            log.warning(f"Rejected {cur}: negative {raw}")
            continue
        if rate > 100000: # absurd spike protection
            rejected.append({"currency": cur, "reason": f"spike {rate}", "raw": raw})
            log.warning(f"Rejected {cur}: spike {rate}")
            continue

        clean.append({
            "date": today,
            "base_currency": BASE_CURRENCY,
            "target_currency": cur,
            "rate": rate,
            "fetched_at": now_iso,
            "source": API_URL
        })

    log.info(f"Transform: {len(clean)} clean, {len(rejected)} rejected")
    return clean, rejected

def load_rates(clean_rows: List[Dict]):
    """Load: SQLite warehouse with idempotent table creation."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS currency_rates (
        date TEXT NOT NULL,
        base_currency TEXT NOT NULL,
        target_currency TEXT NOT NULL,
        rate REAL NOT NULL,
        fetched_at TEXT NOT NULL,
        source TEXT,
        PRIMARY KEY (date, base_currency, target_currency)
    );
    """)
    # Create rejected log table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rejected_rates (
        date TEXT,
        base_currency TEXT,
        target_currency TEXT,
        reason TEXT,
        raw_value TEXT,
        logged_at TEXT
    );
    """)
    # Insert clean with REPLACE (upsert for same day)
    for r in clean_rows:
        cur.execute("""
        INSERT OR REPLACE INTO currency_rates
        (date, base_currency, target_currency, rate, fetched_at, source)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (r["date"], r["base_currency"], r["target_currency"], r["rate"], r["fetched_at"], r["source"]))
    
    conn.commit()
    # Verify
    cur.execute("SELECT COUNT(*) FROM currency_rates WHERE date = ?", (clean_rows[0]["date"] if clean_rows else "",))
    count = cur.fetchone()[0] if clean_rows else 0
    conn.close()
    log.info(f"✓ Loaded {len(clean_rows)} rows into currency_rates (total today: {count}) in {DB_PATH}")
    return count

def load_rejected(rejected_rows: List[Dict]):
    if not rejected_rows:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    for rej in rejected_rows:
        cur.execute("""
        INSERT INTO rejected_rates (date, base_currency, target_currency, reason, raw_value, logged_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (today, BASE_CURRENCY, rej["currency"], rej["reason"], str(rej["raw"]), now))
    conn.commit()
    conn.close()

def main():
    start = time.time()
    log.info("="*50)
    log.info(f"ETL START — Base={BASE_CURRENCY} Targets={TARGET_CURRENCIES}")
    try:
        all_rates = fetch_rates()
        clean, rejected = transform_rates(all_rates)
        if clean:
            load_rates(clean)
        load_rejected(rejected)
        elapsed = time.time() - start
        log.info(f"Done in {elapsed:.1f}s — warehouse ready at {DB_PATH}")
        send_telegram(build_summary(BASE_CURRENCY, clean, rejected, elapsed))
        # Pretty print table
        print("\n" + "="*60)
        print(f"CURRENCY RATES — {datetime.now().strftime('%Y-%m-%d')} | Base {BASE_CURRENCY}")
        print("="*60)
        for r in clean:
            print(f"{r['base_currency']} → {r['target_currency']}: {r['rate']}")
        if rejected:
            print("\nRejected (safe):")
            for rej in rejected:
                print(f"  {rej['currency']}: {rej['reason']}")
        print("="*60 + "\n")
    except Exception as e:
        log.exception(f"ETL FAILED: {e}")
        send_telegram(f"ETL FAILED: {type(e).__name__}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
