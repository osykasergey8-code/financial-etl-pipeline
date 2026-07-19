"""
Unit tests for the ETL pipeline's transform() step.

Run with:
    pip install pytest
    pytest tests/
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pipeline  # noqa: E402


def test_valid_rates_are_marked_valid():
    payload = {
        "result": "success",
        "time_last_update_utc": "Tue, 14 Jul 2026 00:00:00 +0000",
        "rates": {c: 1.5 for c in pipeline.TARGET_CURRENCIES},
    }
    df = pipeline.transform(payload)

    assert len(df) == len(pipeline.TARGET_CURRENCIES)
    assert df["is_valid"].all()
    assert (df["rate"] == 1.5).all()


def test_missing_currency_is_rejected_not_guessed():
    payload = {
        "result": "success",
        "time_last_update_utc": "Tue, 14 Jul 2026 00:00:00 +0000",
        "rates": {},  # no currencies present at all
    }
    df = pipeline.transform(payload)

    assert len(df) == len(pipeline.TARGET_CURRENCIES)
    assert not df["is_valid"].any()
    assert df["rate"].isna().all()


def test_negative_and_zero_rates_are_rejected():
    rates = {c: -1 for c in pipeline.TARGET_CURRENCIES}
    if pipeline.TARGET_CURRENCIES:
        rates[pipeline.TARGET_CURRENCIES[0]] = 0

    payload = {"result": "success", "rates": rates}
    df = pipeline.transform(payload)

    assert not df["is_valid"].any()


def test_non_numeric_rate_is_rejected():
    rates = {c: "N/A" for c in pipeline.TARGET_CURRENCIES}
    payload = {"result": "success", "rates": rates}
    df = pipeline.transform(payload)

    assert not df["is_valid"].any()


def test_fetch_returns_none_on_missing_rates_key():
    # Simulates the API returning success but a malformed body.
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"result": "success"}  # no "rates" key at all

    original_get = pipeline.requests.get
    pipeline.requests.get = lambda *a, **k: FakeResponse()
    try:
        assert pipeline.fetch_exchange_rates() is None
    finally:
        pipeline.requests.get = original_get
