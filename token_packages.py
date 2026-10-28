"""קטלוג חבילות הטוקנים של Clipik.

המחיר נקבע בשרת בלבד, לפי מזהה החבילה. הלקוח לא שולח סכום.

- העלות לסרטון מגיעה מ-unifically_provider (דולר לשנייה, כולל שמע).
- מחיר הלקוח = עלות × MARKUP × שער הדולר, אחרי הנחה אם יש מבצע לסוג הסרטון.
- כל חבילה נמכרת כמספר סרטונים מסוג אחד. הטוקנים נשארים המטבע הפנימי,
  לכן אפשר לערבב סוגים כי היתרה היא סכום הטוקנים.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import unifically_provider as _uni

MARKUP = Decimal("1.5")
VIDEO_COUNTS = (1, 5, 10, 15, 20)
VIDEO_TYPES = (
    ("720p", 5), ("720p", 10), ("720p", 15), ("720p", 20), ("720p", 30),
    ("1080p", 5), ("1080p", 10), ("1080p", 15), ("1080p", 20), ("1080p", 30),
)

# מבצעים לפי סוג סרטון: אחוז הנחה מהמחיר הרגיל
PROMOS = {("1080p", 30): Decimal("0.15")}

# הנחה לפי כמות בחבילה (מוכפלת עם מבצע הסוג אם יש). סרטון בודד ללא הנחה.
PACK_DISCOUNTS = {
    1: Decimal("0"),
    5: Decimal("0.05"),
    10: Decimal("0.10"),
    15: Decimal("0.12"),
    20: Decimal("0.15"),
}

TRIAL_PACKAGE_ID = "trial"
TRIAL_TOKENS = 6
TRIAL_PRICE = Decimal("9.99")


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def package_id(resolution: str, duration: int, count: int) -> str:
    return f"{resolution}-{duration}-{count}"


def quote(resolution: str, duration: int, count: int) -> dict:
    """מחזיר טוקנים ומחיר לחבילה. זורק ValueError לבקשה לא תקינה."""
    duration, resolution = _uni.validate_options(duration, resolution)
    if count not in VIDEO_COUNTS:
        raise ValueError("כמות הסרטונים לא נתמכת")
    if (resolution, duration) not in VIDEO_TYPES:
        raise ValueError("סוג הסרטון לא נתמך")

    tokens = _uni.estimate_tokens(duration, resolution) * count
    cost_usd = _uni.RATE_PER_SECOND_USD[resolution] * duration * count
    cost_ils = cost_usd * _uni.USD_TO_ILS
    discount = PROMOS.get((resolution, duration), Decimal("0"))
    pack_discount = PACK_DISCOUNTS[count]
    list_price = _money(cost_ils * MARKUP * (Decimal("1") - discount))
    price = _money(cost_ils * MARKUP * (Decimal("1") - discount) * (Decimal("1") - pack_discount))
    return {
        "package_id": package_id(resolution, duration, count),
        "resolution": resolution,
        "duration": duration,
        "count": count,
        "tokens": tokens,
        "price_ils": price,
        "cost_ils": _money(cost_ils),
        "promo_discount": discount,
        "pack_discount": pack_discount,
        "list_price_ils": list_price,
    }


def lookup(pkg_id: str) -> dict | None:
    """מחזיר את פרטי החבילה לפי מזהה, או None אם המזהה לא מוכר."""
    if pkg_id == TRIAL_PACKAGE_ID:
        return {
            "package_id": TRIAL_PACKAGE_ID,
            "tokens": TRIAL_TOKENS,
            "price_ils": TRIAL_PRICE,
            "cost_ils": None,
            "promo_discount": Decimal("0"),
        }
    parts = pkg_id.split("-")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return None
    try:
        return quote(parts[0], int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def catalog() -> list[dict]:
    """כל החבילות לתצוגה, לפי סוג סרטון וכמות."""
    return [quote(res, dur, n) for res, dur in VIDEO_TYPES for n in VIDEO_COUNTS]
