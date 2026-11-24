"""Copy screenshots into sorted folders. Originals are never moved, modified or deleted."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .scanner import OUTPUT_NAME

TRASH = "_Trash"


def output_root(folder: str) -> Path:
    env = os.environ.get("SG_OUTPUT")
    if env:
        return Path(env)
    src = Path(folder).resolve()
    parent = src.parent if src.parent != src else src
    return parent / OUTPUT_NAME


def _unique_dest(dest_dir: Path, name: str, src: Path) -> tuple[Path, bool]:
    """Pick a destination path. Returns (path, already_there) so re-exports are idempotent."""
    dest = dest_dir / name
    stem, suf = Path(name).stem, Path(name).suffix
    k = 2
    st = src.stat()
    while dest.exists():
        dst = dest.stat()
        if dst.st_size == st.st_size and int(dst.st_mtime) == int(st.st_mtime):
            return dest, True
        dest = dest_dir / f"{stem} ({k}){suf}"
        k += 1
    return dest, False


def copy_into(src_path: str, dest_dir: Path) -> Path:
    src = Path(src_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest, exists = _unique_dest(dest_dir, src.name, src)
    if not exists:
        shutil.copy2(src, dest)
    return dest


def export_items(items: list[dict], root: Path) -> dict:
    """items: dicts with id, path, category, export_path. Returns {id: new_export_path} and stats."""
    done, skipped, failed, updates = 0, 0, [], {}
    for it in items:
        try:
            cur = it.get("export_path")
            if cur and Path(cur).exists() and Path(cur).parent.name == it["category"]:
                skipped += 1
                continue
            dest = copy_into(it["path"], root / it["category"])
            updates[it["id"]] = str(dest)
            done += 1
        except Exception as e:
            failed.append({"id": it["id"], "error": str(e)[:160]})
    return {"copied": done, "skipped": skipped, "failed": failed, "updates": updates, "root": str(root)}


def trash_items(items: list[dict], root: Path) -> dict:
    """Move each junk item's *copy* into root/_Trash. If no copy exists yet, copy the original there."""
    trash_dir = root / TRASH
    trash_dir.mkdir(parents=True, exist_ok=True)
    moved, freed, failed, updates = 0, 0, [], {}
    for it in items:
        try:
            cur = it.get("export_path")
            cur_p = Path(cur) if cur else None
            if cur_p and cur_p.exists() and cur_p.parent == trash_dir:
                updates[it["id"]] = str(cur_p)
            elif cur_p and cur_p.exists() and root in cur_p.parents:
                dest, exists = _unique_dest(trash_dir, cur_p.name, cur_p)
                if exists:
                    cur_p.unlink()
                else:
                    shutil.move(str(cur_p), str(dest))
                updates[it["id"]] = str(dest)
            else:
                updates[it["id"]] = str(copy_into(it["path"], trash_dir))
            moved += 1
            freed += int(it.get("size") or 0)
        except Exception as e:
            failed.append({"id": it["id"], "error": str(e)[:160]})
    return {"moved": moved, "freed": freed, "failed": failed, "updates": updates, "root": str(root)}
