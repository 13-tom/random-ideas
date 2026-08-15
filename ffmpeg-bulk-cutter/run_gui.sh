#!/usr/bin/env bash
# One-click launcher for the Clipper Studio GUI (Mac/Linux).
# Double-click this file (or run `./run_gui.sh` in a terminal) — it sets up
# a virtual environment on first run, then opens the app every time after.
set -e
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Install it first:"
  echo "  Mac:   brew install ffmpeg"
  echo "  Linux: sudo apt install ffmpeg"
  exit 1
fi

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"

if [ ! -d ".venv" ]; then
  echo "First run: setting up a local Python environment (this can take several"
  echo "minutes — it downloads the free captioning model dependencies)..."
  "$PYTHON_BIN" -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
  ./.venv/bin/pip install -r gui/requirements-gui.txt
  echo "Setup complete."
fi

./.venv/bin/python gui/app.py
