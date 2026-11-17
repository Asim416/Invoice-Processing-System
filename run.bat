@echo off
REM One-command start for Windows: double-click run.bat
cd /d "%~dp0"
if not exist ".venv" (
  echo First run: setting up, this takes a minute...
  python -m venv .venv
  if errorlevel 1 ( echo Python was not found. Install Python 3.10+ from python.org and tick "Add to PATH". & pause & exit /b 1 )
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
)
if not exist ".env" ( copy .env.example .env >nul & echo Created .env ^(demo mode^). )
if not exist "data\pos.csv" .venv\Scripts\python scripts\generate_data.py
.venv\Scripts\python -m ap.doctor
echo Opening the app. Close this window to stop it.
.venv\Scripts\python -m streamlit run app.py
pause
