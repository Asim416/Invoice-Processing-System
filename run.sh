#!/usr/bin/env bash
# One-command start for macOS / Linux:  bash run.sh
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  echo "First run: setting up (takes a minute)..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi
[ -f ".env" ] || { cp .env.example .env; echo "Created .env (demo mode)."; }
[ -f "data/pos.csv" ] || .venv/bin/python scripts/generate_data.py
.venv/bin/python -m ap.doctor || true
echo "Opening the app. Close this window (or press Ctrl+C) to stop it."
exec .venv/bin/python -m streamlit run app.py
