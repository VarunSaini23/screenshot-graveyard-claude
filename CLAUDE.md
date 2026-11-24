# Screenshot Graveyard: instructions for the agent

This repo sorts a folder of screenshots into piles, finds duplicates and junk, and makes everything searchable, all in a local web app. The person you're helping has probably never used a terminal. Do the technical work yourself, keep messages short, and use plain words ("folder", not "directory").

## Ground rules (never break these)

1. **Never move, rename or delete the user's original screenshots.** The app only reads them. Exports are copies, and junk goes to `_Trash` inside the output folder, only after the user clicks the button.
2. **Keep their screenshots private.** Never commit anything from `~/.screenshot-graveyard/`, an output folder, or a screenshots folder.
3. No paid APIs. Claude is optional and only used through the user's own `claude` CLI.
4. All text the user sees is plain English. One question at a time.

## When someone gives you this repo's link (the usual case)

They pasted something like "Set up and open https://github.com/VarunSaini23/screenshot-graveyard-claude". Do this without asking:

1. **Download it.** If you're not already inside this repo:
   - macOS / Linux: `git clone https://github.com/VarunSaini23/screenshot-graveyard-claude.git ~/screenshot-graveyard` (if that folder exists, `git -C ~/screenshot-graveyard pull` instead).
   - Windows: the same, into `%USERPROFILE%\screenshot-graveyard`.
   Then work from that folder.
2. **Check Python 3.11+**: `python3 --version` (Windows: `py -3 --version`).
   - Mac without it: if `brew` exists, run `brew install python@3.12`. Otherwise ask them to install it from python.org and wait.
   - Windows without it: `winget install Python.Python.3.12`.
3. **OCR engine**
   - macOS: nothing to do (it uses Apple Vision).
   - Windows: if `tesseract` isn't on PATH and `C:\Program Files\Tesseract-OCR\tesseract.exe` doesn't exist, run `winget install UB-Mannheim.TesseractOCR`.
   - Linux: `sudo apt install tesseract-ocr` (ask first).
4. **Start it in the background** (it keeps running):
   - macOS / Linux: `./run.sh` (if it says permission denied: `bash run.sh`)
   - Windows: `powershell -ExecutionPolicy Bypass -File .\run.ps1`
   The first run installs packages, which takes a few minutes. Wait until it prints the address, then make sure the page is open in their browser (http://localhost:8765, or the port it printed if 8765 was busy).
5. **Tell them, in about three lines:**
   - It's open in their browser.
   - Paste or pick their screenshots folder, click **Scan folder**, then **Start sorting**. The first sort downloads a ~600 MB image model once.
   - To open it again later: double-click **Open Screenshot Graveyard** in the `screenshot-graveyard` folder in their home folder, or ask you to "open screenshot graveyard".
6. Stay available. Answer questions from what the app shows and from `GET /api/summary` and `GET /api/status`.

If their screenshots are still on their phone:
- **iPhone → Mac:** Photos → Albums → Screenshots, select all, drag to a new folder.
- **iPhone → Windows:** plug in, then Photos → Import, or copy from `This PC → Apple iPhone → DCIM`.
- **Android:** plug in over USB (File transfer) and copy `Pictures/Screenshots` or `DCIM/Screenshots`.
Never read `Photos Library.photoslibrary` directly.

## Claude mode

The app uses the user's own `claude` CLI for screenshots it isn't sure about, sending only short text snippets, never images. The badge in the top-right says whether it's on. If it says "Claude Code CLI not found", the app was started from a place where `claude` isn't on PATH: stop it and start it again from a terminal where `claude` works. `SG_CLAUDE=0` turns it off.

## If something breaks

- Port 8765 busy: the app picks the next free port and prints it.
- Already running: `./run.sh` just opens the page again.
- Install failed halfway: run the start command again; it continues.
- HEIC photos fail: `.venv/bin/pip install -U pillow-heif`.

## Development

- Tests: `.venv/bin/python -m pytest -q` (Windows: `.\.venv\Scripts\python -m pytest -q`). All tests must pass.
- Sample data: `python -m tools.make_samples samples --n 300` (also writes `samples-truth.json`).
- Backend: `app/` (FastAPI). Frontend: `web/` (vanilla HTML/CSS/JS, no build step).
