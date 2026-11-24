"""FastAPI app: REST API, SSE progress stream, thumbnails and the static dashboard."""
from __future__ import annotations

import asyncio
import io
import json
import os
import platform
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import export, ocr
from .classify import CATEGORIES, Clip
from .claude_ai import ClaudeStatus
from .db import DB, fts_query, home_dir
from .pipeline import Job, junk_rows, summarize
from .scanner import HEIC_OK, ScanError, ensure_thumb, find_images, open_image

WEB = Path(__file__).resolve().parent.parent / "web"
PAGE = 120

@asynccontextmanager
async def lifespan(_app):
    claude.start_check()
    yield


app = FastAPI(title="Screenshot Graveyard", lifespan=lifespan)
db = DB()
clip = Clip()
claude = ClaudeStatus()
job = Job(db, clip, claude)
STATE_FILE = home_dir() / "state.json"


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _save_state(**kw):
    s = _load_state()
    s.update(kw)
    STATE_FILE.write_text(json.dumps(s), "utf-8")


state = _load_state()


@app.exception_handler(Exception)
async def friendly_errors(request: Request, exc: Exception):
    return JSONResponse({"error": "Something went wrong on our side. Please try again."}, status_code=500)


def err(msg: str, code: int = 400):
    raise HTTPException(code, msg)


class ScanIn(BaseModel):
    folder: str


@app.get("/api/status")
def status():
    home = Path.home()
    sugg = [p for p in [home / "Pictures" / "Screenshots", home / "Desktop", home / "Downloads",
                        home / "OneDrive" / "Pictures" / "Screenshots", home / "Pictures"] if p.is_dir()]
    return {
        "claude": claude.state, "claude_detail": claude.detail,
        "ocr": ocr.engine(), "clip": clip.available(), "heic": HEIC_OK,
        "suggestions": [str(p) for p in sugg][:4],
        "folder": state.get("folder"), "sorted": bool(state.get("sorted")),
        "job": job.state, "platform": platform.system(),
    }


@app.post("/api/scan")
def scan(body: ScanIn):
    if job.running():
        err("A sort is already running. Please wait for it to finish.")
    try:
        files = find_images(body.folder)
    except ScanError as e:
        err(str(e))
    folder = str(Path(os.path.expanduser(body.folder.strip().strip('"'))).resolve())
    state["scan"] = {"folder": folder}
    job.reset(folder, files)
    indexed = 0
    if files:
        with db.lock:
            paths = {r[0]: (r[1], r[2]) for r in db.conn.execute("SELECT path, mtime, size FROM items WHERE status!='new'")}
        indexed = sum(1 for f in files if paths.get(f["path"]) == (f["mtime"], f["size"]))
    return {"folder": folder, "count": len(files), "bytes": sum(f["size"] for f in files), "indexed": indexed,
            "heic": sum(1 for f in files if f["name"].lower().endswith((".heic", ".heif")))}


@app.post("/api/sort")
def sort():
    if job.running():
        return {"ok": True, "already": True}
    if not job.folder:
        err("Scan a folder first.")
    if not job.files:
        err("There are no screenshots in that folder to sort.")
    job.start(job.folder, job.files)
    state.update(folder=job.folder, sorted=False)
    _save_state(folder=job.folder, sorted=False)
    return {"ok": True, "total": job.total}


@app.post("/api/cancel")
def cancel():
    job.cancel = True
    return {"ok": True}


@app.get("/api/peek/{i}.webp")
def peek(i: int):
    if i < 0 or i >= len(job.files):
        err("Not found", 404)
    f = job.files[i]
    p = ensure_thumb(f["path"], f["mtime"])
    if not p:
        err("Not found", 404)
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/progress")
async def progress(request: Request):
    async def gen():
        yield f"data: {json.dumps(job.snapshot())}\n\n"
        sent = len(job.events)
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            with job.lock:
                new = job.events[sent:]
            if new:
                sent += len(new)
                # coalesce into one SSE message to keep the browser smooth on big folders
                yield f"data: {json.dumps({'type': 'batch', 'events': new, 'done': job.done, 'total': job.total})}\n\n"
                idle = 0
            else:
                idle += 1
                if idle % 50 == 0:
                    yield ": ping\n\n"
            if not job.running() and sent >= len(job.events):
                if job.state in ("done", "cancelled", "error"):
                    _mark_sorted()
                return
            await asyncio.sleep(0.12)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _mark_sorted():
    if job.state == "done" and not state.get("sorted"):
        state.update(folder=job.folder, sorted=True)
        _save_state(folder=job.folder, sorted=True)


def _folder() -> str:
    _mark_sorted()
    f = state.get("folder")
    if not f:
        err("No folder has been sorted yet.")
    return f


@app.get("/api/summary")
def api_summary():
    s = summarize(db, _folder())
    s["output"] = str(export.output_root(s["folder"]))
    s["claude"] = claude.state
    return s


COLS = "id, name, size, mtime, category, confidence, reason, title, words, dup_of, trashed, status, width, height"


@app.get("/api/items")
def items(category: str = "", q: str = "", page: int = 0, view: str = ""):
    folder = _folder()
    where, args = ["i.folder=?"], [folder]
    if view == "junk":
        ids = [r["id"] for r in junk_rows(db, folder)]
        where.append(f"i.id IN ({','.join(map(str, ids)) or '0'})")
    elif view == "duplicates":
        where.append("(i.dup_of IS NOT NULL OR i.id IN (SELECT dup_of FROM items WHERE folder=? AND dup_of IS NOT NULL))")
        args.append(folder)
    elif view == "trash":
        where.append("i.trashed=1")
    else:
        where.append("i.trashed=0")
    if category and category in CATEGORIES:
        where.append("i.category=?")
        args.append(category)
    order = "i.mtime DESC"
    if view == "duplicates":
        order = "COALESCE(i.dup_of, i.id), i.dup_of IS NOT NULL, i.mtime DESC"
    sel = ", ".join(f"i.{c.strip()}" for c in COLS.split(","))
    fq = fts_query(q) if q.strip() else ""
    if q.strip() and not fq:
        return {"items": [], "total": 0, "page": page, "pages": 0}
    if fq:
        base = (f"FROM items i JOIN items_fts f ON f.rowid=i.id WHERE items_fts MATCH ? AND {' AND '.join(where)}")
        args = [fq] + args
        sel += ", snippet(items_fts, 0, '[[', ']]', '…', 14) AS snippet"
        order = "bm25(items_fts)"
    else:
        base = f"FROM items i WHERE {' AND '.join(where)}"
    total = db.one(f"SELECT COUNT(*) n {base}", args)["n"]
    rows = db.q(f"SELECT {sel} {base} ORDER BY {order} LIMIT ? OFFSET ?", args + [PAGE, page * PAGE])
    return {"items": rows, "total": total, "page": page, "pages": (total + PAGE - 1) // PAGE}


@app.get("/api/item/{item_id}")
def item(item_id: int):
    r = db.one("SELECT * FROM items WHERE id=?", (item_id,))
    if not r:
        err("Not found", 404)
    r.pop("thumb", None)
    return r


@app.get("/thumbs/{item_id}.webp")
def thumb(item_id: int):
    r = db.one("SELECT path, mtime, thumb FROM items WHERE id=?", (item_id,))
    if not r:
        err("Not found", 404)
    p = Path(r["thumb"]) if r["thumb"] else None
    if not p or not p.exists():
        p = ensure_thumb(r["path"], r["mtime"])
    if not p:
        err("Not found", 404)
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "max-age=86400"})


@app.get("/image/{item_id}")
def image(item_id: int):
    r = db.one("SELECT path FROM items WHERE id=?", (item_id,))
    if not r or not os.path.exists(r["path"]):
        err("Not found", 404)
    ext = Path(r["path"]).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        return FileResponse(r["path"])
    try:
        img = open_image(r["path"]).convert("RGB")
    except Exception:
        err("This image can't be displayed.", 415)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return Response(buf.getvalue(), media_type="image/jpeg")


@app.post("/api/export")
def do_export():
    folder = _folder()
    if job.running():
        err("Please wait for sorting to finish.")
    rows = db.q("SELECT id, path, category, export_path FROM items WHERE folder=? AND trashed=0", (folder,))
    root = export.output_root(folder)
    res = export.export_items(rows, root)
    with db.lock:
        db.conn.executemany("UPDATE items SET export_path=? WHERE id=?", [(p, i) for i, p in res.pop("updates").items()])
        db.conn.commit()
    return res


@app.post("/api/trash-junk")
def trash_junk():
    folder = _folder()
    if job.running():
        err("Please wait for sorting to finish.")
    rows = junk_rows(db, folder)
    root = export.output_root(folder)
    res = export.trash_items(rows, root)
    with db.lock:
        db.conn.executemany("UPDATE items SET export_path=?, trashed=1 WHERE id=?",
                            [(p, i) for i, p in res.pop("updates").items()])
        db.conn.commit()
    res["ids"] = [r["id"] for r in rows]
    return res


@app.post("/api/open-output")
def open_output():
    root = export.output_root(_folder())
    root.mkdir(parents=True, exist_ok=True)
    try:
        if platform.system() == "Windows":
            os.startfile(str(root))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(root)])
        else:
            subprocess.Popen(["xdg-open", str(root)])
    except Exception:
        err(f"Couldn't open the folder. It's here: {root}")
    return {"ok": True, "path": str(root)}


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
