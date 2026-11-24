# Instructions for AI agents (Claude Code etc.)

When a user asks you to "set up and open" this repo:

1. **Check Python 3.11+**: run `python3 --version` (macOS/Linux) or `py -3 --version` (Windows). If it's missing, tell the user how to install it (`brew install python@3.12`, or python.org).
2. **OCR engine**
   - macOS: nothing to do (it uses Apple Vision).
   - Windows: if `tesseract` isn't on PATH and `C:\Program Files\Tesseract-OCR\tesseract.exe` doesn't exist, run `winget install UB-Mannheim.TesseractOCR`.
   - Linux: `sudo apt install tesseract-ocr` (ask the user first).
3. **Start it**: run `./run.sh` (macOS/Linux) or `powershell -ExecutionPolicy Bypass -File .\run.ps1` (Windows). It creates `.venv`, installs `requirements.txt`, and starts the server.
4. **Open** http://localhost:8765. If 8765 is busy, the app prints `Port 8765 is busy, so using N instead.`; open that port instead.
5. Tell the user: "Type or pick your screenshots folder and click **Scan folder**, then sort. The first sort downloads a ~600 MB image model once."

## Development

- Tests: `.venv/bin/python -m pytest -q` (Windows: `.\.venv\Scripts\python -m pytest -q`). All tests must pass.
- Sample data: `python tools/make_samples.py samples --n 300` (also writes `samples-truth.json`).
- Backend: `app/` (FastAPI). Frontend: `web/` (vanilla HTML/CSS/JS, no build step).
- Rules that must hold:
  - Never modify, move, or delete the user's original files. Export only copies, and send junk to `_Trash` inside the output folder.
  - All text the user sees is plain English.
  - No paid APIs. Claude is optional and only used through the user's own `claude` CLI.
