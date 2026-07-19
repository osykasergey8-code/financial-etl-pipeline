# Financial Data ETL Pipeline

Automated Python ETL pipeline that fetches live currency exchange rates from a public API, validates and cleans the data, and loads it into a structured SQLite/PostgreSQL warehouse — designed to replace a manual daily spreadsheet-download routine.

## Features

- Extracts live exchange rate data from a public REST API
- Validates every rate before loading (rejects missing/malformed values instead of silently inserting bad data)
- Loads only validated rows into a structured warehouse table, with full logging of rejected rows
- Runs unattended via Cron — no manual downloads or reformatting
- Structured logging (console + file) for monitoring scheduled runs
- Configurable via environment variables — no hardcoded paths or credentials

## Tech Stack

Python · Requests · Pandas · SQLite (swappable for PostgreSQL) · Cron · Docker

## How it works

1. **Extract** — calls the exchange rate API and pulls the latest rates
2. **Transform** — filters to the currencies the business actually tracks, flags any missing or invalid rate as rejected instead of guessing a value
3. **Load** — writes only valid rows to the `currency_rates` table in the warehouse; rejected rows are logged with the reason, not silently dropped

This "reject, don't guess" validation step is the difference between a pipeline that's safe to plug into financial reporting and one that quietly corrupts a report with a null or malformed value.

## Setup

```bash
pip install -r requirements.txt
python src/pipeline.py
```

## Configuration

Configuration is read from environment variables, with safe defaults so the pipeline runs out of the box with no setup. To override:

```bash
cp .env.example .env
# edit .env, then export it before running, e.g.:
export $(cat .env | xargs)
python src/pipeline.py
```

| Variable                 | Default                                     | Purpose                          |
|--------------------------|----------------------------------------------|-----------------------------------|
| `ETL_API_URL`            | `https://open.er-api.com/v6/latest/USD`      | Exchange rate API endpoint       |
| `ETL_DB_PATH`            | `financial_warehouse.db`                     | SQLite file path                 |
| `ETL_TARGET_CURRENCIES`  | `EUR,GBP,CAD,JPY,CHF,AUD`                    | Comma-separated currencies to track |
| `ETL_REQUEST_TIMEOUT`    | `10`                                          | API request timeout in seconds   |

## Running on a schedule

```bash
0 7 * * * /usr/bin/python3 /path/to/financial-etl-pipeline/src/pipeline.py
```

## Running with Docker

```bash
docker build -t financial-etl-pipeline .
docker run --rm --env-file .env financial-etl-pipeline
```

Note: the container writes `financial_warehouse.db` and `etl_pipeline.log` inside `/app`. Mount a volume if you need them to persist on the host:

```bash
docker run --rm --env-file .env -v $(pwd)/data:/app financial-etl-pipeline
```

## Switching to PostgreSQL

The pipeline uses SQLite by default for simplicity. To point it at PostgreSQL, replace the `sqlite3.connect(...)` calls in `src/pipeline.py` with a `psycopg2` or `SQLAlchemy` connection — the transform/validation logic stays identical, only the load step changes.

## Testing

```bash
pip install pytest
pytest tests/
```

Tests cover the `transform()` validation logic: valid rates, missing currencies, zero/negative rates, and non-numeric values are all confirmed to be rejected rather than silently accepted. `fetch_exchange_rates()` is covered for the case where the API returns a 200 with a malformed body (no `rates` key).

## Project structure

```
financial-etl-pipeline/
├── src/
│   └── pipeline.py       # main ETL logic
├── tests/
│   └── test_pipeline.py  # unit tests for validation logic
├── logs/                 # runtime logs (gitignored)
├── .env.example          # environment variable template
├── Dockerfile
├── requirements.txt
└── README.md
```

## License

MIT
