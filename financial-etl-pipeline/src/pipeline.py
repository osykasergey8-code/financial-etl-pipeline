"""
Automated Financial Data ETL Pipeline
----------------------------------------
Fetches live exchange rate data from a public API, validates and cleans it,
and loads it into a structured PostgreSQL/SQLite warehouse for reporting.

Designed to run unattended via Cron with structured logging, so a finance
team never has to manually download or reformat rate data again.

Author: Sergey O.
Stack: Python, Requests, Pandas, SQLite/PostgreSQL, Cron
"""

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("etl_pipeline.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Config is read from environment variables so credentials/paths never need
# to be hardcoded or committed. Sensible defaults keep `python src/pipeline.py`
# working out of the box with no .env file present.
API_URL = os.environ.get("ETL_API_URL", "https://open.er-api.com/v6/latest/USD")
DB_PATH = os.environ.get("ETL_DB_PATH", "financial_warehouse.db")
TARGET_CURRENCIES = os.environ.get(
    "ETL_TARGET_CURRENCIES", "EUR,GBP,CAD,JPY,CHF,AUD"
).split(",")
REQUEST_TIMEOUT = int(os.environ.get("ETL_REQUEST_TIMEOUT", "10"))


@dataclass
class PipelineResult:
    rows_fetched: int = 0
    rows_loaded: int = 0
    rows_rejected: int = 0
    errors: list = field(default_factory=list)


def fetch_exchange_rates() -> Optional[dict]:
    """Call the exchange rate API and return the raw JSON payload.

    Returns None (and logs why) on any network failure, non-2xx status,
    non-JSON body, or an API-level failure result — callers only ever
    need to check for None, never guess which failure mode occurred.
    """
    try:
        response = requests.get(API_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error("API request failed: %s", e)
        return None

    try:
        payload = response.json()
    except ValueError as e:
        logger.error("API returned non-JSON response: %s", e)
        return None

    if not isinstance(payload, dict):
        logger.error("API returned unexpected payload shape: %r", type(payload))
        return None

    if payload.get("result") != "success":
        logger.error("API returned non-success result: %s", payload.get("result"))
        return None

    if not isinstance(payload.get("rates"), dict):
        logger.error("API payload missing a valid 'rates' object")
        return None

    return payload


def transform(payload: dict) -> pd.DataFrame:
    """Filter to target currencies, validate values, and structure as a DataFrame.

    Any currency with a missing, non-numeric, or non-positive rate is kept
    in the output but flagged is_valid=False, so nothing is silently guessed.
    """
    rates = payload.get("rates", {})
    updated_at = payload.get(
        "time_last_update_utc", datetime.now(timezone.utc).isoformat()
    )

    records = []
    for currency in TARGET_CURRENCIES:
        rate = rates.get(currency)
        is_valid = isinstance(rate, (int, float)) and not isinstance(rate, bool) and rate > 0

        records.append(
            {
                "base_currency": "USD",
                "target_currency": currency,
                "rate": rate if is_valid else None,
                "is_valid": is_valid,
                "source_updated_at": updated_at,
                "loaded_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    return pd.DataFrame(records)


def load_to_warehouse(df: pd.DataFrame) -> tuple[int, int]:
    """Write validated rows to SQLite. Rejects and logs any row that failed validation."""
    valid_df = df[df["is_valid"]].drop(columns=["is_valid"])
    rejected_df = df[~df["is_valid"]]

    if not rejected_df.empty:
        for _, row in rejected_df.iterrows():
            logger.warning(
                "Rejected row — missing/invalid rate for %s", row["target_currency"]
            )

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS currency_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_currency TEXT NOT NULL,
                target_currency TEXT NOT NULL,
                rate REAL NOT NULL,
                source_updated_at TEXT,
                loaded_at TEXT NOT NULL
            )
            """
        )
        valid_df.to_sql("currency_rates", conn, if_exists="append", index=False)

    return len(valid_df), len(rejected_df)


def run_pipeline() -> PipelineResult:
    result = PipelineResult()

    payload = fetch_exchange_rates()
    if payload is None:
        result.errors.append("API fetch failed — pipeline aborted")
        return result

    df = transform(payload)
    result.rows_fetched = len(df)

    loaded, rejected = load_to_warehouse(df)
    result.rows_loaded = loaded
    result.rows_rejected = rejected

    return result


if __name__ == "__main__":
    logger.info("Starting financial ETL pipeline run")
    result = run_pipeline()

    if result.errors:
        logger.error("Pipeline finished with errors: %s", result.errors)
    else:
        logger.info(
            "Pipeline completed successfully. Fetched: %d | Loaded: %d | Rejected: %d",
            result.rows_fetched,
            result.rows_loaded,
            result.rows_rejected,
        )
