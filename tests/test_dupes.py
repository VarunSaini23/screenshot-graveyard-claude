import io

import imagehash
from PIL import Image, ImageDraw

from app.dupes import duplicate_map, find_groups


def make(seed: int, size=(540, 960)) -> Image.Image:
    import random
    rnd = random.Random(seed)
    img = Image.new("RGB", size, (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    d = ImageDraw.Draw(img)
    for _ in range(14):
        x, y = rnd.randint(0, size[0]), rnd.randint(0, size[1])
        d.rectangle([x, y, x + rnd.randint(40, 260), y + rnd.randint(40, 260)],
                    fill=(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    return img


def ph(img):
    return str(imagehash.phash(img))


def jpeg(img, q=60):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=q)
    return Image.open(io.BytesIO(buf.getvalue()))


def test_identical_resized_and_compressed_are_grouped():
    a = make(1)
    items = [
        {"id": 1, "phash": ph(a), "mtime": 100, "ocr": ""},
        {"id": 2, "phash": ph(a.copy()), "mtime": 300, "ocr": ""},
        {"id": 3, "phash": ph(a.resize((270, 480))), "mtime": 200, "ocr": ""},
        {"id": 4, "phash": ph(jpeg(a, 40)), "mtime": 50, "ocr": ""},
    ]
    groups = find_groups(items)
    assert len(groups) == 1 and {i["id"] for i in groups[0]} == {1, 2, 3, 4}
    m = duplicate_map(items)
    assert m == {1: 2, 3: 2, 4: 2}  # newest (id 2) is kept


def test_different_images_not_grouped():
    items = [{"id": i, "phash": ph(make(i + 10)), "mtime": i, "ocr": ""} for i in range(12)]
    assert find_groups(items) == []


def test_lookalike_screens_with_different_text_not_grouped():
    a = make(5)
    t1 = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima"
    t2 = "mike november oscar papa quebec romeo sierra tango uniform victor whiskey xray"
    items = [{"id": 1, "phash": ph(a), "mtime": 1, "ocr": t1}, {"id": 2, "phash": ph(a), "mtime": 2, "ocr": t2}]
    assert find_groups(items) == []


def test_missing_hash_ignored():
    assert find_groups([{"id": 1, "phash": None, "mtime": 1}, {"id": 2, "phash": None, "mtime": 2}]) == []
