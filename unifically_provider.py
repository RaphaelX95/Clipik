"""ספק הווידאו של Clipik: UnificAlly (מודל Kling 4.0).

המחירים לשנייה לפי הרזולוציה (כולל שמע):
- 720p  (mode="std") : $0.1134 לשנייה
- 1080p (mode="pro") : $0.1701 לשנייה
"""
from __future__ import annotations

import json
import os
import time
from decimal import ROUND_CEILING, Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://api.unifically.com/v1"
MODEL_ID = "kuaishou/kling-4.0-video"

RESOLUTION_MODE = {"720p": "std", "1080p": "pro"}
RATE_PER_SECOND_USD = {"720p": Decimal("0.1134"), "1080p": Decimal("0.1701")}
# 1080p עולה 1.5 פעמים מ-720p, לכן הטוקנים מוכפלים באותו יחס.
RESOLUTION_TOKEN_FACTOR = {"720p": Decimal("1"), "1080p": Decimal("1.5")}
ASPECT_RATIO = {"אנכי · 9:16": "9:16", "ריבוע · 1:1": "1:1", "רחב · 16:9": "16:9"}
ALLOWED_DURATIONS = range(3, 31)
USD_TO_ILS = Decimal("3.45")

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 900


class UnifiError(RuntimeError):
    """שגיאה שניתנת להצגה למשתמש."""


def _api_key() -> str:
    key = os.environ.get("UNIFICALLY_API_KEY", "")
    if not key:
        raise UnifiError("מפתח UnificAlly חסר. הגדירו UNIFICALLY_API_KEY במשתני הסביבה.")
    return key


def validate_options(duration: int, resolution: str) -> tuple[int, str]:
    """בודק משך ורזולוציה. מחזיר את הערכים הנקיים או זורק ValueError."""
    if isinstance(duration, bool):
        raise ValueError("בחרו אורך סרטון תקין")
    try:
        duration = int(duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("בחרו אורך סרטון תקין") from exc
    if duration not in ALLOWED_DURATIONS:
        raise ValueError("אפשר לבחור 3 עד 30 שניות")
    if resolution not in RATE_PER_SECOND_USD:
        raise ValueError("אפשר לבחור 720p או 1080p")
    return duration, resolution


def estimate_cost_usd(duration: int, resolution: str = "720p") -> Decimal:
    """עלות היצירה אצל הספק בדולרים, לפני ניסיונות חוזרים."""
    duration, resolution = validate_options(duration, resolution)
    return (Decimal(duration) * RATE_PER_SECOND_USD[resolution]).quantize(Decimal("0.001"))


_BASE_TOKENS = [(5, 2), (10, 4), (15, 6), (20, 8), (25, 10), (30, 12)]


def estimate_tokens(duration: int, resolution: str = "720p") -> int:
    """מספר הטוקנים שהלקוח משלם על סרטון לפי משך ורזולוציה."""
    duration, resolution = validate_options(duration, resolution)
    base = next(tokens for limit, tokens in _BASE_TOKENS if duration <= limit)
    scaled = Decimal(base) * RESOLUTION_TOKEN_FACTOR[resolution]
    return int(scaled.to_integral_value(rounding=ROUND_CEILING))


def _request(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(
        API_BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise UnifiError(f"UnificAlly החזיר שגיאה ({exc.code}). נסו שוב.") from exc
    except URLError as exc:
        raise UnifiError("לא ניתן להתחבר ל-UnificAlly כרגע. נסו שוב.") from exc


def generate_clip(
    *,
    image_url: str,
    prompt: str,
    duration: int,
    resolution: str = "720p",
    platform: str = "אנכי · 9:16",
    poll_interval: float = POLL_INTERVAL_SECONDS,
    timeout: float = POLL_TIMEOUT_SECONDS,
) -> str:
    """שולח משימה ל-UnificAlly, ממתין לסיום ומחזיר קישור לסרטון."""
    duration, resolution = validate_options(duration, resolution)
    if not image_url.startswith("https://"):
        raise UnifiError("כתובת התמונה חייבת להיות ציבורית (https).")

    created = _request(
        "POST",
        "/tasks",
        {
            "model": MODEL_ID,
            "input": {
                "prompt": prompt,
                "image_urls": [image_url],
                "start_image_index": 1,
                "duration": duration,
                "mode": RESOLUTION_MODE[resolution],
                "aspect_ratio": ASPECT_RATIO.get(platform, "9:16"),
                "native_audio": True,
            },
        },
    )
    task_id = (created.get("data") or {}).get("task_id")
    if not task_id:
        raise UnifiError("UnificAlly לא החזיר מזהה משימה.")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        data = (_request("GET", f"/tasks/{task_id}").get("data") or {})
        status = data.get("status")
        if status == "completed":
            video_url = (data.get("output") or {}).get("video_url")
            if isinstance(video_url, str) and video_url.startswith("https://"):
                return video_url
            raise UnifiError("היצירה הסתיימה בלי קישור לסרטון.")
        if status == "failed":
            raise UnifiError(data.get("error_message") or "היצירה נכשלה. נסו שוב.")
    raise UnifiError("היצירה לוקחת יותר מדי זמן. נסו שוב.")
