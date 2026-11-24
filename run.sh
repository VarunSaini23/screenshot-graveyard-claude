#!/usr/bin/env bash
# Screenshot Graveyard: one-command setup and start (macOS / Linux).
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11 or newer is required."
  echo "Install it with:  brew install python@3.12   (or download from https://www.python.org/downloads/)"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating a virtual environment..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f .venv/.deps-ok ] || [ requirements.txt -nt .venv/.deps-ok ]; then
  echo "Installing requirements (first run takes a few minutes)..."
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r requirements.txt
  touch .venv/.deps-ok
fi

if [ "$(uname)" != "Darwin" ] && ! command -v tesseract >/dev/null 2>&1; then
  echo "Note: Tesseract OCR isn't installed, so text inside screenshots can't be read."
  echo "      Install it with: sudo apt install tesseract-ocr   (or your package manager)"
fi

echo "The image model (~600 MB) downloads once, the first time it's needed."
exec python -m app
