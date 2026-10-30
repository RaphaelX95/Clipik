"""מייצר 8 דמויות AI לבחירה בעמוד יצירת הסרטון, בעזרת Gemini.

שימוש (המפתח נקרא רק מהמשתנה הסביבתי GEMINI_API_KEY, לא נשמר בקובץ):
    GEMINI_API_KEY=... python3 scripts/generate_avatars.py
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "gemini-2.5-flash-image"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
OUT_DIR = Path(__file__).resolve().parent.parent / "avatars"

BASE = (
    "Realistic photo portrait of one person, head and shoulders, facing the camera, "
    "soft natural light, plain neutral background, friendly expression, "
    "looks like a real customer recording a casual UGC testimonial on a phone. "
    "No text, no logos, no watermark."
)

AVATARS = [
    ("avatar-1", "young woman, 24, curly dark hair, casual white t-shirt"),
    ("avatar-2", "man, 30, short beard, navy hoodie"),
    ("avatar-3", "woman, 35, straight blonde hair, light blue blouse"),
    ("avatar-4", "man, 42, short gray hair, olive green shirt"),
    ("avatar-5", "woman, 28, long dark hair in a bun, beige knit sweater"),
    ("avatar-6", "young man, 21, short black hair, streetwear jacket"),
    ("avatar-7", "woman, 50, short silver hair, cream linen shirt"),
    ("avatar-8", "man, 33, glasses, rolled-up sleeves, white shirt"),
]


def generate(api_key: str, description: str) -> bytes:
    body = {
        "contents": [{"parts": [{"text": f"{BASE} Person: {description}."}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError("התשובה לא הכילה תמונה: " + json.dumps(data, ensure_ascii=False)[:300])


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("חסר המשתנה GEMINI_API_KEY", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name, desc in AVATARS:
        target = OUT_DIR / f"{name}.png"
        if target.exists():
            print(f"{name}: כבר קיים, מדלגים")
            ok += 1
            continue
        try:
            target.write_bytes(generate(api_key, desc))
            print(f"{name}: נוצר")
            ok += 1
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            print(f"{name}: נכשל, HTTP {exc.code}: {detail}", file=sys.stderr)
        except Exception as exc:  # שגיאת רשת או תשובה לא צפויה
            print(f"{name}: נכשל: {exc}", file=sys.stderr)
    print(f"נוצרו {ok} מתוך {len(AVATARS)} דמויות")
    return 0 if ok == len(AVATARS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
