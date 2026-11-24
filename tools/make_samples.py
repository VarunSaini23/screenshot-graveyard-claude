"""Generate fake, clearly synthetic phone screenshots for testing (no personal data).

    python -m tools.make_samples OUT_DIR [--n 300]
"""
from __future__ import annotations

import argparse
import os
import random
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEXTS = {
    "Receipts": [
        "Payment Successful\n₹{a} paid to Swiggy\nUPI transaction ID {d10}\nGoogle Pay\n{date}",
        "PhonePe\nPaid to {name} Kirana Store\nRs {a}\nDebited from HDFC Bank\nUTR {d12}",
        "Paytm\nMoney sent successfully\nRs {a}\nTransaction ID T{d10}\nPaid to {name}",
    ],
    "OTPs": [
        "{d6} is your OTP for login\nto {brand} account.\nDo not share it with anyone.",
        "Your verification code is {d4}.\nIt expires in 10 minutes.\nDo not share this code.",
        "Use one time password {d6}\nto complete sign in on {brand}.",
    ],
    "Tickets": [
        "IRCTC e-ticket\nPNR: {d10}\nTrain 12951 Rajdhani\nCoach B2 Berth {s}\nDeparture 16:55",
        "IndiGo Boarding Pass\nBLR to DEL\nGate {s} Seat 14C\nFlight 6E {d4}\nBoarding 07:10",
        "BookMyShow\nBooking ID: {code}\nMovie: Space Story\nScreen 3, Seat H{s}\nPVR {city}",
    ],
    "Shopping": [
        "Amazon\nWireless Earbuds Model {s}\n₹{a} M.R.P. 67% off\nFREE delivery by Tuesday\nAdd to Cart\nBuy Now",
        "Flipkart\nRunning Shoes\nPrice ₹{a}\n40% off\nDelivery by 24 Nov\nAdd to cart",
        "Myntra\nCotton Shirt\nSize M L XL\n60% off  price ₹{a}\nAdd to Bag\nWishlist",
    ],
    "Chats": [
        "{name}\nonline\nDid you eat? 10:42 pm\nYes, just now 10:43 pm\nOk good night 10:45 pm\nGood night 10:46 pm",
        "{name}\nlast seen today at 9:12 am\nwhere are you 9:01 am\ncoming in 5 9:03 am\nhurry up 9:05 am",
        "WhatsApp\nWeekend plans\n{name}: movie at 3? 11:02\nAmit: ok 11:04\nme: done 11:05\ntyping...",
    ],
    "Addresses": [
        "Flat {s}, Sunshine Apartment\nSector 21, Gurugram\nHaryana 122016\nNear City Mall",
        "Google Maps\n12, MG Road, Shanti Nagar\nBengaluru 560027\nDirections\n12 min (3.4 km)",
        "Delivery address\nHouse {s}, Lane 4, Indira Nagar\nLucknow 226016\nPin code 226016",
    ],
    "Recipes": [
        "Paneer Butter Masala recipe\nIngredients\n2 tbsp butter\n1 cup cream\n1 tsp garam masala\nCook 20 minutes",
        "Chocolate Cake\nIngredients\n2 cups flour\n1 cup sugar\n1 tsp baking soda\nPreheat oven, bake 35 minutes",
    ],
    "Notes": [
        "Meeting notes. The team agreed to move the launch to the second week of next month so that "
        "the onboarding flow can be tested with more people. Design will share new screens on Monday and "
        "engineering will estimate the remaining work. Marketing wants a short video and a blog post, and "
        "support needs a help page before launch. We will review progress again on Thursday afternoon.",
    ],
}
NAMES = ["Asha", "Rohan", "Meera", "Kabir", "Isha", "Dev"]
BRANDS = ["Amazon", "HDFC", "Swiggy", "Zomato", "Uber"]
CITIES = ["Phoenix", "Forum", "Orion"]

COLORS = {"Receipts": (236, 252, 240), "OTPs": (255, 255, 255), "Tickets": (245, 240, 255), "Shopping": (255, 248, 238),
          "Chats": (230, 221, 212), "Addresses": (235, 248, 252), "Recipes": (255, 245, 248), "Notes": (250, 250, 250)}


def font(size):
    for f in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def fill(t: str, rnd: random.Random) -> str:
    return t.format(a=f"{rnd.randint(49, 4999):,}", d4=rnd.randint(1000, 9999), d6=rnd.randint(100000, 999999),
                    d10=rnd.randint(10**9, 10**10 - 1), d12=rnd.randint(10**11, 10**12 - 1), s=rnd.randint(1, 60),
                    name=rnd.choice(NAMES), brand=rnd.choice(BRANDS), city=rnd.choice(CITIES),
                    code="".join(rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6)),
                    date=f"{rnd.randint(1, 28)} Nov 2026")


def wrap(text: str, width: int = 34) -> str:
    out = []
    for para in text.split("\n"):
        line = ""
        for w in para.split():
            if len(line) + len(w) + 1 > width:
                out.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        out.append(line)
    return "\n".join(out)


def text_shot(cat: str, rnd: random.Random, variant: int = 0) -> Image.Image:
    img = Image.new("RGB", (720, 1280), COLORS.get(cat, (255, 255, 255)))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 720, 60], fill=(30, 30, 30))
    d.text((24, 16), f"{rnd.randint(1, 12)}:{rnd.randint(10, 59)}", fill=(255, 255, 255), font=font(26))
    d.rectangle([0, 60, 720, 150], fill=tuple(max(0, c - 60) for c in COLORS.get(cat, (200, 200, 200))))
    body = wrap(fill(TEXTS[cat][variant % len(TEXTS[cat])], rnd))
    y = 200
    for line in body.split("\n"):
        d.text((40, y), line, fill=(20, 20, 20), font=font(34))
        y += 52
    # visual variety so perceptual hashes differ between unrelated shots
    for _ in range(4):
        x0, y0 = rnd.randint(0, 600), rnd.randint(700, 1180)
        d.rounded_rectangle([x0, y0, x0 + rnd.randint(60, 200), y0 + rnd.randint(40, 120)], 12,
                            fill=(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    return img


def meme_shot(rnd: random.Random) -> Image.Image:
    img = Image.new("RGB", (720, 900), (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    d = ImageDraw.Draw(img)
    for _ in range(20):
        x, y = rnd.randint(0, 720), rnd.randint(0, 900)
        d.ellipse([x, y, x + rnd.randint(30, 200), y + rnd.randint(30, 200)],
                  fill=(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    d.text((40, 30), "WHEN THE WIFI", fill="white", font=font(60), stroke_width=3, stroke_fill="black")
    d.text((40, 800), "COMES BACK", fill="white", font=font(60), stroke_width=3, stroke_fill="black")
    return img


def make(out: Path, n: int = 300, seed: int = 7) -> dict:
    """Returns {file name: true category}."""
    rnd = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    cats = list(TEXTS) + ["Memes"]
    truth = {}
    now = time.time()
    made = []
    for i in range(n):
        cat = cats[i % len(cats)]
        img = meme_shot(rnd) if cat == "Memes" else text_shot(cat, rnd, i // len(cats))
        name = f"Screenshot_{i:04d}.png"
        if i % 25 == 3:
            name = f"स्क्रीनशॉट {i:04d} copy.png"
        elif i % 9 == 4:
            name = f"Screenshot {i:04d}.jpg"
        p = out / name
        if p.suffix == ".jpg":
            img.save(p, quality=88)
        else:
            img.save(p)
        mt = now - rnd.randint(0, 600) * 86400
        os.utime(p, (mt, mt))
        truth[name] = cat
        made.append((p, img, cat))
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        for k in range(min(6, len(made))):
            p, img, cat = made[k * 7 % len(made)]
            hp = out / f"IMG_{k:03d}.heic"
            img.save(hp, format="HEIF", quality=80)
            truth[hp.name] = cat
    except Exception:
        pass
    for k in range(max(1, n // 20)):
        p, img, cat = made[(k * 13) % len(made)]
        old = now - 400 * 86400
        d1 = out / f"dup_{k:03d}.png"
        img.save(d1)
        os.utime(d1, (old, old))
        truth[d1.name] = cat
        d2 = out / f"dup_{k:03d}_small.jpg"
        img.resize((img.width // 2, img.height // 2)).save(d2, quality=55)
        os.utime(d2, (old, old))
        truth[d2.name] = cat
    (out / "empty.png").write_bytes(b"")
    (out / "corrupt.jpg").write_bytes(b"\xff\xd8\xff garbage not a jpeg" * 10)
    (out / "notes.txt").write_text("not an image")
    return truth


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=300)
    a = ap.parse_args()
    t = make(Path(a.out), a.n)
    import json
    Path(a.out, "..", Path(a.out).name + "-truth.json").resolve().write_text(json.dumps(t, ensure_ascii=False, indent=1), "utf-8")
    print(f"Wrote {len(t) + 2} image files to {a.out}")
