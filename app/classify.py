"""Classification: keyword rules on OCR text, then OpenCLIP zero-shot for low-text images."""
from __future__ import annotations

import os
import re
import threading

CATEGORIES = ["Receipts", "OTPs", "Chats", "Memes", "Tickets", "Shopping",
              "Addresses", "Recipes", "Notes", "Photos", "Other"]

# Order matters for ties: earlier wins.
PRIORITY = ["OTPs", "Receipts", "Tickets", "Shopping", "Chats", "Addresses", "Recipes"]

KEYWORDS = {
    "OTPs": ["one time password", "one-time password", "verification code", "do not share",
             "don't share", "dont share", "security code", "login code", "otp", "passcode",
             "authentication code", "ओटीपी"],
    "Receipts": ["paid", "payment successful", "payment of", "upi", "transaction id", "txn id",
                 "utr", "gpay", "google pay", "phonepe", "paytm", "debited", "credited", "invoice",
                 "total", "amount", "received", "sent to", "paid to", "bank", "receipt",
                 "भुगतान", "सफल"],
    "Tickets": ["pnr", "boarding pass", "booking id", "seat", "gate", "irctc", "flight",
                "check-in", "web check-in", "bookmyshow", "movie", "screen", "departure",
                "arrival", "coach", "berth", "train", "terminal", "e-ticket", "ticket"],
    "Shopping": ["add to cart", "amazon", "flipkart", "myntra", "meesho", "price", "% off",
                 "delivery by", "buy now", "free delivery", "in stock", "mrp", "wishlist",
                 "size", "ratings", "nykaa", "ajio"],
    "Chats": ["typing...", "typing…", "online", "last seen", "whatsapp", "message", "reply",
              "delivered", "seen", "telegram", "today", "yesterday", "forwarded"],
    "Addresses": ["pin code", "pincode", "road", "nagar", "sector", "google maps", "directions",
                  "colony", "street", "lane", "near", "floor", "flat", "apartment", "block",
                  "landmark", "km", "marg"],
    "Recipes": ["ingredients", "tbsp", "tsp", "cup", "cups", "recipe", "minutes", "teaspoon",
                "tablespoon", "bake", "preheat", "chopped", "salt", "boil", "simmer"],
}

STRONG = {
    "OTPs": {"otp", "one time password", "one-time password", "verification code", "ओटीपी"},
    "Receipts": {"payment successful", "transaction id", "utr", "upi", "paid to", "debited"},
    "Tickets": {"pnr", "boarding pass", "booking id", "irctc", "bookmyshow", "e-ticket"},
    "Shopping": {"add to cart", "buy now", "delivery by", "% off"},
    "Chats": {"last seen", "typing...", "typing…", "whatsapp"},
    "Addresses": {"google maps", "pin code", "pincode", "directions"},
    "Recipes": {"ingredients", "recipe", "tbsp", "tsp"},
}

THRESHOLD = {"OTPs": 2, "Receipts": 2, "Tickets": 2, "Shopping": 2, "Chats": 2,
             "Addresses": 2, "Recipes": 2}

_kw_re_cache: dict[str, re.Pattern] = {}

CURRENCY = re.compile(r"₹\s?\d|\brs\.?\s?\d|\binr\s?\d|\$\s?\d")
CODE = re.compile(r"(?<![\d.,₹])\b\d{4,8}\b(?![.,]\d)")
TIMESTAMP = re.compile(r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d\s?(?:am|pm)?\b")
PIN = re.compile(r"\b[1-9]\d{2}\s?\d{3}\b")
PNR = re.compile(r"\bpnr\W{0,5}\d{10}\b")


def _has(text: str, kw: str) -> bool:
    pat = _kw_re_cache.get(kw)
    if pat is None:
        pre = r"(?<![a-z0-9])" if kw[0].isalnum() else ""
        post = r"(?![a-z0-9])" if kw[-1].isalnum() else ""
        pat = re.compile(pre + re.escape(kw) + post)
        _kw_re_cache[kw] = pat
    return pat.search(text) is not None


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or "", flags=re.UNICODE))


def rule_scores(text: str) -> dict[str, tuple[int, list[str]]]:
    t = (text or "").lower()
    out: dict[str, tuple[int, list[str]]] = {}
    for cat, kws in KEYWORDS.items():
        hits = [k for k in kws if _has(t, k)]
        score = sum(2 if k in STRONG.get(cat, ()) else 1 for k in hits)
        out[cat] = (score, hits)

    def bump(cat, n, label):
        s, h = out[cat]
        out[cat] = (s + n, h + [label])

    if CURRENCY.search(t):
        bump("Receipts", 1, "currency amount")
        bump("Shopping", 1, "currency amount")
    if out["OTPs"][0] and CODE.search(t):
        bump("OTPs", 2, "numeric code")
    if PNR.search(t):
        bump("Tickets", 2, "PNR number")
    stamps = len(TIMESTAMP.findall(t))
    if stamps >= 3:
        bump("Chats", 2 + min(stamps - 3, 3), f"{stamps} timestamps")
    if PIN.search(t) and out["Addresses"][0]:
        bump("Addresses", 1, "PIN code")
    return out


def rule_classify(text: str) -> tuple[str, float, str] | None:
    """Return (category, confidence, reason) or None if no rule is confident."""
    text = text or ""
    scores = rule_scores(text)
    best = None
    for cat in PRIORITY:
        s, hits = scores[cat]
        if s >= THRESHOLD[cat] and (best is None or s > best[1]):
            best = (cat, s, hits)
    if best:
        cat, s, hits = best
        conf = min(0.99, 0.5 + 0.08 * s)
        return cat, round(conf, 2), "rule: " + ", ".join(dict.fromkeys(hits))[:120]
    if word_count(text) > 60:
        return "Notes", 0.7, "rule: long text (>60 words)"
    return None


# ---------------------------------------------------------------- OpenCLIP
CLIP_PROMPTS = [
    ("a meme with a funny image and caption", "Memes"),
    ("a screenshot of a chat conversation on a phone", "Chats"),
    ("a photo of people or a place", "Photos"),
    ("a screenshot of an app screen", "Other"),
]
CLIP_ACCEPT = 0.45


class Clip:
    def __init__(self):
        self._lock = threading.Lock()
        self._model = None
        self._failed = False
        self.error = ""

    @property
    def enabled(self) -> bool:
        return os.environ.get("SG_DISABLE_CLIP") != "1" and not self._failed

    def available(self) -> bool:
        if not self.enabled:
            return False
        try:
            import importlib.util
            return importlib.util.find_spec("open_clip") is not None and importlib.util.find_spec("torch") is not None
        except Exception:
            return False

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):
        import open_clip
        import torch
        dev = "cpu"
        if torch.backends.mps.is_available():
            dev = "mps"
        elif torch.cuda.is_available():
            dev = "cuda"
        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
        tok = open_clip.get_tokenizer("ViT-B-32")
        model = model.to(dev).eval()
        with torch.no_grad():
            tf = model.encode_text(tok([p for p, _ in CLIP_PROMPTS]).to(dev))
            tf = tf / tf.norm(dim=-1, keepdim=True)
        self._model = (model, preprocess, tf, dev)

    def classify(self, img) -> tuple[str, float] | None:
        if not self.enabled:
            return None
        with self._lock:
            try:
                if self._model is None:
                    self._load()
                import torch
                model, preprocess, tf, dev = self._model
                with torch.no_grad():
                    x = preprocess(img.convert("RGB")).unsqueeze(0).to(dev)
                    f = model.encode_image(x)
                    f = f / f.norm(dim=-1, keepdim=True)
                    probs = (100.0 * f @ tf.T).softmax(dim=-1)[0].tolist()
            except Exception as e:
                self._failed = True
                self.error = str(e)[:200]
                return None
        i = max(range(len(probs)), key=probs.__getitem__)
        return CLIP_PROMPTS[i][1], float(probs[i])


def looks_like_meme_caption(text: str) -> bool:
    """Short text that is mostly ALL-CAPS words, like a classic top/bottom meme caption."""
    toks = re.findall(r"[A-Za-z]{2,}", text)
    if len(toks) < 2 or len(toks) > 25:
        return False
    caps = [t for t in toks if t.isupper()]
    return len(caps) >= 2 and len(caps) / len(toks) >= 0.5


def classify(text: str, image_loader=None, clip: Clip | None = None) -> tuple[str, float, str]:
    """Full local pipeline (rules, then CLIP). `image_loader` returns a PIL image lazily."""
    words = word_count(text)
    r = rule_classify(text)
    if r and words >= 8:
        return r
    caption = r is None and looks_like_meme_caption(text)
    meme = ("Memes", 0.6, "rule: short all-caps caption")
    if clip is not None and image_loader is not None and clip.enabled:
        try:
            img = image_loader()
        except Exception:
            img = None
        res = clip.classify(img) if img is not None else None
        if res:
            cat, p = res
            if r and r[1] >= p:
                return r
            if caption and (cat == "Other" or p < CLIP_ACCEPT):
                return meme
            if p >= CLIP_ACCEPT:
                return cat, round(p, 2), f"image model: {cat.lower()} ({p:.0%})"
            if r:
                return r
            return "Other", round(p, 2), f"image model unsure (best guess {cat.lower()} {p:.0%})"
    if r:
        return r
    if caption:
        return meme
    return "Other", 0.3, "no rule matched" + (" (little text)" if words < 8 else "")
