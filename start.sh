#!/usr/bin/env bash
cd "$(dirname "$0")"

# Create virtualenv if not present
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
fi

echo "Starting AICTE APAAR Server at http://127.0.0.1:8000 ..."
./venv/bin/python3 run.py
