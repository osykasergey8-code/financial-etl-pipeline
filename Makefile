run:
	python pipeline.py

install:
	pip install -r requirements.txt

test:
	pytest -v

docker:
	docker build -t financial-etl .
	docker run --env-file .env financial-etl

db:
	sqlite3 ./data/financial_warehouse.db "SELECT * FROM currency_rates ORDER BY target_currency;"
