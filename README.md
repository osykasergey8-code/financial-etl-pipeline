# Financial ETL Pipeline

Automated daily pipeline that fetches live exchange rates from a public API, validates every value, and loads the clean data into a SQLite warehouse. Bad values are never guessed or patched: they are rejected and logged with the reason.

```
open.er-api.com  →  Fetch (3 retries + backoff)  →  Validate  →  SQLite warehouse
                                                      └─ rejected_rates table (with reason)
```

## Why it is useful

A finance or reporting team no longer downloads and reformats rate files by hand. The job runs unattended (cron, Docker or Task Scheduler), writes a structured log, and keeps a history of every day's rates.

## Features

- **Extract** from the free open.er-api.com API with timeouts, 3 retries and exponential backoff
- **Validate** each currency: missing, zero, negative, non-numeric and absurd spikes are rejected, not loaded
- **Load** with an idempotent upsert (one row per date, base and target currency), so reruns never create duplicates
- **Audit trail**: rejected values are stored in `rejected_rates` with the reason and timestamp
- **Configurable** through `.env`: pick any currency codes, change the database and log paths
- Docker image, Makefile and one-click run scripts for Linux, macOS and Windows
- Unit tests for the validation rules

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
python pipeline.py
```

Example output:

```
CURRENCY RATES — 2026-11-06 | Base USD
USD → EUR: 0.8742
USD → GBP: 0.7471
...
```

Check the warehouse:

```bash
sqlite3 ./data/financial_warehouse.db "SELECT * FROM currency_rates ORDER BY target_currency;"
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `API_URL` | `https://open.er-api.com/v6/latest/USD` | Rates source |
| `BASE_CURRENCY` | `USD` | Base currency |
| `CURRENCIES` | `EUR,GBP,CAD,JPY,CHF,AUD` | Currencies to keep |
| `DB_PATH` | `./data/financial_warehouse.db` | SQLite file |
| `LOG_PATH` | `./data/etl_pipeline.log` | Log file |

## Validation rules

| Case | Action |
|---|---|
| Currency missing from the API response | Reject and log |
| Value is 0 | Reject and log |
| Negative value | Reject and log |
| Non-numeric value | Reject and log |
| Value above 100,000 (spike protection) | Reject and log |
| Anything else | Load |

## Run on a schedule

Docker:

```bash
docker build -t financial-etl .
docker run --env-file .env financial-etl
```

Cron, every day at 07:00:

```
0 7 * * * cd /path/to/project && python pipeline.py
```

## PostgreSQL

The warehouse is SQLite by default. To load into PostgreSQL, replace the `sqlite3.connect(DB_PATH)` calls in `load_rates()` and `load_rejected()` with a `psycopg2` connection (and `%s` placeholders).

## Tests

```bash
pip install pytest
pytest -v
```

## Project structure

```
pipeline.py            extract, transform (validation), load
tests/test_transform.py  validation tests
.env.example           configuration template
Dockerfile, Makefile, run.sh, run.bat
```

## Stack

Python, requests, SQLite, python-dotenv, pytest, Docker

## License

See [LICENSE.txt](LICENSE.txt).

Author: Sergey Osyka. Need a custom data pipeline or scraper? Contact me on [Contra](https://contra.com/sergey_osyka_lw5bxb5o).
