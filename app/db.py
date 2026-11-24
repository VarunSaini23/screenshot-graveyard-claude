"""SQLite storage with an FTS5 index over OCR text."""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from pathlib import Path


def home_dir() -> Path:
    d = Path(os.environ.get("SG_HOME", Path.home() / ".screenshot-graveyard"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "thumbs").mkdir(exist_ok=True)
    return d


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    folder TEXT NOT NULL,
    name TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    width INTEGER, height INTEGER,
    phash TEXT,
    ocr TEXT DEFAULT '',
    words INTEGER DEFAULT 0,
    category TEXT DEFAULT 'Other',
    confidence REAL DEFAULT 0,
    reason TEXT DEFAULT '',
    title TEXT DEFAULT '',
    thumb TEXT,
    status TEXT DEFAULT 'new',
    error TEXT DEFAULT '',
    dup_of INTEGER,
    export_path TEXT,
    trashed INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_items_folder ON items(folder);
CREATE INDEX IF NOT EXISTS idx_items_cat ON items(folder, category);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(ocr, title, name, tokenize='unicode61');
"""


class DB:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else home_dir() / "index.db"
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def q(self, sql: str, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def exec(self, sql: str, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def get_by_path(self, path: str):
        return self.one("SELECT * FROM items WHERE path=?", (path,))

    def upsert(self, rec: dict) -> int:
        cols = ["path", "folder", "name", "size", "mtime", "width", "height", "phash", "ocr",
                "words", "category", "confidence", "reason", "title", "thumb", "status", "error"]
        vals = [rec.get(c) for c in cols]
        with self.lock:
            row = self.conn.execute("SELECT id FROM items WHERE path=?", (rec["path"],)).fetchone()
            if row:
                item_id = row[0]
                sets = ",".join(f"{c}=?" for c in cols)
                self.conn.execute(
                    f"UPDATE items SET {sets}, dup_of=NULL, export_path=NULL, trashed=0 WHERE id=?",
                    vals + [item_id])
                self.conn.execute("DELETE FROM items_fts WHERE rowid=?", (item_id,))
            else:
                cur = self.conn.execute(
                    f"INSERT INTO items ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
                item_id = cur.lastrowid
            self.conn.execute("INSERT INTO items_fts(rowid, ocr, title, name) VALUES (?,?,?,?)",
                              (item_id, rec.get("ocr") or "", rec.get("title") or "", rec.get("name") or ""))
            self.conn.commit()
        return item_id

    def set_category(self, item_id: int, category: str, confidence: float, reason: str, title: str | None = None):
        with self.lock:
            if title is not None:
                self.conn.execute("UPDATE items SET category=?, confidence=?, reason=?, title=? WHERE id=?",
                                  (category, confidence, reason, title, item_id))
                self.conn.execute("UPDATE items_fts SET title=? WHERE rowid=?", (title, item_id))
            else:
                self.conn.execute("UPDATE items SET category=?, confidence=?, reason=? WHERE id=?",
                                  (category, confidence, reason, item_id))
            self.conn.commit()

    def set_folder(self, path: str, folder: str):
        self.exec("UPDATE items SET folder=? WHERE path=?", (folder, path))


def fts_query(q: str) -> str:
    """Turn free text into a safe FTS5 prefix query: every word must appear."""
    toks = re.findall(r"[\w₹]+", q, flags=re.UNICODE)
    return " ".join(f'"{t}"*' for t in toks[:8])
