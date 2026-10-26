"""מודם fal.ai צד-שרתי ל-Klipik MVP."""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import os
import re
import shutil
import subprocess
from decimal import Decimal

MODEL_ID = "kling/v4/image-to-video"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
PROMO_END = dt.date(2026, 10, 31)
PROMO_RATE_768P = Decimal("0.157")
REGULAR_RATE_768P = Decimal("0.157")
TOKEN_PRICE = Decimal("2.70")
USD_TO_ILS = Decimal("3.45")
ALLOWED_DURATIONS = {3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30}


def estimate_tokens(duration: int) -> int:
    if duration <= 5:
        return 2
    if duration <= 10:
        return 4
    if duration <= 15:
        return 6
    if duration <= 20:
        return 8
    if duration <= 25:
        return 10
    return 12

def split_duration(duration: int) -> list[int]:
    """פיצול משך סרטון Finals לקטעי גeneration של עד 15 שניות."""
    if isinstance(duration, bool) or (isinstance(duration, float) and not duration.is_integer()):
        raise ValueError("בחרו אורך סרטון תקין")
    try:
        duration = int(duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("בחרו אורך סרטון תקין") from exc
    if duration not in ALLOWED_DURATIONS:
        raise ValueError("אפשר לבחור 3 עד 30 שניות")
    remaining = duration
    parts: list[int] = []
    while remaining > 15:
        parts.append(15)
        remaining -= 15
    if remaining:
        parts.append(remaining)
    if any(part < 5 or part > 15 for part in parts):
        raise ValueError("אורך הקטע אינו נתמך על ידי מודל הווידאו")
    return parts


def estimate_cost_usd(duration: int, day: dt.date | None = None) -> Decimal:
    """הערכת עלות היצירה (בדולרים) לפי משך הסרטון, לפני ניסיונות ומס."""
    parts = split_duration(duration)
    today = day or dt.date.today()
    rate = PROMO_RATE_768P if today <= PROMO_END else REGULAR_RATE_768P
    return sum((Decimal(part) * rate for part in parts), Decimal("0")).quantize(Decimal("0.001"))


def validate_image_data_url(data_url: str) -> tuple[str, bytes]:
    """פענוח כתובת תמונה JPG/PNG שהועלתה, עם הגבלת גודל."""
    if not isinstance(data_url, str) or "," not in data_url:
        raise ValueError("העלו תמונת מוצר מסוג JPG או PNG")
    header, encoded = data_url.split(",", 1)
    allowed = {
        "data:image/jpeg;base64": "image/jpeg",
        "data:image/png;base64": "image/png",
    }
    content_type = allowed.get(header.lower())
    if content_type is None:
        raise ValueError("אפשר להעלות תמונת JPG או PNG בלבד")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("קובץ התמונה אינו תקין") from exc
    if not data:
        raise ValueError("קובץ התמונה ריק")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("כל תמונה צריכה להיות עד 10MB")
    return content_type, data


def partition_script(script: str, segment_count: int) -> list[str]:
    """חלוקת תסריט לקטעים מעודכנים רצוף, ללא חזרה על שורות."""
    text = " ".join(str(script).split())
    if not text or segment_count < 1:
        raise ValueError("צריך תסריט ולפחות קטע אחד")
    sentences = [part.strip() for part in re.split(r"(?<=[.!?؟])\s+", text) if part.strip()]
    if len(sentences) < segment_count:
        words = text.split()
        chunks = []
        start = 0
        for index in range(segment_count):
            remaining_words = len(words) - start
            remaining_parts = segment_count - index
            take = max(1, (remaining_words + remaining_parts - 1) // remaining_parts)
            chunks.append(" ".join(words[start:start + take]))
            start += take
        return chunks
    chunks = []
    sentence_index = 0
    for index in range(segment_count):
        remaining_sentences = len(sentences) - sentence_index
        remaining_parts = segment_count - index
        if index == segment_count - 1:
            take = remaining_sentences
        else:
            target = sum(len(s.split()) for s in sentences[sentence_index:]) / remaining_parts
            take = 1
            current = len(sentences[sentence_index].split())
            while take < remaining_sentences - (remaining_parts - 1):
                next_words = len(sentences[sentence_index + take].split())
                if abs(current + next_words - target) > abs(current - target):
                    break
                current += next_words
                take += 1
        chunks.append(" ".join(sentences[sentence_index:sentence_index + take]))
        sentence_index += take
    return chunks


def _is_rtl_language(language: str) -> bool:
    label = str(language or "").lower()
    return any(lang in label for lang in ["עברית", "العربية", "רוסית", "ars", "heb", "ru"])


def _fix_rtl_script(script: str, language: str) -> str:
    if not _is_rtl_language(language):
        return script
    # Reverse the script to counteract model reversal
    # Add RTL markers for better model understanding
    reversed_script = script[::-1]
    # Add Unicode RTL markers
    return f"\u200F{reversed_script}\u200F"


def fit_image_to_platform(image_bytes: bytes, platform: str) -> tuple[str, bytes]:
    """התאמת תמונת המוצר לפרופורציה פלטפורמתית ללא חיתוך."""
    label = str(platform or "")
    if "1:1" in label:
        width, height = 1024, 1024
    elif "16:9" in label:
        width, height = 1280, 720
    else:
        width, height = 720, 1280
    executable = shutil.which("ffmpeg")
    if not executable:
        try:
            import imageio_ffmpeg
            executable = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError as exc:
            raise RuntimeError("נדרשת ספריית FFmpeg כדי להתאים את תמונת המוצר") from exc
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white"
    )
    command = [executable, "-hide_banner", "-loglevel", "error", "-f", "image2pipe", "-i", "pipe:0", "-vf", video_filter, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    result = subprocess.run(command, input=image_bytes, capture_output=True, timeout=60)
    if result.returncode or not result.stdout.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10))):
        raise ValueError("לא הצלחנו להתאים את תמונת המוצר לפורמט הסרטון")
    return "image/png", result.stdout


def build_prompt(
    *, product: str, audience: str, language: str, script: str, style: str,
    segment_index: int, segment_count: int, creator: str = "דמות AI",
) -> str:
    """בניית פרומפט UGC מפורט לקטע וידאו אחד, כפוף למוצר ולסגנון."""
    if not script.strip():
        raise ValueError("צריך לכתוב תסריט לפני יצירת הסרטון")
    if segment_index < 0 or segment_index >= segment_count:
        raise ValueError("מספר הקטע אינו תקין")
    spoken_script = partition_script(script, segment_count)[segment_index]
    # Fix RTL text reversal issue in video model
    spoken_script = _fix_rtl_script(spoken_script, language)
    part = f"זה הקטע {segment_index + 1} מתוך {segment_count}. שמור על אותו יוצר וסגנון חזותי."
    delivery = (
        "הצג תמונות מוצר קרובות ללא אדם במצלמה; השתמש בקריינות טבעית."
        if creator == "קריינות"
        else "הצג יוצר AI עקבי אחד שמדבר למצלמה בצורה טבעית UGC."
    )
    return (
        "צור סרטון קצר 9:16 אנכי לפרסומת מוצר UGC, תחושת מצלמה טבעית ביד. "
        "השתמש בתמונת המוצר שסופחה כהפנייה חזותית. אל תשנה צורת המוצר, "
        "צבע, תווית, אריזה או פרטים גלויים אחרים. אל תמציא תכונות מוצר או טענות. "
        "אל תוסיף כתוביות, לוגואים או טקסט כתוב; אלה מתווספים בעריכת הוידאו. "
        f"מוצר: {product[:120]}. קהל: {audience[:300] or 'קונים גנריים'}. "
        f"סגנון: {style[:80]}. {part} "
        f"{delivery} ב-{language}, אמור את התסריט שסופק כדיאלוג מדבר או קריינות: "
        f"{spoken_script[:5000]}"
    )


def generate_clip(*, image_bytes: bytes, content_type: str, prompt: str, duration: int) -> str:
    """העלאת תמונת מוצר וקריאת המודל ליצירת קטע וידאו אחד ב-fal.ai."""
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError("מפתח fal.ai חסר. הגדירו FAL_KEY בקובץ .env המקומי.")
    if duration < 5 or duration > 15:
        raise ValueError("המודל תומך בקטעים של 5–15 שניות")
    try:
        import fal_client
    except ImportError as exc:
        raise RuntimeError("חסרה ספריית fal-client. הפעילו מחדש דרך start.bat להתקנה.") from exc
    image_url = fal_client.upload(
        image_bytes,
        content_type,
        file_name="clipic-product.png" if content_type == "image/png" else "clipic-product.jpg",
    )
    result = fal_client.subscribe(
        MODEL_ID,
        arguments={
            "prompt": prompt,
            "start_image_url": image_url,
            "duration": duration,
            "resolution": "720p",
        },
        with_logs=False,
        client_timeout=900,
    )
    video = result.get("video") if isinstance(result, dict) else None
    url = video.get("url") if isinstance(video, dict) else None
    if not isinstance(url, str) or not url.startswith("https://"):
        raise RuntimeError("fal.ai לא החזיר קישור תקין לסרטון")
    return url
