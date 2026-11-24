"""Exact and near-duplicate detection with perceptual hashes (phash, Hamming <= 6)."""
from __future__ import annotations

import re

import numpy as np

MAX_DIST = 6
_POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def _popcount64(x: np.ndarray) -> np.ndarray:
    return _POP[x.view(np.uint8)].reshape(x.shape + (8,)).sum(axis=-1)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", (text or "").lower()))


def _text_compatible(a: str, b: str) -> bool:
    """Screens from the same app can look alike; if both are text-heavy, the text must match too."""
    ta, tb = _tokens(a), _tokens(b)
    if len(ta) < 8 or len(tb) < 8:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.7


def find_groups(items: list[dict], max_dist: int = MAX_DIST) -> list[list[dict]]:
    """items: dicts with id, phash (hex), mtime, ocr. Returns groups (size >= 2), newest first."""
    items = [it for it in items if it.get("phash")]
    n = len(items)
    if n < 2:
        return []
    hashes = np.array([int(it["phash"], 16) for it in items], dtype=np.uint64)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    chunk = 512
    for start in range(0, n, chunk):
        block = hashes[start:start + chunk]
        d = _popcount64(block[:, None] ^ hashes[None, :])
        ii, jj = np.nonzero(d <= max_dist)
        for a, b in zip((ii + start).tolist(), jj.tolist()):
            if b <= a:
                continue
            ra, rb = find(a), find(b)
            if ra != rb and _text_compatible(items[a].get("ocr", ""), items[b].get("ocr", "")):
                parent[rb] = ra

    groups: dict[int, list[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i])
    out = [sorted(g, key=lambda it: (it["mtime"], it["id"]), reverse=True) for g in groups.values() if len(g) > 1]
    out.sort(key=len, reverse=True)
    return out


def duplicate_map(items: list[dict]) -> dict[int, int]:
    """Map duplicate id -> id of the copy we keep (the newest)."""
    m = {}
    for g in find_groups(items):
        keep = g[0]["id"]
        for it in g[1:]:
            m[it["id"]] = keep
    return m
