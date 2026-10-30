#!/usr/bin/env python3
"""Tiny dependency-free local server for the Clipic MVP."""
from __future__ import annotations
import base64
import html
import hashlib
import hmac
import json
import re
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import urlencode
import store as _store
from product_page import render_product_page, clean_images, clean_theme, example_page_html, example_edit_html, template_data, EXAMPLES, HIDEABLE as HIDEABLE_SECTIONS
from decimal import Decimal
import os
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(_Path(__file__).resolve().parent / ".env"), override=False)
except Exception:
    pass
import fal_provider as _fal_provider
import unifically_provider as _uni
import token_packages as _token_packages
import requests as _requests
import product_import as _product_import

ROOT = Path(__file__).resolve().parent
# תיקיית הנתונים (קבצי JSON של משתמשים, פרויקטים ותשלומים). ברירת מחדל: תיקיית הקוד.
DATA_DIR = Path(os.environ.get("DATA_DIR") or ROOT)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA = DATA_DIR / "projects.json"
MAX_BODY = 1_000_000
# דף מוצר יכול לכלול עד 10 תמונות, לכן מגבילים אותו בנפרד
MAX_PRODUCT_BODY = 8_000_000

# Base URL for the application (used for iCount redirects and meta tags)
_BASE_URL = os.environ.get("BASE_URL", f"http://127.0.0.1:{os.environ.get('PORT', '8765')}")

# iCount configuration
_ICOUNT_CID = os.environ.get("ICOUNT_CID", "")
_ICOUNT_USER = os.environ.get("ICOUNT_USER", "")
_ICOUNT_PASS = os.environ.get("ICOUNT_PASS", "")
_ICOUNT_PAGE_ID = os.environ.get("ICOUNT_PAGE_ID", "")
_ANALYTICS_TOKEN = os.environ.get("ANALYTICS_TOKEN", "")


def _analytics_ok(token: str) -> bool:
    return bool(_ANALYTICS_TOKEN) and hmac.compare_digest(str(token), _ANALYTICS_TOKEN)
_ICOUNT_BASE = "https://api.icount.co.il/api/v3.php"
_ICOUNT_SID = None
_ICOUNT_SID_EXIRES = 0

# Deduplication cache for video generation requests
_GENERATION_CACHE: dict[str, float] = {}
_GENERATION_CACHE_TTL = 300  # 5 minutes

# Demo video for free trial users (pre-generated, no cost)
_UPLOAD_DIR = Path(__file__).resolve().parent / "temp_uploads"
_TEMP_IMAGE_RE = re.compile(r"[0-9a-f]{32}\.(png|jpg)")
_DEMO_VIDEO_URL = "https://v3b.fal.media/files/b/0aafe5c3/fAPg5-ZZJpXUy1q3uEUju_output.mp4"


def read_projects():
    data = _store.load("projects", [], DATA_DIR)
    return data if isinstance(data, list) else []


def write_projects(items):
    _store.save("projects", items, DATA_DIR)


def _load_users() -> dict:
    data = _store.load("users", {'users': []}, DATA_DIR)
    return data if isinstance(data, dict) else {'users': []}

def _save_users(data: dict) -> None:
    _store.save("users", data, DATA_DIR)

def _get_user(user_id: str) -> dict | None:
    data = _load_users()
    for user in data.get('users', []):
        if user.get('id') == user_id:
            return user
    return None

_SITE_ICONS = {
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
    "/favicon-48.png": ("favicon-48.png", "image/png"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "/og-image.png": ("og-image.png", "image/png"),
}
_SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
SESSION_COOKIE = "clipik_session"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OTP_TTL = 600          # קוד תקף 10 דקות
_OTP_COOLDOWN = 60     # שליחה חוזרת לאותה כתובת אחרי דקה
_OTP_MAX_TRIES = 5
_OTP_STORE: dict = {}  # email -> {"hash", "exp", "tries", "sent_at"} (בזיכרון, כמו בגרסה שעבדה)
_OTP_LOCK = threading.Lock()


def _otp_get(email: str):
    return _OTP_STORE.get(email)


def _otp_put(email: str, entry: dict) -> None:
    now = time.time()
    for k in [k for k, v in _OTP_STORE.items() if v.get("exp", 0) < now - 3600]:
        _OTP_STORE.pop(k, None)
    _OTP_STORE[email] = entry


def _otp_del(email: str) -> None:
    _OTP_STORE.pop(email, None)


def _otp_hash(email: str, code: str) -> str:
    return hmac.new(_SESSION_SECRET.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def _send_login_code(email: str, code: str) -> bool:
    """שולח את הקוד במייל דרך Resend. מחזיר False אם השליחה נכשלה."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    sender = os.environ.get("MAIL_FROM", "")
    if not (api_key and sender):
        return False
    try:
        r = _requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": sender,
                "to": [email],
                "subject": "קוד ההתחברות שלכם לקליפיק",
                "text": f"קוד ההתחברות שלכם: {code}\nהקוד תקף 10 דקות. אם לא ביקשתם אותו, אפשר להתעלם מההודעה.",
            },
            timeout=15,
        )
        return r.ok
    except Exception:
        return False


def _sign(payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(_SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _unsign(token: str) -> dict | None:
    if not token or "." not in token or not _SESSION_SECRET:
        return None
    raw, sig = token.rsplit(".", 1)
    good = hmac.new(_SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or float(data.get("exp", 0)) < time.time():
        return None
    return data


def _ensure_user(user_id: str, email: str) -> None:
    """יוצר משתמש אם חסר. שגיאת אחסון לא מפילה את ההתחברות: הסשן נחתם בנפרד."""
    try:
        _ensure_user_inner(user_id, email)
    except Exception as exc:
        print(f"[auth] could not save user record: {exc!r}", flush=True)


def _ensure_user_inner(user_id: str, email: str) -> None:
    data = _load_users()
    users = data.setdefault("users", [])
    if any(u.get("id") == user_id for u in users):
        return
    users.append({
        "id": user_id,
        "email": email,
        "tokens": 0,
        "free_trial_used": False,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    _save_users(data)


def _has_enough_tokens(user_id: str, needed: int) -> bool:
    user = _get_user(user_id)
    return bool(user) and int(user.get("tokens", 0)) >= needed


def _update_user_tokens(user_id: str, tokens: int) -> dict:
    data = _load_users()
    for user in data.get('users', []):
        if user.get('id') == user_id:
            user['tokens'] = max(0, int(tokens))
            _save_users(data)
            return user
    return {}


def _has_free_trial_available(user_id: str) -> bool:
    user = _get_user(user_id)
    if not user:
        return False
    # Free trial available if user hasn't used it yet and has exactly 6 tokens
    # (the amount given in the free trial package)
    return user.get('free_trial_used') is False and int(user.get('tokens', 0)) == 6


def _mark_free_trial_used(user_id: str) -> None:
    data = _load_users()
    for user in data.get('users', []):
        if user.get('id') == user_id:
            user['free_trial_used'] = True
            _save_users(data)
            return


def _icount_session() -> str:
    global _ICOUNT_SID, _ICOUNT_SID_EXIRES
    now = datetime.now(timezone.utc).timestamp()
    if _ICOUNT_SID and now < _ICOUNT_SID_EXIRES:
        return _ICOUNT_SID
    try:
        r = _requests.post(
            f"{_ICOUNT_BASE}/auth/login",
            json={"cid": _ICOUNT_CID, "user": _ICOUNT_USER, "pass": _ICOUNT_PASS},
            timeout=15,
        )
        data = r.json()
        if data.get("status") and data.get("sid"):
            _ICOUNT_SID = data["sid"]
            _ICOUNT_SID_EXIRES = now + 900  # 15 minutes
            return _ICOUNT_SID
        print(f"[icount] login failed: status={r.status_code} error={str(data.get('error_description') or data.get('error') or data)[:200]}", flush=True)
    except Exception as exc:
        print(f"[icount] login exception: {exc!r}", flush=True)
    return ""


def _icount_create_payment_link(amount: float, order_id: str, description: str, client_email: str) -> dict:
    """יוצר קישור לדף סליקה ייעודי לעסקה אחת, עם הסכום שנקבע בשרת."""
    sid = _icount_session()
    if not sid:
        return {"error": "iCount session failed"}
    if not _ICOUNT_PAGE_ID:
        return {"error": "ICOUNT_PAGE_ID not set"}
    try:
        payload = {
            "sid": sid,
            "paypage_id": int(_ICOUNT_PAGE_ID),
            "sum": float(amount),
            "x_order_id": order_id,
            "description": description,
            "email": client_email,
        }
        r = _requests.post(f"{_ICOUNT_BASE}/paypage/generate_sale", json=payload, timeout=20)
        data = r.json()
        sale_url = data.get("sale_url", "")
        if sale_url:
            return {"ok": True, "sale_url": sale_url}
        print(f"[icount] generate_sale failed: status={r.status_code} data={str(data)[:300]}", flush=True)
        return {"error": f"iCount: {data.get('error_description') or data.get('error') or 'Failed'}"}
    except Exception as exc:
        print(f"[icount] generate_sale exception: {exc!r}", flush=True)
        return {"error": f"iCount exception: {exc}"}


def _icount_verify_payment(confirmation_code: str, expected_amount: float) -> bool:
    """בודק מול iCount שהתשלום קיים ושהסכום תואם. לא סומכים על ה-IPN לבד."""
    if not confirmation_code:
        return False
    sid = _icount_session()
    if not sid:
        return False
    try:
        r = _requests.post(
            f"{_ICOUNT_BASE}/cc/transactions",
            json={"sid": sid, "confirmation_code": confirmation_code},
            timeout=20,
        )
        data = r.json()
        results = data.get("results_list") or {}
        items = list(results.values()) if isinstance(results, dict) else list(results)
        for tx in items:
            if str(tx.get("confirmation_code", "")) != str(confirmation_code):
                continue
            tx_sum = float(tx.get("sum", tx.get("payment_sum", 0)) or 0)
            return abs(tx_sum - float(expected_amount)) < 0.01
        return False
    except Exception:
        return False



# Simple rate limiting
from collections import defaultdict
import time
_request_counts = defaultdict(list)
def _check_rate_limit(ip):
    now = time.time()
    window = 60
    max_requests = 120  # מספיק לדף אחד עם כמה בקשות API, ועדיין מונע הצפה
    _request_counts[ip] = [t for t in _request_counts[ip] if now - t < window]
    if len(_request_counts[ip]) >= max_requests:
        return False
    _request_counts[ip].append(now)
    return True


def _publish_temp_image(image_bytes, content_type):
    """שומר את תמונת המוצר זמנית כדי ש-UnificAlly יוכל לקרוא אותה מכתובת ציבורית."""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = "png" if content_type == "image/png" else "jpg"
    name = f"{uuid.uuid4().hex}.{ext}"
    path = _UPLOAD_DIR / name
    path.write_bytes(image_bytes)
    return path, f"{_BASE_URL}/uploads/{name}"


def _remove_temp_image(path):
    try:
        path.unlink()
    except FileNotFoundError:
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "ClipicMVP/0.1"

    def _client_ip(self):
        fwd = self.headers.get("X-Forwarded-For", "") if hasattr(self, "headers") else ""
        if fwd:
            return fwd.split(",")[0].strip()[:64]
        return self.client_address[0] if hasattr(self, "client_address") else "unknown"

    def send_json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)


    def _handle_generation(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"error": "Request must be under 1 MB"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                return self.send_json(400, {"error": "Expected a project object"})
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Invalid JSON"})

        uid = self._require_session_user()
        if not uid:
            return

        # מניעת לחיצה כפולה: אותה בקשה של אותו משתמש לא נשלחת פעמיים בתוך 5 דקות.
        # לא מחזירים סרטון של משתמש אחר ולא מנכים טוקנים פעמיים.
        import hashlib
        cache_key = hashlib.md5(
            uid.encode("utf-8") + json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        now = datetime.now(timezone.utc).timestamp()
        if cache_key in _GENERATION_CACHE and now - _GENERATION_CACHE[cache_key] < _GENERATION_CACHE_TTL:
            return self.send_json(409, {"error": "אותה בקשה כבר נשלחה לפני דקות ספורות. בדקו את 'הסרטונים שלי'."})

        # Add to cache
        _GENERATION_CACHE[cache_key] = now
        # Clean old entries in-place to avoid global rebinding
        expired = [k for k, v in _GENERATION_CACHE.items() if now - v >= _GENERATION_CACHE_TTL]
        for k in expired:
            _GENERATION_CACHE.pop(k, None)

        image_data_url = payload.get("image_data_url")
        if not image_data_url or not isinstance(image_data_url, str):
            return self.send_json(400, {"error": "image_data_url is required"})

        try:
            content_type, image_bytes = _fal_provider.validate_image_data_url(image_data_url)
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})

        resolution = str(payload.get("resolution", "720p"))
        try:
            duration, resolution = _uni.validate_options(payload.get("duration", 15), resolution)
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})

        user_id = uid
        tokens_needed = _uni.estimate_tokens(duration, resolution)
        if not _has_enough_tokens(user_id, tokens_needed):
            return self.send_json(402, {"error": "אין מספיק טוקנים. רכשו חבילה כדי ליצור סרטון."})
        
        prompt = payload.get("prompt") or _fal_provider.build_prompt(
            product=payload.get("product", "מוצר לדוגמה"),
            audience=payload.get("audience", ""),
            language=payload.get("language", "עברית"),
            script=payload.get("script", ""),
            style=payload.get("style", "UGC טבעי"),
            segment_index=0,
            segment_count=1,
            creator=payload.get("creator", "דמות AI"),
            ar_effects=json.loads(payload.get("ar_effects", "[]") or "[]"),
        )
        image_path, image_url = _publish_temp_image(image_bytes, content_type)
        try:
            video_url = _uni.generate_clip(
                image_url=image_url,
                prompt=prompt,
                duration=duration,
                resolution=resolution,
                platform=str(payload.get("platform", "אנכי · 9:16")),
            )
        except RuntimeError as exc:
            return self.send_json(500, {"error": str(exc)})
        except Exception as exc:
            return self.send_json(500, {"error": f"Generation failed: {exc}"})
        finally:
            _remove_temp_image(image_path)

        project = {
            "id": uuid.uuid4().hex[:10],
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "product": str(payload.get("product", "מוצר לדוגמה"))[:120],
            "product_url": str(payload.get("product_url", ""))[:500],
            "audience": str(payload.get("audience", ""))[:300],
            "language": str(payload.get("language", "עברית"))[:40],
            "platform": str(payload.get("platform", "אנכי · 9:16"))[:40],
            "duration": str(duration)[:20],
            "resolution": resolution,
            "script": str(payload.get("script", ""))[:750],
            "captions": str(payload.get("captions", ""))[:50],
            "music": str(payload.get("music", "ללא מוזיקה"))[:40],
            "ar_effects": str(payload.get("ar_effects", "[]"))[:200],
            "style": str(payload.get("style", "UGC טבעי"))[:80],
            "creator": str(payload.get("creator", "דמות AI"))[:80],
            "status": "completed",
            "video_url": video_url,
            "user_id": uid,
        }
        # Deduct tokens after successful generation
        user_id = uid
        tokens_required = _uni.estimate_tokens(duration, resolution)
        new_tokens = 0
        user = _get_user(user_id)
        if user:
            new_tokens = max(0, int(user.get('tokens', 0)) - tokens_required)
            _update_user_tokens(user_id, new_tokens)
        
        items = read_projects()
        items.insert(0, project)
        write_projects(items[:2000])
        return self.send_json(201, {"project": project, "video_url": video_url, "tokens_remaining": new_tokens if user else 0, "tokens_spent": tokens_required})

    REDIRECTS = {
        '/templates.html': '/create.html',
        '/tips.html': '/create.html',
        '/product-page.html': '/pricing.html',
        '/packages.html': '/pricing.html',
        '/analytics.html': '/pricing.html',
    }

    def _cookie(self, name):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except Exception:
            return ""
        morsel = jar.get(name)
        return morsel.value if morsel else ""

    def _session(self):
        return _unsign(self._cookie(SESSION_COOKIE))

    def _session_user_id(self):
        sess = self._session()
        return sess["uid"] if sess and sess.get("uid") else None

    def _require_session_user(self):
        """מחזיר מזהה משתמש מהסשן החתום בלבד. בלי סשן עונה 401 ומחזיר None."""
        uid = self._session_user_id()
        if not uid:
            self.send_json(401, {"error": "צריך להתחבר כדי להמשיך."})
        return uid

    def _secure_flag(self):
        return "; Secure" if _BASE_URL.startswith("https://") else ""

    def _redirect(self, location, set_cookies=()):
        self.send_response(302)
        self.send_header("Location", location)
        for cookie in set_cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_small_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 10_000:
                return None
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _safe_call(self, fn):
        """מונע מצב שבו שגיאה בשרת (למשל בשמירה ל-Supabase) מחזירה תשובה ריקה לדפדפן."""
        try:
            return fn()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"[auth] server error in {fn.__name__}: {exc!r}", flush=True)
            try:
                return self.send_json(503, {"error": "שגיאה זמנית בשרת. נסו שוב בעוד רגע."})
            except Exception:
                return None

    def _email_request_code(self):
        """שלב 1: שולחים קוד בן 6 ספרות לאימייל."""
        if not _SESSION_SECRET:
            return self.send_json(503, {"error": "ההתחברות לא הוגדרה עדיין. נסו שוב מאוחר יותר."})
        payload = self._read_small_json()
        if payload is None:
            return self.send_json(400, {"error": "בקשה לא תקינה"})
        email = str(payload.get("email", "")).strip().lower()
        if len(email) > 254 or not _EMAIL_RE.match(email):
            return self.send_json(400, {"error": "נא להזין כתובת אימייל תקינה"})
        now = time.time()
        with _OTP_LOCK:
            last = (_otp_get(email) or {}).get("sent_at", 0)
            if now - last < _OTP_COOLDOWN:
                return self.send_json(429, {"error": "כבר שלחנו קוד. נסו שוב בעוד דקה."})
            code = f"{secrets.randbelow(1_000_000):06d}"
            if not _send_login_code(email, code):
                return self.send_json(503, {"error": "שליחת הקוד נכשלה. נסו שוב מאוחר יותר."})
            _otp_put(email, {"hash": _otp_hash(email, code), "exp": now + _OTP_TTL,
                             "tries": 0, "sent_at": now})
            print(f"[otp] request: code stored for {email}", flush=True)
        return self.send_json(200, {"sent": True})

    def _email_verify_code(self):
        """שלב 2: בודקים את הקוד ופותחים סשן."""
        if not _SESSION_SECRET:
            return self.send_json(503, {"error": "ההתחברות לא הוגדרה עדיין. נסו שוב מאוחר יותר."})
        payload = self._read_small_json()
        if payload is None:
            return self.send_json(400, {"error": "בקשה לא תקינה"})
        email = str(payload.get("email", "")).strip().lower()
        code = re.sub(r"\s", "", str(payload.get("code", "")))
        invalid = {"error": "הקוד לא תקין או שפג תוקפו. בקשו קוד חדש."}
        with _OTP_LOCK:
            entry = _otp_get(email)
            if not entry:
                print(f"[otp] verify: no code stored for {email}", flush=True)
                return self.send_json(400, invalid)
            if time.time() > entry["exp"] or entry["tries"] >= _OTP_MAX_TRIES:
                print(f"[otp] verify: expired or too many tries for {email} (tries={entry['tries']})", flush=True)
                _otp_del(email)
                return self.send_json(400, invalid)
            entry["tries"] += 1
            _otp_put(email, entry)
            if not hmac.compare_digest(entry["hash"], _otp_hash(email, code)):
                print(f"[otp] verify: code mismatch for {email} (try {entry['tries']}, code length {len(code)})", flush=True)
                return self.send_json(400, invalid)
            print(f"[otp] verify: ok for {email}", flush=True)
            _otp_del(email)
        uid = f"email:{email}"
        _ensure_user(uid, email)
        session = _sign({"uid": uid, "exp": time.time() + 30 * 86400})
        cookie = f"{SESSION_COOKIE}={session}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax{self._secure_flag()}"
        body = json.dumps({"user_id": uid, "email": email}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path in self.REDIRECTS:
            self.send_response(301)
            self.send_header("Location", self.REDIRECTS[path])
            self.end_headers()
            return
        if path not in ('/', '/index.html', '/home.html', '/create.html', '/templates.html', '/product-examples.html', '/my-videos.html', '/product-builder.html', '/pricing.html', '/examples.html', '/faq.html', '/login.html', '/payment_success.html', '/payment_failure.html', '/payment_cancel.html', '/template.html', '/sitemap.xml', '/robots.txt', '/google7cfae0c73b4d1768.html', '/logo.svg', '/logo-source.jpg', '/logo.html', '/styles.css', '/favicon.ico', '/favicon-48.png', '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png', '/og-image.png'):
            self.send_error(404, 'Not found')
            return
        body = b''
        if path in ('/', '/index.html', '/home.html'):
            body = (ROOT / 'create.html').read_bytes()
        elif path == '/create.html':
            body = (ROOT / 'create.html').read_bytes()
        elif path == '/templates.html':
            body = (ROOT / 'templates.html').read_bytes()
        elif path == '/product-examples.html':
            body = (ROOT / 'product-examples.html').read_bytes()
        elif path == '/my-videos.html':
            body = (ROOT / 'my-videos.html').read_bytes()
        elif path == '/product-builder.html':
            body = (ROOT / 'product-builder.html').read_bytes()
        elif path == '/pricing.html':
            body = (ROOT / 'pricing.html').read_bytes()
        elif path == '/examples.html':
            body = (ROOT / 'examples.html').read_bytes()
        elif path == '/faq.html':
            body = (ROOT / 'faq.html').read_bytes()
        elif path == '/login.html':
            body = (ROOT / 'login.html').read_bytes()
        elif path == '/payment_success.html':
            body = (ROOT / 'payment_success.html').read_bytes()
        elif path == '/payment_failure.html':
            body = (ROOT / 'payment_failure.html').read_bytes()
        elif path == '/payment_cancel.html':
            body = (ROOT / 'payment_cancel.html').read_bytes()
        elif path == '/sitemap.xml':
            body = (ROOT / 'sitemap.xml').read_bytes()
        elif path == '/robots.txt':
            body = (ROOT / 'robots.txt').read_bytes()
        elif path == '/google7cfae0c73b4d1768.html':
            body = (ROOT / 'google7cfae0c73b4d1768.html').read_bytes()
        elif path == '/logo.svg':
            body = (ROOT / 'logo.svg').read_bytes()
        elif path == '/logo-source.jpg':
            body = (ROOT / 'logo-source.jpg').read_bytes()
        elif path == '/logo.html':
            body = (ROOT / 'logo.html').read_bytes()
        elif path == '/styles.css':
            body = (ROOT / 'styles.css').read_bytes()
        elif path == '/favicon.ico':
            body = b''
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()

    def do_GET(self):
        ip = self._client_ip()
        path = urlparse(self.path).path
        # ההגבלה חלה על ה-API בלבד. דף אחד טוען עשרות קבצים (CSS, JS, תמונות, פונטים),
        # ולכן הגבלה על כל בקשה שברה את העיצוב אצל משתמשים רגילים.
        if path.startswith("/api/") and not _check_rate_limit(ip):
            self.send_json(429, {"error": "Too many requests"})
            return
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "app": "clipic-mvp"})
        if path.startswith("/p/"):
            return self._serve_product_page(path[3:].strip("/"))
        if path.startswith("/api/product-templates/"):
            data = template_data(path[len("/api/product-templates/"):].strip("/"))
            if data is None:
                return self.send_json(404, {"error": "not found"})
            return self.send_json(200, data)
        if path.startswith("/product-examples/") or path.startswith("/product-edit/"):
            if path.startswith("/product-edit/"):
                body = example_edit_html(path[len("/product-edit/"):].strip("/"))
            else:
                body = example_page_html(path[len("/product-examples/"):].strip("/"))
            if body is None:
                return self.send_json(404, {"error": "not found"})
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/auth/logout":
            return self._redirect("/login.html", [f"{SESSION_COOKIE}=; Path=/; Max-Age=0"])
        if path == "/api/auth/me":
            sess = self._session()
            if not sess:
                return self.send_json(401, {"error": "not logged in"})
            uid = sess.get("uid", "")
            row = _get_user(uid) or {}
            return self.send_json(200, {"user_id": uid, "email": row.get("email", ""), "tokens": row.get("tokens", 0)})
        if path == "/api/fal/status":
            configured = bool(os.environ.get("UNIFICALLY_API_KEY"))
            return self.send_json(200, {"configured": configured, "model": _uni.MODEL_ID})
        if path == "/api/projects":
            uid = self._require_session_user()
            if not uid:
                return
            return self.send_json(200, {"projects": [p for p in read_projects() if p.get("user_id") == uid]})
        if path == "/api/users/me":
            user_id = self._require_session_user()
            if not user_id:
                return
            try:
                user = _get_user(user_id)
                if not user and user_id.startswith("email:"):
                    # הסשן תקף אבל רשומת המשתמש לא נשמרה (למשל תקלת אחסון): יוצרים אותה מחדש
                    _ensure_user(user_id, user_id[len("email:"):])
                    user = _get_user(user_id)
            except Exception as exc:
                # האחסון לא זמין: מחזירים לפחות את פרטי ההתחברות מהסשן, כדי שהאתר יציג שאתם מחוברים
                print(f"[auth] user store unavailable: {exc!r}", flush=True)
                email = user_id[len("email:"):] if user_id.startswith("email:") else ""
                return self.send_json(200, {"user": {"id": user_id, "email": email, "tokens": 0, "degraded": True}})
            if not user:
                return self.send_json(404, {"error": "User not found"})
            return self.send_json(200, {"user": user})
        if path == "/template.html":
            body = (ROOT / "template.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/payment/success":
            body = (ROOT / "payment_success.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/payment/failure":
            body = (ROOT / "payment_failure.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/payment/cancel":
            body = "<html><body style='font-family: Arial; text-align: center; padding: 50px; direction: rtl;'><h1>התשלום בוטל</h1><p>החיוב לא בוצע. ניתן לנסות שוב בכל עת.</p><p><a href='/pricing.html'>חזרה למחירון</a></p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if path == "/api/fal/estimate":
            query = parse_qs(urlparse(self.path).query)
            try:
                duration = int(query.get("duration", ["15"])[0])
                resolution = query.get("resolution", ["720p"])[0]
                duration, resolution = _uni.validate_options(duration, resolution)
                cost = _uni.estimate_cost_usd(duration, resolution)
                tokens = _uni.estimate_tokens(duration, resolution)
                cost_ils = float((cost * _uni.USD_TO_ILS).quantize(Decimal("0.01")))
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
            return self.send_json(200, {"estimated_cost_usd": f"{cost:.3f}", "estimated_cost_ils": cost_ils, "tokens_required": tokens, "model": _uni.MODEL_ID, "duration": duration, "resolution": resolution})
        if path in _SITE_ICONS:
            name, ctype = _SITE_ICONS[path]
            data = (ROOT / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/avatars/"):
            name = path.rsplit("/", 1)[-1]
            file_path = ROOT / "avatars" / name
            if not re.fullmatch(r"avatar-(10|[1-9])\.jpg", name) or not file_path.is_file():
                return self.send_error(404, "Not found")
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/uploads/"):
            name = path.rsplit("/", 1)[-1]
            file_path = _UPLOAD_DIR / name
            if not _TEMP_IMAGE_RE.fullmatch(name) or not file_path.is_file():
                return self.send_error(404, "Not found")
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png" if name.endswith(".png") else "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path not in ("/", "/index.html", "/home.html", "/create.html", "/templates.html", "/product-examples.html", "/my-videos.html", "/product-builder.html", "/pricing.html", "/examples.html", "/faq.html", "/login.html", "/payment_success.html", "/payment_failure.html", "/payment_cancel.html", "/template.html", "/sitemap.xml", "/robots.txt", "/google7cfae0c73b4d1768.html", "/logo.svg", "/logo-source.jpg", "/logo.html", "/logo.html", "/styles.css", "/favicon.ico", "/favicon-48.png", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png", "/og-image.png"):
            self.send_error(404, "Not found")
            return
        body = b""
        if path == "/templates.html":
            body = (ROOT / "templates.html").read_bytes()
        if path == "/product-examples.html":
            body = (ROOT / "product-examples.html").read_bytes()
        if path == "/my-videos.html":
            body = (ROOT / "my-videos.html").read_bytes()
        if path == "/product-builder.html":
            body = (ROOT / "product-builder.html").read_bytes()
        if path == "/pricing.html":
            body = (ROOT / "pricing.html").read_bytes()
        if path == "/examples.html":
            body = (ROOT / "examples.html").read_bytes()
        if path == "/faq.html":
            body = (ROOT / "faq.html").read_bytes()
        if path == "/login.html":
            body = (ROOT / "login.html").read_bytes()
        if path == "/create.html":
            body = (ROOT / "create.html").read_bytes()
        if path == "/index.html":
            body = (ROOT / "index.html").read_bytes()
        if path == "/google7cfae0c73b4d1768.html":
            body = (ROOT / "google7cfae0c73b4d1768.html").read_bytes()
        if path == "/logo.svg":
            body = (ROOT / "logo.svg").read_bytes()
        if path == "/logo-source.jpg":
            body = (ROOT / "logo-source.jpg").read_bytes()
        if path == "/logo.html":
            body = (ROOT / "logo.html").read_bytes()
        if path == "/product-page.html":
            body = (ROOT / "product-page.html").read_bytes()
        if path == "/analytics.html":
            body = (ROOT / "analytics.html").read_bytes()
        if path == "/payment_success.html":
            body = (ROOT / "payment_success.html").read_bytes()
        elif path == "/payment_failure.html":
            body = (ROOT / "payment_failure.html").read_bytes()
        elif path == "/payment_cancel.html":
            body = (ROOT / "payment_cancel.html").read_bytes()
        elif path == "/sitemap.xml":
            body = (ROOT / "sitemap.xml").read_bytes()
        elif path == "/robots.txt":
            body = (ROOT / "robots.txt").read_bytes()
        elif path == "/":
            body = (ROOT / "create.html").read_bytes()
        if path == "/my-videos.html":
            body = (ROOT / "my-videos.html").read_bytes()
        if path == "/product-builder.html":
            body = (ROOT / "product-builder.html").read_bytes()
        if path == "/pricing.html":
            body = (ROOT / "pricing.html").read_bytes()
        if path == "/examples.html":
            body = (ROOT / "examples.html").read_bytes()
        if path == "/faq.html":
            body = (ROOT / "faq.html").read_bytes()
        if path == "/login.html":
            body = (ROOT / "login.html").read_bytes()
        if path == "/styles.css":
            body = (ROOT / "styles.css").read_bytes()
        if path == "/favicon.ico":
            body = b''

        # Set correct content type for non-HTML files
        if path == "/sitemap.xml":
            content_type = "application/xml; charset=utf-8"
        elif path == "/robots.txt":
            content_type = "text/plain; charset=utf-8"
        elif path.endswith(".jpg") or path.endswith(".jpeg"):
            content_type = "image/jpeg"
        elif path.endswith(".png"):
            content_type = "image/png"
        elif path.endswith(".svg"):
            content_type = "image/svg+xml"
        elif path.endswith(".ico"):
            content_type = "image/x-icon"
        elif path.endswith(".css"):
            content_type = "text/css; charset=utf-8"
        else:
            content_type = "text/html; charset=utf-8"
        
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        ip = self._client_ip()
        if not _check_rate_limit(ip):
            self.send_json(429, {"error": "Too many requests"})
            return
        path = urlparse(self.path).path
        # ה-IPN של iCount נשלח כטופס (form-urlencoded) משרת לשרת, ולכן לא עובר את בדיקת ה-JSON.
        # הוא מאומת בשרת מול iCount לפני זיכוי טוקנים.
        if path != "/api/icount/ipn" and not self._verify_csrf():
            return self.send_json(403, {"error": "CSRF check failed"})
        if path in ("/api/auth/email/request", "/api/auth/email/verify"):
            return self._safe_call(self._email_request_code if path.endswith("/request") else self._email_verify_code)
        if path == "/api/auth/email/request":
            return self._email_request_code()
        if path == "/api/auth/email/verify":
            return self._email_verify_code()
        if path == "/api/generations":
            return self._handle_generation()
        if path == "/api/script/generate":
            return self._handle_script_generate()
        if path == "/api/product-page":
            return self._handle_product_page()
        if path == "/api/product-page/preview":
            return self._handle_product_preview()
        if path == "/api/product-page/import":
            return self._handle_product_import()
        if path == "/api/analytics/summary":
            token = urlparse(self.path).query.split("token=")[-1].split("&")[0] if "token=" in self.path else ""
            if not _analytics_ok(token):
                return self.send_json(403, {"error": "Forbidden"})
            return self._handle_analytics_summary()
        if path == "/api/analytics/event":
            token = urlparse(self.path).query.split("token=")[-1].split("&")[0] if "token=" in self.path else ""
            if not _analytics_ok(token):
                return self.send_json(403, {"error": "Forbidden"})
            return self._handle_analytics_event()
        if path == "/api/icount/create-payment":
            return self._safe_call(self._handle_icount_payment)
        if path == "/api/icount/ipn":
            return self._handle_icount_ipn()
        if path != "/api/projects":
            self.send_error(404, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"error": "Request too large"})
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Invalid JSON"})
        uid = self._require_session_user()
        if not uid:
            return
        project = {
            "id": uuid.uuid4().hex[:10],
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "product": self._sanitize(payload.get("product", "מוצר לדוגמה"), 120),
            "product_url": self._sanitize(payload.get("product_url", ""), 500),
            "audience": self._sanitize(payload.get("audience", ""), 300),
            "language": self._sanitize(payload.get("language", "עברית"), 40),
            "platform": self._sanitize(payload.get("platform", "אנכי · 9:16"), 40),
            "duration": self._sanitize(payload.get("duration", "15"), 20),
            "script": self._sanitize(payload.get("script", ""), 750),
            "captions": self._sanitize(payload.get("captions", ""), 50),
            "music": self._sanitize(payload.get("music", "ללא מוזיקה"), 40),
            "ar_effects": self._sanitize(payload.get("ar_effects", "[]"), 200),
            "style": self._sanitize(payload.get("style", "UGC טבעי"), 80),
            "creator": self._sanitize(payload.get("creator", "דמות AI"), 80),
            "status": "draft",
            "user_id": uid,
        }
        items = read_projects()
        items.insert(0, project)
        write_projects(items[:2000])
        return self.send_json(201, {"project": project})

    def _serve_product_page(self, slug):
        page = None
        if re.fullmatch(r"[a-f0-9]{8}", slug or ""):
            page = _store.load(f"product_page_{slug}", None, DATA_DIR)
            if not isinstance(page, dict):
                # דפים ישנים נשמרו ברשימה אחת
                legacy = _store.load("product_pages", [], DATA_DIR)
                page = next((p for p in legacy if isinstance(p, dict) and p.get("slug") == slug), None) if isinstance(legacy, list) else None
        if not isinstance(page, dict):
            body = "<!doctype html><html lang='he' dir='rtl'><meta charset='utf-8'><title>הדף לא נמצא</title><body style='font-family:sans-serif;padding:40px'><h1>הדף לא נמצא</h1><p><a href='/'>לאתר קליפיק</a></p></body></html>".encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = render_product_page(page).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _read_product_payload(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > MAX_PRODUCT_BODY:
            return None, (413, {"error": "Request too large"})
        try:
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return None, (400, {"error": "Invalid JSON"})
        if not isinstance(payload, dict):
            return None, (400, {"error": "Invalid JSON"})
        return payload, None

    @staticmethod
    def _build_product_page(payload):
        clean = Handler._sanitize
        items_in = lambda key, limit, max_items: [
            t for t in (clean(i, limit) for i in (payload.get(key) or [])[:max_items] if isinstance(i, str)) if t.strip()
        ]
        reviews = []
        for r in (payload.get("reviews") or [])[:10]:
            if isinstance(r, dict):
                text = clean(r.get("text", ""), 400)
                if text.strip():
                    try:
                        rating = max(1, min(5, int(r.get("rating", 5))))
                    except (TypeError, ValueError):
                        rating = 5
                    reviews.append({"name": clean(r.get("name", ""), 60), "text": text, "rating": rating})
        faq = []
        for f in (payload.get("faq") or [])[:20]:
            if isinstance(f, dict):
                q = clean(f.get("q", ""), 200)
                a = clean(f.get("a", ""), 600)
                if q.strip() and a.strip():
                    faq.append({"q": q, "a": a})
        cta_url = clean(payload.get("cta_url", ""), 500).strip()
        if not cta_url.lower().startswith(("http://", "https://")):
            cta_url = ""
        return {
            "product": clean(payload.get("product", ""), 120),
            "headline": clean(payload.get("headline", ""), 200),
            "price": clean(payload.get("price", ""), 40),
            "description": clean(payload.get("description", ""), 800),
            "cta_text": clean(payload.get("cta_text", ""), 40),
            "cta_url": cta_url,
            "details_title": clean(payload.get("details_title", ""), 80),
            "details": clean(payload.get("details", ""), 2000),
            "specs": clean(payload.get("specs", ""), 1500),
            "hidden": [k for k in (payload.get("hidden") or []) if isinstance(k, str) and k in HIDEABLE_SECTIONS],
            "shipping": clean(payload.get("shipping", ""), 200),
            "images": clean_images(payload.get("images")),
            "benefits": items_in("benefits", 160, 6),
            "reviews": reviews,
            "faq": faq,
            "theme": clean_theme(payload.get("theme")),
        }

    def _handle_product_page(self):
        payload, error = self._read_product_payload()
        if error:
            return self.send_json(*error)
        page = self._build_product_page(payload)
        if not page["product"].strip():
            return self.send_json(400, {"error": "כתבו שם מוצר"})
        slug = uuid.uuid4().hex[:8]
        page.update({
            "id": uuid.uuid4().hex[:10],
            "slug": slug,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        _store.save(f"product_page_{slug}", page, DATA_DIR)
        page_url = f"{_BASE_URL}/p/{slug}"
        return self.send_json(201, {"ok": True, "page": {"slug": slug}, "page_url": page_url})

    def _handle_product_import(self):
        payload, error = self._read_product_payload()
        if error:
            return self.send_json(*error)
        url = payload.get("url")
        try:
            data = _product_import.import_product(url if isinstance(url, str) else "")
        except _product_import.ImportError_ as exc:
            return self.send_json(400, {"error": str(exc)})
        except Exception:
            return self.send_json(502, {"error": "לא הצלחנו לייבא את המוצר מהקישור"})
        return self.send_json(200, data)

    def _handle_product_preview(self):
        payload, error = self._read_product_payload()
        if error:
            return self.send_json(*error)
        edit = "edit=1" in self.path
        return self.send_json(200, {"html": render_product_page(self._build_product_page(payload), edit=edit)})

    def _handle_script_generate(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"error": "Request too large"})
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Invalid JSON"})

        product = self._sanitize(payload.get("product", ""), 120)
        audience = self._sanitize(payload.get("audience", ""), 300)
        style = self._sanitize(payload.get("style", "UGC טבעי"), 80)
        language = self._sanitize(payload.get("language", "he"), 40)
        duration = int(payload.get("duration", 15))

        if not product:
            return self.send_json(400, {"error": "product is required"})

        try:
            result = _fal_provider.generate_script_from_brief(
                product=product,
                audience=audience,
                style=style,
                language=language,
                duration_seconds=duration,
            )
            return self.send_json(200, result)
        except Exception as exc:
            return self.send_json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


    def _handle_analytics_summary(self):
        # Demo summary - in production read from analytics store
        demo = {
            'total_views': 1247,
            'total_videos': 18,
            'total_downloads': 32,
            'total_clicks': 486,
            'weekly': [
                {'day':'א','views':120,'videos':2},
                {'day':'ב','views':98,'videos':1},
                {'day':'ג','views':156,'videos':3},
                {'day':'ד','views':134,'videos':2},
                {'day':'ה','views':210,'videos':4},
                {'day':'ו','views':89,'videos':1},
                {'day':'ש','views':440,'videos':5}
            ],
            'recent_videos': [
                {'name':'סרטון מוצר A','date':'27/10/2026','status':'הושלם','views':124},
                {'name':'סרטון מוצר B','date':'26/10/2026','status':'הושלם','views':89},
                {'name':'סרטון מוצר C','date':'25/10/2026','status':'מעובד','views':45}
            ],
            'recent_products': [
                {'name':'מוצר אלפא','price':'₪199','date':'27/10/2026','downloads':12},
                {'name':'מוצר בטא','price':'₪149','date':'26/10/2026','downloads':8},
                {'name':'מוצר גאמה','price':'₪249','date':'25/10/2026','downloads':7}
            ]
        }
        return self.send_json(200, demo)

    def _handle_analytics_event(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {'error': 'Request too large'})
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {'error': 'Invalid JSON'})

        event_type = self._sanitize(payload.get('type', 'unknown'), 40)
        data = payload.get('data', {})
        # In production: persist to analytics store / database
        print(f'ANALYTICS: {event_type} | {data}')
        return self.send_json(200, {'ok': True})


    def _handle_icount_payment(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"error": "Request too large"})
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Invalid JSON"})

        package_id = self._sanitize(payload.get("package_id", ""), 40)
        user_id = self._session_user_id()
        if not user_id:
            return self.send_json(401, {"error": "צריך להתחבר כדי לרכוש טוקנים."})
        user_email = self._sanitize(payload.get("email", ""), 120)

        # המחיר נקבע בשרת לפי מזהה החבילה. סכום שנשלח מהלקוח מתעלם.
        pkg = _token_packages.lookup(package_id)
        if pkg is None:
            return self.send_json(400, {"error": "Invalid package"})
        tokens = pkg["tokens"]
        amount = float(pkg["price_ils"])

        order_id = secrets.token_urlsafe(16)
        description = f"טוקנים - {tokens} טוקנים (חבילה {package_id})"
        result = _icount_create_payment_link(
            amount=amount,
            order_id=order_id,
            description=description,
            client_email=user_email or "customer@example.com",
        )

        if not result.get("ok"):
            return self.send_json(500, {"error": result.get("error", "Failed")})

        pending = {
            "order_id": order_id,
            "user_id": user_id,
            "package_id": package_id,
            "tokens": tokens,
            "amount": amount,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        pending_list = _store.load("pending_payments", [], DATA_DIR)
        if not isinstance(pending_list, list):
            pending_list = []
        pending_list.append(pending)
        _store.save("pending_payments", pending_list, DATA_DIR)

        return self.send_json(200, {"redirect_url": result["sale_url"], "order_id": order_id})

    def _handle_icount_ipn(self):
        # iCount שולח אישור תשלום. לא סומכים על התוכן לבד: בודקים מול iCount לפני זיכוי.
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > MAX_BODY:
            return self.send_json(200, {"status": "ignored"})
        try:
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            form = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        except Exception:
            return self.send_json(200, {"status": "ignored"})

        order_id = form.get("x_order_id", "")
        confirmation = form.get("confirmation_code", "")
        if not order_id or not confirmation:
            return self.send_json(200, {"status": "ignored"})

        pending_list = _store.load("pending_payments", [], DATA_DIR)
        if not isinstance(pending_list, list):
            pending_list = []
        matched = next((p for p in pending_list if str(p.get("order_id")) == order_id), None)
        if matched is None:
            return self.send_json(200, {"status": "unknown_order"})

        # מניעת זיכוי כפול: אותו אישור תשלום לא נזקף פעמיים
        txs = _store.load("transactions", [], DATA_DIR)
        if not isinstance(txs, list):
            txs = []
        if any(t.get("confirmation") == confirmation for t in txs):
            return self.send_json(200, {"status": "already_credited"})

        if not _icount_verify_payment(confirmation, float(matched.get("amount", 0))):
            return self.send_json(200, {"status": "not_verified"})

        user_id = matched.get("user_id", "")
        tokens_to_add = int(matched.get("tokens", 0))
        user = _get_user(user_id) if user_id else None
        if user:
            new_total = int(user.get("tokens", 0)) + tokens_to_add
            _update_user_tokens(user_id, new_total)

        txs.append({
            "order_id": order_id,
            "user_id": user_id,
            "tokens": tokens_to_add,
            "amount": matched.get("amount"),
            "confirmation": confirmation,
            "status": "paid",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        _store.save("transactions", txs, DATA_DIR)

        remaining = [p for p in pending_list if str(p.get("order_id")) != order_id]
        _store.save("pending_payments", remaining, DATA_DIR)

        return self.send_json(200, {"status": "ok", "tokens_added": tokens_to_add})


    def end_headers(self):
        self._send_security_headers()
        super().end_headers()

    def _send_security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')

    @staticmethod
    def _sanitize(value, max_length=200):
        if value is None:
            return ''
        text = str(value)
        allowed = [chr(10), chr(13), chr(9)]
        text = ''.join(ch for ch in text if ch.isprintable() or ch in allowed)
        return text.strip()[:max_length]

    def _verify_csrf(self):
        ctype = self.headers.get('Content-Type', '')
        return 'application/json' in ctype

if __name__ == "__main__":
    host = os.environ.get("CLIPIC_HOST", os.environ.get("HOST", "0.0.0.0"))
    port = int(os.environ.get("PORT", "8765"))
    address = f"http://{host}:{port}"
    print(f"Clipic MVP running at {address}")
    print("Project drafts are stored in projects.json beside this file.")
    # Only open browser in local development
    if os.environ.get("RENDER") != "true" and os.environ.get("RAILWAY_ENVIRONMENT") is None:
        threading.Timer(0.8, webbrowser.open, args=(address,)).start()
    ThreadingHTTPServer((host, port), Handler).serve_forever()