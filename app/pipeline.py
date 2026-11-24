"""The sorting job: OCR + classify in a process pool, duplicates, then an optional Claude pass."""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from . import claude_ai, dupes
from .classify import CATEGORIES, Clip, classify, word_count
from .db import DB
from .scanner import open_image, process_one

YEAR = 365 * 24 * 3600


def workers() -> int:
    env = os.environ.get("SG_WORKERS")
    if env and env.isdigit():
        return max(1, int(env))
    return max(1, (os.cpu_count() or 2) - 1)


class Job:
    def __init__(self, db: DB, clip: Clip, claude: claude_ai.ClaudeStatus):
        self.db, self.clip, self.claude = db, clip, claude
        self.lock = threading.Lock()
        self.reset(None, [])

    def reset(self, folder, files):
        self.folder = folder
        self.files = files
        self.state = "idle"
        self.phase = ""
        self.phase_text = ""
        self.total = len(files)
        self.done = 0
        self.cached = 0
        self.errors = 0
        self.counts = {c: 0 for c in CATEGORIES}
        self.started = None
        self.finished = None
        self.events: list[dict] = []
        self.error = ""
        self.cancel = False
        self.thread = None

    # ------------------------------------------------------------------ helpers
    def emit(self, ev: dict):
        with self.lock:
            self.events.append(ev)

    def set_phase(self, phase: str, text: str):
        self.phase, self.phase_text = phase, text
        self.emit({"type": "phase", "phase": phase, "text": text})

    def snapshot(self) -> dict:
        return {"type": "snapshot", "state": self.state, "phase": self.phase, "text": self.phase_text,
                "done": self.done, "total": self.total, "cached": self.cached, "counts": dict(self.counts),
                "elapsed": round((self.finished or time.time()) - self.started, 1) if self.started else 0,
                "error": self.error, "folder": self.folder}

    def running(self) -> bool:
        return self.state == "running"

    def start(self, folder: str, files: list[dict]):
        if self.running():
            raise RuntimeError("A sort is already running.")
        self.reset(folder, files)
        self.state = "running"
        self.started = time.time()
        self.thread = threading.Thread(target=self._run_safe, daemon=True)
        self.thread.start()

    def _run_safe(self):
        try:
            self._run()
            self.state = "cancelled" if self.cancel else "done"
        except Exception as e:  # pragma: no cover - surfaced to the UI
            self.state, self.error = "error", f"Sorting stopped: {e}"
        self.finished = time.time()
        self.emit({"type": "end", **self.snapshot()})

    # ------------------------------------------------------------------ pipeline
    def _run(self):
        folder, files = self.folder, self.files
        self.set_phase("reading", "Reading text inside your screenshots…")
        todo, cached_idx = [], []
        for idx, f in enumerate(files):
            row = self.db.get_by_path(f["path"])
            if row and abs(row["mtime"] - f["mtime"]) < 1e-6 and row["size"] == f["size"] and row["status"] in ("done", "error"):
                if row["folder"] != folder:
                    self.db.set_folder(f["path"], folder)
                self.counts[row["category"]] = self.counts.get(row["category"], 0) + 1
                self.cached += 1
                self.done += 1
                cached_idx.append(idx)
            else:
                todo.append((idx, f))
        if self.cached:
            self.emit({"type": "cached", "n": self.cached, "counts": dict(self.counts), "done": self.done,
                       "idx": cached_idx})

        if todo:
            with ProcessPoolExecutor(max_workers=workers()) as pool:
                futs = {pool.submit(process_one, f["path"], f["mtime"]): (idx, f) for idx, f in todo}
                for fut in as_completed(futs):
                    if self.cancel:
                        pool.shutdown(wait=False, cancel_futures=True)
                        return
                    idx, f = futs[fut]
                    try:
                        res = fut.result()
                    except Exception as e:  # worker crashed
                        res = {"path": f["path"], "status": "error", "error": str(e)[:200], "ocr": ""}
                    self._store(idx, f, res)

        if self.cancel:
            return
        self.set_phase("dupes", "Looking for duplicates…")
        self._dupes()

        if self.cancel:
            return
        if self.claude.state in ("unknown", "checking"):
            self.claude.check()
        if self.claude.state == "on":
            self._claude_pass()
        self.set_phase("summary", "Adding it all up…")
        self.witty = None
        if self.claude.state == "on":
            s = summarize(self.db, folder)
            self.witty = claude_ai.witty_lines({
                "screenshots": s["total"], "otps": s["counts"].get("OTPs", 0), "duplicates": s["dupes"],
                "receipts": s["counts"].get("Receipts", 0), "memes": s["counts"].get("Memes", 0),
                "gb_freeable": round(s["junk_bytes"] / 1e9, 2)})
        save_witty(self.db, folder, self.witty)

    def _store(self, idx: int, f: dict, res: dict):
        text = res.get("ocr") or ""
        if res.get("status") == "error":
            cat, conf, reason = "Other", 0.0, f"could not read image ({res.get('error', '')})"
        else:
            needs_clip = self.clip.enabled and word_count(text) < 8
            if needs_clip and not self.clip.loaded:
                self.set_phase("model", "Loading the image model (first run downloads ~600 MB)…")
            cat, conf, reason = classify(text, lambda: open_image(f["path"]), self.clip if needs_clip else None)
            if self.phase == "model":
                self.set_phase("reading", "Reading text inside your screenshots…")
        rec = {**f, **res, "folder": self.folder, "ocr": text, "words": word_count(text),
               "category": cat, "confidence": conf, "reason": reason, "title": ""}
        item_id = self.db.upsert(rec)
        self.counts[cat] = self.counts.get(cat, 0) + 1
        self.done += 1
        if res.get("status") == "error":
            self.errors += 1
        self.emit({"type": "item", "i": idx, "id": item_id, "category": cat, "done": self.done,
                   "thumb": f"/thumbs/{item_id}.webp" if res.get("thumb") else None})

    def _dupes(self):
        rows = self.db.q("SELECT id, phash, mtime, ocr FROM items WHERE folder=? AND status='done'", (self.folder,))
        m = dupes.duplicate_map(rows)
        with self.db.lock:
            self.db.conn.execute("UPDATE items SET dup_of=NULL WHERE folder=?", (self.folder,))
            self.db.conn.executemany("UPDATE items SET dup_of=? WHERE id=?", [(k, d) for d, k in m.items()])
            self.db.conn.commit()
        self.emit({"type": "dupes", "n": len(m)})

    def _claude_pass(self):
        rows = self.db.q(
            "SELECT id, ocr, category FROM items WHERE folder=? AND status='done' AND words>0 "
            "AND (category='Other' OR confidence<0.6) ORDER BY id", (self.folder,))
        if not rows:
            return
        batches = [rows[i:i + claude_ai.BATCH] for i in range(0, len(rows), claude_ai.BATCH)]
        failures = 0
        for n, batch in enumerate(batches, 1):
            if self.cancel:
                return
            self.set_phase("claude", f"Claude is sorting the tricky ones… (batch {n} of {len(batches)})")
            res = claude_ai.sort_batch(batch)
            if not res:
                failures += 1
                if failures >= 2 and n == failures:
                    self.claude.mark_off("Claude Code didn't answer; kept the local results.")
                    return
                continue
            old = {r["id"]: r["category"] for r in batch}
            for item_id, (cat, title) in res.items():
                self.db.set_category(item_id, cat, 0.8, "Claude (from the text only)", title)
                if old[item_id] != cat:
                    self.counts[old[item_id]] -= 1
                    self.counts[cat] = self.counts.get(cat, 0) + 1
            self.emit({"type": "reclass", "counts": dict(self.counts), "changed": len(res)})


# ---------------------------------------------------------------------- summary helpers
def junk_rows(db: DB, folder: str, include_trashed: bool = False) -> list[dict]:
    cutoff = time.time() - YEAR
    tr = "" if include_trashed else "AND trashed=0"
    return db.q(
        f"SELECT id, path, size, category, export_path, dup_of, words, mtime FROM items WHERE folder=? {tr} AND ("
        "category='OTPs' OR dup_of IS NOT NULL OR (category='Other' AND words<5 AND mtime<?))", (folder, cutoff))


def save_witty(db: DB, folder: str, lines):
    import json
    db.exec("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    db.exec("INSERT OR REPLACE INTO meta VALUES (?,?)", ("witty:" + folder, json.dumps(lines)))


def load_witty(db: DB, folder: str):
    import json
    db.exec("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    r = db.one("SELECT v FROM meta WHERE k=?", ("witty:" + folder,))
    return json.loads(r["v"]) if r and r["v"] else None


def summarize(db: DB, folder: str) -> dict:
    cutoff = time.time() - YEAR
    tot = db.one("SELECT COUNT(*) n, COALESCE(SUM(size),0) b, SUM(status='error') e, SUM(trashed) t, "
                 "COALESCE(SUM(CASE WHEN trashed=1 THEN size ELSE 0 END),0) tb FROM items WHERE folder=?", (folder,))
    counts = {c: 0 for c in CATEGORIES}
    for r in db.q("SELECT category, COUNT(*) n FROM items WHERE folder=? AND trashed=0 GROUP BY category", (folder,)):
        counts[r["category"]] = r["n"]
    d = db.one("SELECT COUNT(*) n, COALESCE(SUM(size),0) b FROM items WHERE folder=? AND trashed=0 AND dup_of IS NOT NULL", (folder,))
    otp = db.one("SELECT COUNT(*) n FROM items WHERE folder=? AND trashed=0 AND category='OTPs'", (folder,))
    old = db.one("SELECT COUNT(*) n FROM items WHERE folder=? AND trashed=0 AND category='Other' AND words<5 "
                 "AND mtime<? AND dup_of IS NULL", (folder, cutoff))
    junk = junk_rows(db, folder)
    return {
        "folder": folder, "total": tot["n"], "bytes": tot["b"], "errors": tot["e"] or 0,
        "counts": counts, "dupes": d["n"], "dupe_bytes": d["b"], "otps": otp["n"],
        "old_other": old["n"], "junk": len(junk), "junk_bytes": sum(r["size"] for r in junk),
        "trashed": tot["t"] or 0, "trashed_bytes": tot["tb"],
        "exported": db.one("SELECT COUNT(*) n FROM items WHERE folder=? AND export_path IS NOT NULL AND trashed=0", (folder,))["n"],
        "witty": load_witty(db, folder),
    }
