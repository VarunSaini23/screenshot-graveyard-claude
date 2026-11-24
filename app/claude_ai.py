"""Optional Claude pass through the user's own `claude -p` CLI. Only OCR text snippets are sent, never images."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading

from .classify import CATEGORIES

BATCH = 40
SNIPPET = 300
TIMEOUT = 240


def find_cli() -> str | None:
    if os.environ.get("SG_CLAUDE") == "0":
        return None
    return shutil.which("claude")


def _default_runner(cmd: list[str], prompt: str) -> str:
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                       timeout=TIMEOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode != 0 and not p.stdout.strip():
        raise RuntimeError((p.stderr or "claude exited with an error").strip()[:200])
    return p.stdout


def call_claude(prompt: str, runner=None, cli: str | None = None) -> str:
    """Run `claude -p --output-format json` and return the model's text. Raises on any failure."""
    cli = cli or find_cli()
    if not cli:
        raise FileNotFoundError("claude CLI not found")
    out = (runner or _default_runner)([cli, "-p", "--output-format", "json"], prompt)
    data = json.loads(out)
    if isinstance(data, dict):
        if data.get("is_error") or data.get("subtype") not in (None, "success"):
            raise RuntimeError(str(data.get("result") or "claude returned an error")[:200])
        return str(data.get("result", ""))
    raise RuntimeError("unexpected claude output")


def extract_json(text: str):
    """Pull the first JSON array/object out of a model reply (handles ``` fences and chatter)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON found in reply")


def build_sort_prompt(batch: list[dict]) -> str:
    rows = [{"id": it["id"], "text": (it.get("ocr") or "")[:SNIPPET].replace("\n", " "),
             "guess": it.get("category", "Other")} for it in batch]
    return (
        "You sort phone screenshots using only their OCR text. For each item choose exactly one category from "
        f"this list: {', '.join(CATEGORIES)}.\n"
        "Receipts = payments/UPI/bills. OTPs = one-time codes. Chats = messaging. Tickets = travel/movie bookings. "
        "Shopping = product pages/carts. Addresses = locations/maps. Recipes = cooking. Notes = long informational text. "
        "Memes = jokes. Photos = pictures of people/places. Other = anything else.\n"
        "Also give a short 3-6 word English title, e.g. \"Swiggy order ₹482\" or \"IndiGo boarding pass BLR–DEL\".\n"
        "Reply with ONLY a JSON array like [{\"id\": 1, \"category\": \"Receipts\", \"title\": \"...\"}], no prose.\n\n"
        f"Items:\n{json.dumps(rows, ensure_ascii=False)}"
    )


def parse_sort_reply(text: str, valid_ids: set[int]) -> dict[int, tuple[str, str]]:
    data = extract_json(text)
    if isinstance(data, dict):
        data = data.get("items") or data.get("results") or []
    out = {}
    lookup = {c.lower(): c for c in CATEGORIES}
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            item_id = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        cat = lookup.get(str(row.get("category", "")).strip().lower())
        if item_id not in valid_ids or not cat:
            continue
        title = re.sub(r"\s+", " ", str(row.get("title") or "")).strip()[:60]
        out[item_id] = (cat, title)
    return out


def sort_batch(batch: list[dict], runner=None, cli=None) -> dict[int, tuple[str, str]]:
    """Returns {id: (category, title)}; empty dict on any failure so old results are kept."""
    try:
        reply = call_claude(build_sort_prompt(batch), runner=runner, cli=cli)
        return parse_sort_reply(reply, {int(it["id"]) for it in batch})
    except Exception:
        return {}


def witty_lines(stats: dict, runner=None, cli=None) -> list[str] | None:
    prompt = (
        "Write 3 short, witty, friendly English one-liners (max 12 words each) about someone's screenshot "
        "collection, based on these counts. Use the real numbers with thousands separators. Example: "
        "\"2,340 OTPs. Not one of them still works.\" Reply with ONLY a JSON array of strings.\n\n"
        f"{json.dumps(stats)}"
    )
    try:
        data = extract_json(call_claude(prompt, runner=runner, cli=cli))
        lines = [str(s).strip()[:120] for s in data if isinstance(s, str) and s.strip()][:3]
        return lines or None
    except Exception:
        return None


class ClaudeStatus:
    """Checks once (in the background) whether the local CLI is installed and logged in."""

    def __init__(self):
        self.state = "unknown"  # unknown | checking | on | off
        self.detail = ""
        self._lock = threading.Lock()

    def check(self, runner=None):
        with self._lock:
            if self.state in ("checking", "on", "off"):
                return
            self.state = "checking"
        cli = find_cli()
        if not cli:
            self.state, self.detail = "off", "Claude Code CLI not found"
            return
        try:
            call_claude("Reply with the single word: ok", runner=runner, cli=cli)
            self.state, self.detail = "on", "Using your Claude Code subscription"
        except Exception as e:
            self.state, self.detail = "off", f"Claude Code not ready: {e}"[:160]

    def mark_off(self, why: str):
        self.state, self.detail = "off", why[:160]

    def start_check(self):
        threading.Thread(target=self.check, daemon=True).start()
