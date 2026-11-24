import pytest

from app.classify import Clip, classify, rule_classify

SAMPLES = {
    "OTPs": [
        "123456 is your OTP for login to HDFC NetBanking. Do not share it with anyone.",
        "Your verification code is 8842. It expires in 10 minutes.",
        "Use one time password 552310 to complete your Amazon sign in. Don't share this code.",
        "Swiggy: 4821 is your OTP. Valid for 5 minutes. Do not share.",
    ],
    "Receipts": [
        "Payment Successful\n₹482 paid to Swiggy\nUPI transaction ID 3141592653\nGoogle Pay",
        "PhonePe\nPaid to Ramesh Kirana\nRs 1,250\nDebited from HDFC Bank\nUTR 402918273645",
        "Paytm\nMoney sent successfully\n₹ 300\nTransaction ID: T2309181234\nUPI Ref",
        "INVOICE #2231\nTotal amount: ₹ 2,499.00\nPaid via UPI\nThank you",
    ],
    "Tickets": [
        "IRCTC\nPNR: 4512398760\nTrain 12951 Rajdhani\nCoach B2 Berth 34\nDeparture 16:55",
        "IndiGo Boarding Pass\nBLR to DEL\nGate 12 Seat 14C\nFlight 6E 2131",
        "BookMyShow\nBooking ID: WLY8K2\nOppenheimer\nScreen 3, Seat H12\nPVR Phoenix",
    ],
    "Shopping": [
        "Amazon\nboAt Rockerz 450\n₹1,299 M.R.P. ₹3,990 67% off\nFREE delivery by Tuesday\nAdd to Cart\nBuy Now",
        "Flipkart\nPrice ₹ 799\n40% off\nDelivery by 24 Nov\nAdd to cart",
        "Myntra\nRoadster Men Shirt\nSize M L XL\n60% off\nAdd to Bag\nWishlist\nprice",
    ],
    "Chats": [
        "Mom\nonline\nDid you eat? 10:42 pm\nYes ma 10:43 pm\nOk good night 10:45 pm\nGood night 10:46 pm",
        "Rahul\nlast seen today at 9:12 am\nbro where are you 9:01 am\ncoming 9:03 am\nhurry 9:05 am",
        "WhatsApp\nOffice group\nPriya: meeting at 3 11:02\nAmit: ok 11:04\nme: noted 11:05\ntyping...",
    ],
    "Addresses": [
        "Flat 402, Sunshine Apartment\nSector 21, Gurugram\nHaryana 122016\nNear City Mall",
        "Google Maps\n12, MG Road, Shanti Nagar\nBengaluru 560027\nDirections\n12 min (3.4 km)",
        "Delivery address\nHouse 15, Lane 4, Indira Nagar\nLucknow, Uttar Pradesh\nPin code 226016",
    ],
    "Recipes": [
        "Paneer Butter Masala recipe\nIngredients\n2 tbsp butter\n1 cup cream\n1 tsp garam masala\nCook 20 minutes",
        "Chocolate cake\nIngredients: 2 cups flour, 1 cup sugar, 1 tsp baking soda\nPreheat oven, bake 35 minutes",
        "Masala chai recipe\n1 cup water, 1 cup milk, 2 tsp tea, ginger\nboil for 5 minutes",
    ],
}

NEGATIVE = [
    "",
    "hello",
    "Settings\nWi-Fi\nBluetooth\nBattery",
    "Good morning have a nice day",
    "lol",
]


@pytest.mark.parametrize("cat,text", [(c, t) for c, ts in SAMPLES.items() for t in ts])
def test_rules_positive(cat, text):
    r = rule_classify(text)
    assert r is not None, text
    assert r[0] == cat, (text, r)
    assert 0 < r[1] <= 1 and r[2].startswith("rule:")


@pytest.mark.parametrize("text", NEGATIVE)
def test_rules_negative(text):
    assert rule_classify(text) is None


def test_long_text_is_notes():
    text = " ".join(["The quarterly review covered strategy hiring and the product roadmap in detail."] * 7)
    assert rule_classify(text)[0] == "Notes"


def test_words_alone_do_not_trigger():
    # 'users' contains 'rs', 'paid' alone is not enough, a lone number isn't an OTP
    assert rule_classify("Our users are happy") is None
    assert rule_classify("Order 123456") is None


def test_classify_falls_back_to_other_without_clip():
    cat, conf, reason = classify("hello", None, None)
    assert cat == "Other" and conf < 0.6


class FakeClip(Clip):
    def __init__(self, result):
        super().__init__()
        self.result = result

    @property
    def enabled(self):
        return True

    def classify(self, img):
        return self.result


def test_clip_used_for_low_text():
    cat, conf, reason = classify("lol", lambda: object(), FakeClip(("Memes", 0.8)))
    assert cat == "Memes" and "image model" in reason


def test_clip_low_confidence_goes_to_other():
    cat, conf, _ = classify("", lambda: object(), FakeClip(("Photos", 0.3)))
    assert cat == "Other"


def test_confident_rule_beats_clip_for_text_heavy():
    text = SAMPLES["Receipts"][0]
    cat, _, _ = classify(text, lambda: object(), FakeClip(("Memes", 0.99)))
    assert cat == "Receipts"


class _FakeClip:
    enabled = True

    def __init__(self, result):
        self.result = result

    def classify(self, img):
        return self.result


@pytest.mark.parametrize("text", ["WHEN THE WIFI\n\nCOMES BACK", "WileN Tle WIFI\n\nCOMES SACK ae", "ME AFTER ONE\nPRODUCTIVE DAY"])
def test_meme_caption_beats_clip_other(text):
    cat, _, reason = classify(text, image_loader=lambda: object(), clip=_FakeClip(("Other", 0.95)))
    assert cat == "Memes", reason


def test_meme_caption_without_clip():
    assert classify("WHEN THE WIFI COMES BACK")[0] == "Memes"


def test_clip_confident_photo_wins_over_caption():
    assert classify("GOA 2024", image_loader=lambda: object(), clip=_FakeClip(("Photos", 0.9)))[0] == "Photos"


@pytest.mark.parametrize("text", ["Settings\nWi-Fi\nBluetooth", "OK", "Battery 82%"])
def test_normal_short_text_not_meme(text):
    assert classify(text)[0] != "Memes"
