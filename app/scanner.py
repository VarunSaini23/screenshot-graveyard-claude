"""Find screenshots, make cached thumbnails, and process one file (thumb + hash + OCR)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PIL import Image, ImageOps

from .db import home_dir

EXTS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp"}
OUTPUT_NAME = "Screenshot Graveyard Output"
THUMB_SIZE = 256
Image.MAX_IMAGE_PIXELS = 250_000_000

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_OK = True
except Exception:  # pragma: no cover
    HEIC_OK = False


class ScanError(Exception):
    pass


def find_images(folder: str) -> list[dict]:
    root = Path(os.path.expanduser(folder.strip().strip('"'))).resolve() if folder.strip() else None
    if root is None:
        raise ScanError("Please type a folder path.")
    if not root.exists():
        raise ScanError(f"That folder doesn't exist: {root}")
    if not root.is_dir():
        raise ScanError(f"That path is a file, not a folder: {root}")
    if not os.access(root, os.R_OK):
        raise ScanError(f"No permission to read that folder: {root}")
    found = []
    root_errors: list[OSError] = []

    def on_error(err: OSError):
        if Path(getattr(err, "filename", "") or "") == root:
            root_errors.append(err)

    try:
        for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
            dirnames[:] = [d for d in dirnames if d != OUTPUT_NAME and not d.startswith(".")]
            for fn in filenames:
                if Path(fn).suffix.lower() in EXTS and not fn.startswith("._"):
                    p = os.path.join(dirpath, fn)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    found.append({"path": p, "name": fn, "size": st.st_size, "mtime": st.st_mtime})
    except PermissionError:
        raise ScanError(f"No permission to read that folder: {root}")
    if root_errors:
        raise ScanError(f"No permission to read that folder: {root}")
    found.sort(key=lambda f: f["mtime"], reverse=True)
    return found


def thumb_path(path: str, mtime: float) -> Path:
    key = hashlib.sha1(f"{path}|{mtime}".encode("utf-8")).hexdigest()
    return home_dir() / "thumbs" / f"{key}.webp"


def open_image(path: str) -> Image.Image:
    img = Image.open(path)
    img.load()
    img = ImageOps.exif_transpose(img)
    return img


def make_thumb(img: Image.Image, out: Path) -> None:
    t = img.convert("RGB")
    t.thumbnail((THUMB_SIZE, THUMB_SIZE * 2), Image.LANCZOS)
    tmp = out.with_suffix(".tmp")
    t.save(tmp, "WEBP", quality=78, method=4)
    os.replace(tmp, out)


def ensure_thumb(path: str, mtime: float) -> Path | None:
    out = thumb_path(path, mtime)
    if out.exists():
        return out
    try:
        make_thumb(open_image(path), out)
        return out
    except Exception:
        return None


def process_one(path: str, mtime: float) -> dict:
    """Runs in a worker process. Never raises."""
    import imagehash

    from .ocr import read_text

    rec = {"path": path, "status": "done", "error": "", "ocr": "", "phash": None,
           "thumb": None, "width": None, "height": None}
    try:
        if os.path.getsize(path) == 0:
            raise ValueError("empty file")
        img = open_image(path)
        rec["width"], rec["height"] = img.size
        out = thumb_path(path, mtime)
        if not out.exists():
            make_thumb(img, out)
        rec["thumb"] = str(out)
        rec["phash"] = str(imagehash.phash(img.convert("RGB")))
        try:
            rec["ocr"] = (read_text(img) or "").strip()
        except Exception as e:  # OCR failure shouldn't drop the image
            rec["error"] = f"ocr: {e}"[:200]
    except Exception as e:
        rec["status"] = "error"
        rec["error"] = str(e)[:200] or e.__class__.__name__
    return rec
