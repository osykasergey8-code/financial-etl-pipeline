@echo off
echo Financial ETL Pipeline - Quick Run
echo Creating venv...
python -m venv venv
call venv\Scripts\activate
echo Installing deps...
pip install -r requirements.txt
echo Running pipeline...
python pipeline.py
echo.
echo Done! Check data\financial_warehouse.db
pause
