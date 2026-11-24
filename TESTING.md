# Testing report: Screenshot Graveyard

**Tested on:** Windows 11, Python 3.11, Tesseract 5 (UB-Mannheim build), OpenCLIP ViT-B-32, Chromium-based browser (the app's built-in browser canvas).
**Test data:** synthetic but realistic screenshots made with `tools/make_samples.py`, covering every category, plus duplicates, resized and recompressed copies, HEIC/JPG/PNG files, and a ground-truth JSON for scoring:
- `samples300`: 338 images (284 PNG, 48 JPG, 6 HEIC)
- `samples2000`: 2,208 images

Legend: ✅ pass · ⚠️ partly tested / see note · ❌ not done (reason given)

## Automated tests

Run with `.\.venv\Scripts\python -m pytest -q`. Result: **63 passed** in about 14 s.

| Test | Result | Notes |
|---|---|---|
| Rule tests for every category (≥3 samples each, plus non-matching texts) | ✅ | `tests/test_classify.py`, including meme-caption fallback tests and "normal short text is not a meme" |
| Dupes: identical, resized and recompressed copies grouped; different images not | ✅ | `tests/test_dupes.py` |
| Export: copies land in the right folders, originals byte-identical, Trash only moves copies | ✅ | `tests/test_export.py` |
| Claude step: mocked `claude -p` parsed; invalid JSON, unknown category, missing CLI fall back | ✅ | `tests/test_claude.py` |
| API: scan, sort, search, edge-case errors, unreadable folder | ✅ | `tests/test_api.py` |
| One command (`pytest`) documented in the README | ✅ | |

## Manual end-to-end test

| Test | Result | Notes |
|---|---|---|
| Full flow on ~300 screenshots: scan → sort → results → search → export → Trash | ✅ | 338 images (12.2 MB). Scan, wall animation, 11 pile cards, summary (37 OTPs, 36 duplicates, 71 junk, 1.9 MB freeable), results, export and Trash all worked |
| Accuracy (spot-check ≥50 by eye) | ✅ | Random 60-item spot-check: **58/60**. Scored against ground truth: **97.0 %** (326/336). Every category is 100 % except Memes (28/38) |
| UPI receipts and OTPs near 100 % | ✅ | Receipts 100 %, OTPs 100 % |
| Search: brand, PNR, amount, name, place | ✅ | "Swiggy" 12 results with highlights, PNR 12, "926" 1, "Rohan" 9, "Gurugram" 11, "paneer" 17, nonsense 0 |
| Lightbox: category, reason, path, metadata, OCR text | ✅ | |
| Privacy blur | ✅ | Blurs thumbnails, snippets and OCR text, and is remembered across reloads |
| Export | ✅ | 9 category folders (267 files) + `_Trash` (71 files) |
| Move junk to Trash | ✅ | Confirmation dialog appears first, then 71 copies moved, the button changes to "Junk moved to Trash ✓" and the freed counter updates |
| Run with Claude Code **unavailable** | ✅ | Badge shows "Claude: off" and the full flow completes |
| Run with Claude Code **available** | ⚠️ | The `claude` CLI on the test machine is installed but not signed in, so a live run wasn't possible. The Claude step is covered by mocked tests (success, bad JSON, unknown category, missing CLI). Recheck on a machine where `claude` is signed in |
| Second run on the same folder skips indexed files | ✅ | **1.5 s** versus about 30 s the first time |
| Large folder (2,000+ images) | ✅ | 2,208 images in about 4 min (~9 images/s), accuracy **97.6 %** (2154/2206). Results grid stays smooth with infinite scroll (120 → 600 items loaded), no console errors |

## Edge cases and failures

| Test | Result | Notes |
|---|---|---|
| Folder doesn't exist | ✅ | "That folder doesn't exist" |
| Path is a file / blank path | ✅ | Friendly messages ("Please type a folder path.") |
| Empty folder / folder with no images | ✅ | "No screenshots found in that folder…"; sort says "There are no screenshots in that folder to sort." |
| Folder without read permission | ✅ | Was silently returning 0, now fixed: "No permission to read that folder". Tested with a real `icacls` deny ACL, and a regression test was added |
| Corrupt image / 0-byte file | ✅ | Both skipped and counted as errors; the run continues |
| Very large image (9000×9000) | ✅ | Processed without problems. Its tiny text is unreadable, so it went to Other |
| Non-English names and spaces | ✅ | Spaces, parentheses and Hindi characters in file names all work |
| Server stopped mid-sort | ✅ | Killed at 268/303. The DB integrity check came back `ok` and no processes were left behind. After a restart, already-indexed files were skipped and the run finished |
| No internet on later runs | ✅ | With a dead proxy (`HTTPS_PROXY=http://127.0.0.1:9`), the image model loaded from cache in 11.8 s and sorting worked |
| Originals untouched (count + mtimes before/after) | ✅ | 339 files: count, MD5 and mtime all identical after sort, export and Trash |

## Every screen

| Test | Result | Notes |
|---|---|---|
| Zero console errors / unhandled rejections | ✅ | Checked through the full flow and the 2,208-item grid |
| Layout at 1440×900 | ✅ | No horizontal scroll, nothing overlapping or cut off |
| Layout at 1920×1080 | ✅ | Same |
| Safari quick check | ❌ | No Mac or Safari was available on the Windows test machine. Only standard CSS and JS are used (no Chrome-only APIs). Please check once on a Mac |
| Every button visible and working; loading states; friendly errors | ✅ | No raw stack traces reach the UI |
| Animations smooth with no layout jumps | ✅ | Graveyard wall → pile cards → summary |
| All text in English, no placeholders or "TODO" | ✅ | |

## Fresh-install test

| Test | Result | Notes |
|---|---|---|
| Copy the repo to a new folder (no `.venv`) and follow the README only | ✅ | `.\run.ps1` created the venv, installed the latest versions (torch 2.15, open_clip 4.2.2, Pillow 13, FastAPI 0.163), found 8765 busy and started on 8769. In that fresh venv, `pytest` gave 63 passed, and a real sort of 338 images finished in 64 s with the same pile counts as the dev run |

## Acceptance checklist (§11)

| Item | Result | Notes |
|---|---|---|
| ~1,000 screenshots in under ~5 min, with progress shown the whole time | ✅ | About 9 images/s on Windows, so 1,000 take roughly 2 min. 2,208 took about 4 min. Not timed on an M1/M2 Mac, where Apple Vision OCR is usually faster |
| ≥80 % correct on a 50+ spot-check; UPI and OTP near 100 % | ✅ | 97–97.6 %; Receipts and OTPs 100 % |
| "Swiggy" / PNR search finds the right screenshots instantly | ✅ | SQLite FTS5 search |
| Originals untouched | ✅ | |
| Sorting animation smooth at 1440×900 | ✅ | |
| Works offline after the first model download | ✅ | |
| No paid service or API key; Claude only through the local `claude` CLI; no images sent | ✅ | Only a ≤600-character OCR snippet plus the file name is passed to `claude -p` |
| Claude off → everything works; Claude on → "Other" pile shrinks | ⚠️ | "Off" is verified. "On" couldn't be run live because the CLI isn't signed in here (see above) |

## Known limitations

- **Not tested on macOS** (Apple Vision OCR via `ocrmac`) or **Safari**. That code path is small, and it falls back to Tesseract if `ocrmac` fails.
- **Live Claude run not tested.** It's covered by mocked tests only.
- **Test data is synthetic**, not real phone screenshots. Real-world accuracy may be lower, especially for memes and photos.
- **Memes** whose caption OCR can't read (or that have no caption) can land in **Other**.
- Tiny text on huge images isn't readable. Blank images get a best guess from the image model (one went to Chats).
- The first image-model download is about 600 MB. Hugging Face prints a harmless "unauthenticated requests" warning in the terminal.
- **README demo GIF not recorded yet.** There is a placeholder in the README.
- If port 8765 is busy, the app picks the next free port and prints it.
