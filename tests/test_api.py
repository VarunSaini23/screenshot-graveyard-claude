"""End-to-end API test on generated screenshots: scan -> sort -> summary -> search -> export -> trash."""
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import ocr
from tools.make_samples import make


def snapshot(folder: Path):
    return {str(p): (p.stat().st_mtime, p.stat().st_size) for p in folder.rglob("*") if p.is_file()}


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    root = tmp_path_factory.mktemp("e2e")
    src = root / "My Screenshots"
    make(src, n=36)
    os.environ["SG_OUTPUT"] = str(root / "out")
    from app.server import app
    with TestClient(app) as c:
        yield c, src, root / "out"
    os.environ.pop("SG_OUTPUT", None)


def wait_done(c, timeout=300):
    from app.server import job
    t0 = time.time()
    while job.running():
        assert time.time() - t0 < timeout, "sort took too long"
        time.sleep(0.3)
    assert job.state == "done", job.error
    return job


def test_scan_errors(env):
    c, src, _ = env
    r = c.post("/api/scan", json={"folder": str(src / "does-not-exist")})
    assert r.status_code == 400 and "doesn't exist" in r.json()["detail"]
    r = c.post("/api/scan", json={"folder": ""})
    assert r.status_code == 400
    empty = src.parent / "empty"
    empty.mkdir()
    r = c.post("/api/scan", json={"folder": str(empty)})
    assert r.status_code == 200 and r.json()["count"] == 0
    assert c.post("/api/sort").status_code == 400


def test_full_flow(env):
    c, src, out = env
    before = snapshot(src)
    r = c.post("/api/scan", json={"folder": str(src)})
    assert r.status_code == 200
    info = r.json()
    assert info["count"] >= 36 + 2  # + broken files
    assert any(c.get(f"/api/peek/{i}.webp").status_code == 200 for i in range(4))
    assert c.get("/api/peek/99999.webp").status_code == 404
    assert c.post("/api/sort").status_code == 200
    job = wait_done(c)
    first_duration = job.finished - job.started
    assert job.errors == 2  # empty.png + corrupt.jpg

    s = c.get("/api/summary").json()
    assert s["total"] == info["count"]
    assert s["dupes"] >= 2
    if ocr.engine() != "none":
        assert s["counts"]["OTPs"] >= 3 and s["counts"]["Receipts"] >= 3
        hits = c.get("/api/items", params={"q": "Swiggy"}).json()
        assert hits["total"] >= 1 and "[[" in hits["items"][0]["snippet"]
        assert c.get("/api/items", params={"q": "PNR"}).json()["total"] >= 1

    items = c.get("/api/items").json()
    assert items["total"] == info["count"]
    it = next(i for i in items["items"] if i["status"] == "done")
    assert c.get(f"/thumbs/{it['id']}.webp").status_code == 200
    assert c.get(f"/image/{it['id']}").status_code == 200
    heic = [i for i in c.get("/api/items", params={"q": "IMG"}).json()["items"] if i["name"].endswith(".heic")]
    if heic:
        assert c.get(f"/image/{heic[0]['id']}").headers["content-type"] == "image/jpeg"
    assert c.get("/api/items", params={"view": "duplicates"}).json()["total"] >= 3
    assert c.get("/api/items", params={"q": "\"(*"}).status_code == 200  # weird search input is safe

    ex = c.post("/api/export").json()
    assert ex["copied"] == s["total"] and not ex["failed"]
    junk = s["junk"]
    tr = c.post("/api/trash-junk").json()
    assert tr["moved"] == junk and not tr["failed"]
    assert len(list((out / "_Trash").iterdir())) == junk
    s2 = c.get("/api/summary").json()
    assert s2["junk"] == 0 and s2["trashed"] == junk
    assert snapshot(src) == before  # originals untouched

    # second run: everything is cached, much faster
    c.post("/api/scan", json={"folder": str(src)})
    c.post("/api/sort")
    job = wait_done(c)
    assert job.cached == info["count"]
    assert (job.finished - job.started) < first_duration


def test_unreadable_folder_gives_friendly_error(tmp_path, monkeypatch):
    import os
    import pytest
    from app import scanner

    def fake_walk(root, onerror=None):
        onerror(PermissionError(13, "Access is denied", str(root)))
        return iter(())

    monkeypatch.setattr(scanner.os, "walk", fake_walk)
    with pytest.raises(scanner.ScanError, match="No permission"):
        scanner.find_images(str(tmp_path))
