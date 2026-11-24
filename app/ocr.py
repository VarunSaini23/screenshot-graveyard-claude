"""On-device OCR: Apple Vision (ocrmac) on macOS, Tesseract elsewhere."""
from __future__ import annotations

import os
import platform
import shutil
from functools import lru_cache

from PIL import Image

MAX_SIDE = 2600


@lru_cache(maxsize=1)
def engine() -> str:
    if os.environ.get("SG_OCR") == "none":
        return "none"
    if platform.system() == "Darwin" and os.environ.get("SG_OCR") != "tesseract":
        try:
            import ocrmac  # noqa: F401
            return "apple-vision"
        except Exception:
            pass
    if _tesseract_cmd():
        return "tesseract"
    return "none"


@lru_cache(maxsize=1)
def _tesseract_cmd() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
              "/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract"):
        if os.path.exists(p):
            return p
    return None


def _prepare(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > MAX_SIDE:
        s = MAX_SIDE / longest
        img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    elif longest < 900:
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    return img


def read_text(img: Image.Image) -> str:
    eng = engine()
    if eng == "none":
        return ""
    img = _prepare(img)
    if eng == "apple-vision":
        from ocrmac import ocrmac
        results = ocrmac.OCR(img, recognition_level="accurate").recognize()
        # results are (text, confidence, bbox) with bbox origin at bottom-left; sort top-to-bottom
        results.sort(key=lambda r: (-round(r[2][1] + r[2][3], 2), r[2][0]))
        return "\n".join(r[0] for r in results)
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd()
    lang = os.environ.get("SG_OCR_LANG", "eng")
    return pytesseract.image_to_string(img.convert("L"), lang=lang, config="--psm 3")
