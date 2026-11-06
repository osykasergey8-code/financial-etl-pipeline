#!/bin/bash
python3 -m venv venv 2>/dev/null || python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python pipeline.py
