import hashlib
import os

from app.export import TRASH, export_items, trash_items


def digest(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def setup_files(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    files = []
    for i, cat in enumerate(["Receipts", "OTPs", "Chats", "OTPs"]):
        p = src / (f"shot {i} नमस्ते.png" if i == 2 else f"shot{i}.png")
        p.write_bytes(os.urandom(500 + i))
        os.utime(p, (1_600_000_000 + i, 1_600_000_000 + i))
        files.append({"id": i + 1, "path": str(p), "category": cat, "size": p.stat().st_size, "export_path": None})
    # same file name in a subfolder -> must not overwrite
    sub = src / "sub"
    sub.mkdir()
    p = sub / "shot0.png"
    p.write_bytes(os.urandom(900))
    files.append({"id": 9, "path": str(p), "category": "Receipts", "size": 900, "export_path": None})
    return src, files


def snapshot(folder):
    return {str(p): (p.stat().st_mtime, p.stat().st_size, digest(p)) for p in folder.rglob("*") if p.is_file()}


def test_export_copies_into_categories_and_leaves_originals(tmp_path):
    src, files = setup_files(tmp_path)
    before = snapshot(src)
    out = tmp_path / "out"
    res = export_items(files, out)
    assert res["copied"] == 5 and not res["failed"]
    assert snapshot(src) == before
    assert sorted(p.name for p in (out / "Receipts").iterdir()) == ["shot0 (2).png", "shot0.png"]
    assert len(list((out / "OTPs").iterdir())) == 2
    assert (out / "Chats" / "shot 2 नमस्ते.png").exists()
    for f in files:
        assert digest(res["updates"][f["id"]]) == digest(f["path"])
    # re-export is idempotent
    for f in files:
        f["export_path"] = res["updates"][f["id"]]
    res2 = export_items(files, out)
    assert res2["copied"] == 0 and res2["skipped"] == 5


def test_trash_moves_only_copies(tmp_path):
    src, files = setup_files(tmp_path)
    before = snapshot(src)
    out = tmp_path / "out"
    res = export_items(files, out)
    for f in files:
        f["export_path"] = res["updates"][f["id"]]
    junk = [f for f in files if f["category"] == "OTPs"]
    t = trash_items(junk, out)
    assert t["moved"] == 2 and t["freed"] == sum(f["size"] for f in junk)
    assert len(list((out / TRASH).iterdir())) == 2
    assert not list((out / "OTPs").iterdir())
    assert snapshot(src) == before  # originals untouched


def test_trash_without_export_copies_original(tmp_path):
    src, files = setup_files(tmp_path)
    before = snapshot(src)
    out = tmp_path / "out"
    t = trash_items(files[:1], out)
    assert t["moved"] == 1 and (out / TRASH / "shot0.png").exists()
    assert snapshot(src) == before


def test_missing_source_reported_not_raised(tmp_path):
    res = export_items([{"id": 1, "path": str(tmp_path / "nope.png"), "category": "Other", "export_path": None}], tmp_path / "o")
    assert res["copied"] == 0 and len(res["failed"]) == 1
