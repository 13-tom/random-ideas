@echo off
REM One-click launcher for the Clipper Studio GUI (Windows).
REM Double-click this file — it sets up a virtual environment on first run,
REM then opens the app every time after.
cd /d "%~dp0"

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ffmpeg not found. Install it first: winget install ffmpeg
    pause
    exit /b 1
)

if not exist ".venv" (
    echo First run: setting up a local Python environment ^(this can take
    echo several minutes -- it downloads the free captioning model dependencies^)...
    python -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\python -m pip install -r requirements.txt
    .venv\Scripts\python -m pip install -r gui\requirements-gui.txt
    echo Setup complete.
)

.venv\Scripts\python gui\app.py
pause
