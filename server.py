#!/usr/bin/env python3
"""Tiny dependency-free local server for the Clipic MVP."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import urlencode
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

ROOT = Path(__file__).resolve().parent
# תיקיית הנתונים (קבצי JSON של משתמשים, פרויקטים ותשלומים). ברירת מחדל: תיקיית הקוד.
DATA_DIR = Path(os.environ.get("DATA_DIR") or ROOT)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA = DATA_DIR / "projects.json"
MAX_BODY = 1_000_000

# Base URL for the application (used for iCount redirects and meta tags)
_BASE_URL = os.environ.get("BASE_URL", f"http://127.0.0.1:{os.environ.get('PORT', '8765')}")

# iCount configuration
_ICOUNT_CID = os.environ.get("ICOUNT_CID", "")
_ICOUNT_USER = os.environ.get("ICOUNT_USER", "")
_ICOUNT_PASS = os.environ.get("ICOUNT_PASS", "")
_ICOUNT_PAGE_ID = os.environ.get("ICOUNT_PAGE_ID", "")
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
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_projects(items):
    tmp = DATA.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA)


_USERS_PATH = DATA_DIR / 'users.json'

def _load_users() -> dict:
    if not _USERS_PATH.exists():
        return {'users': []}
    try:
        return json.loads(_USERS_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {'users': []}

def _save_users(data: dict) -> None:
    _USERS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def _get_user(user_id: str) -> dict | None:
    data = _load_users()
    for user in data.get('users', []):
        if user.get('id') == user_id:
            return user
    return None

_SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
SESSION_COOKIE = "clipik_session"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    except Exception:
        pass
    return ""


def _icount_create_payment_link(amount: float, description: str, client_name: str, client_email: str) -> dict:
    sid = _icount_session()
    if not sid:
        return {"error": "iCount session failed"}
    try:
        payload = {
            "sid": sid,
            "doctype": "receipt",
            "client_name": client_name,
            "email": client_email,
            "currency_code": "ILS",
            "lang": "he",
            "items": [
                {"description": description, "quantity": 1, "unitprice": float(amount)}
            ],
            "cc": {
                "sum": str(amount),
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "num_of_payments": 1,
                "first_payment": str(amount),
                "card_type": "VISA",
                "card_number": "0000",
                "exp_year": datetime.now().year + 1,
                "exp_month": 12,
                "holder_id": "000000000",
                "holder_name": client_name or "Customer",
                "confirmation_code": "pending",
            },
        }
        r = _requests.post(f"{_ICOUNT_BASE}/doc/create", json=payload, timeout=20)
        data = r.json()
        if data.get("status"):
            doc_url = data.get("doc_url", "")
            cc_page = data.get("cc_page_url", "")
            return {
                "ok": True,
                "docnum": data.get("docnum"),
                "doc_url": doc_url,
                "cc_page_url": cc_page or doc_url,
            }
        return {"error": data.get("error_description", "Failed")}
    except Exception as exc:
        return {"error": str(exc)}



# Simple rate limiting
from collections import defaultdict
import time
_request_counts = defaultdict(list)
def _check_rate_limit(ip):
    now = time.time()
    window = 60
    max_requests = 10
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

        # Deduplication: check if this exact request was already made recently
        import hashlib
        cache_key = hashlib.md5(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        
        now = datetime.now(timezone.utc).timestamp()
        if cache_key in _GENERATION_CACHE:
            cached_time = _GENERATION_CACHE[cache_key]
            if now - cached_time < _GENERATION_CACHE_TTL:
                # Return the most recent project with same parameters
                projects = read_projects()
                for project in projects:
                    if project.get("status") == "completed":
                        return self.send_json(200, {
                            "project": project,
                            "video_url": project.get("video_url"),
                            "tokens_remaining": 149,  # Approximate
                            "tokens_spent": 6,
                            "cached": True
                        })
        
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

        user_id = self._session_user_id() or payload.get('user_id', 'demo-user')
        tokens_needed = _uni.estimate_tokens(duration, resolution)
        if not _has_enough_tokens(user_id, tokens_needed):
            return self.send_json(402, {"error": "אין מספיק טוקנים. רכשו חבילה כדי ליצור סרטון."})
        
        # Check if user can use free trial (demo video instead of real generation)
        if _has_free_trial_available(user_id):
            _mark_free_trial_used(user_id)
            tokens_required = _uni.estimate_tokens(duration, resolution)
            user = _get_user(user_id)
            new_tokens = 0
            if user:
                new_tokens = max(0, int(user.get('tokens', 0)) - tokens_required)
                _update_user_tokens(user_id, new_tokens)
            
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
                "status": "completed",
                "video_url": _DEMO_VIDEO_URL,
                "demo": True,
            }
            items = read_projects()
            items.insert(0, project)
            write_projects(items[:100])
            return self.send_json(201, {
                "project": project,
                "video_url": _DEMO_VIDEO_URL,
                "tokens_remaining": new_tokens if user else 0,
                "tokens_spent": tokens_required,
                "demo": True,
                "message": "סרטון הדגמה מוכן! רוצים סרטון אמיתי? קנו טוקנים",
            })

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
        }
        # Deduct tokens after successful generation
        user_id = self._session_user_id() or payload.get('user_id', 'demo-user')
        tokens_required = _uni.estimate_tokens(duration, resolution)
        user = _get_user(user_id)
        if user:
            new_tokens = max(0, int(user.get('tokens', 0)) - tokens_required)
            _update_user_tokens(user_id, new_tokens)
        
        items = read_projects()
        items.insert(0, project)
        write_projects(items[:100])
        return self.send_json(201, {"project": project, "video_url": video_url, "tokens_remaining": new_tokens if user else 0, "tokens_spent": tokens_required})

    REDIRECTS = {
        '/templates.html': '/create.html',
        '/tips.html': '/create.html',
        '/product-page.html': '/packages.html',
        '/analytics.html': '/packages.html',
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

    def _secure_flag(self):
        return "; Secure" if _BASE_URL.startswith("https://") else ""

    def _redirect(self, location, set_cookies=()):
        self.send_response(302)
        self.send_header("Location", location)
        for cookie in set_cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _email_login(self):
        """התחברות עם אימייל בלבד (בלי סיסמה). מייצר סשן חתום ל-30 יום."""
        if not _SESSION_SECRET:
            return self.send_json(503, {"error": "ההתחברות לא הוגדרה עדיין. נסו שוב מאוחר יותר."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 10_000:
                return self.send_json(400, {"error": "בקשה לא תקינה"})
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "בקשה לא תקינה"})
        email = str((payload or {}).get("email", "")).strip().lower()
        if len(email) > 254 or not _EMAIL_RE.match(email):
            return self.send_json(400, {"error": "נא להזין כתובת אימייל תקינה"})
        uid = f"email:{email}"
        _ensure_user(uid, email)
        session = _sign({"uid": uid, "exp": time.time() + 30 * 86400})
        cookie = f"{SESSION_COOKIE}={session}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax{self._secure_flag()}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", cookie)
        body = json.dumps({"user_id": uid, "email": email}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path in REDIRECTS:
            self.send_response(301)
            self.send_header('Location', REDIRECTS[path])
            self.end_headers()
            return
        if path not in ('/', '/index.html', '/home.html', '/create.html', '/templates.html', '/my-videos.html', '/product-builder.html', '/pricing.html', '/examples.html', '/faq.html', '/login.html', '/packages.html', '/payment_success.html', '/payment_failure.html', '/payment_cancel.html', '/sitemap.xml', '/robots.txt', '/google7cfae0c73b4d1768.html', '/logo.svg', '/logo-source.jpg', '/logo.html', '/styles.css', '/favicon.ico'):
            self.send_error(404, 'Not found')
            return
        body = b''
        if path in ('/', '/index.html', '/home.html'):
            body = (ROOT / 'create.html').read_bytes()
        elif path == '/create.html':
            body = (ROOT / 'create.html').read_bytes()
        elif path == '/templates.html':
            body = (ROOT / 'templates.html').read_bytes()
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
        elif path == '/packages.html':
            body = (ROOT / 'packages.html').read_bytes()
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
        self._send_security_headers()
        self.end_headers()

    def do_GET(self):
        ip = self.client_address[0] if hasattr(self, "client_address") else "unknown"
        path = urlparse(self.path).path
        # ההגבלה חלה על ה-API בלבד. דף אחד טוען עשרות קבצים (CSS, JS, תמונות, פונטים),
        # ולכן הגבלה על כל בקשה שברה את העיצוב אצל משתמשים רגילים.
        if path.startswith("/api/") and not _check_rate_limit(ip):
            self.send_json(429, {"error": "Too many requests"})
            return
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "app": "clipic-mvp"})
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
            return self.send_json(200, {"projects": read_projects()})
        if path == "/api/users/me":
            user_id = self._session_user_id() or self.headers.get('X-User-Id', 'demo-user')
            user = _get_user(user_id)
            if not user:
                return self.send_json(404, {"error": "User not found"})
            return self.send_json(200, {"user": user})
        if path == "/payment/success":
            body = "<html><body style='font-family: Arial; text-align: center; padding: 50px; direction: rtl;'><h1>תשלום בוצע בהצלחה!</h1><p>הטוקנים יתווספו לחשבונכם shortly.</p><p><a href='/'>חזרה לאתר</a></p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if path == "/payment/failure":
            body = "<html><body style='font-family: Arial; text-align: center; padding: 50px; direction: rtl;'><h1>תשלום נכשל</h1><p>לא הצלחנו לבצע את התשלום. נסו שוב או צרו קשר.</p><p><a href='/packages.html'>חזרה לחבילות</a></p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if path == "/payment/cancel":
            body = "<html><body style='font-family: Arial; text-align: center; padding: 50px; direction: rtl;'><h1>התשלום בוטל</h1><p>החיוב לא בוצע. ניתן לנסות שוב בכל עת.</p><p><a href='/packages.html'>חזרה לחבילות</a></p></body></html>"
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
        if path not in ("/", "/index.html", "/home.html", "/create.html", "/templates.html", "/my-videos.html", "/product-builder.html", "/pricing.html", "/examples.html", "/faq.html", "/login.html", "/packages.html", "/payment_success.html", "/payment_failure.html", "/payment_cancel.html", "/sitemap.xml", "/robots.txt", "/google7cfae0c73b4d1768.html", "/logo.svg", "/logo-source.jpg", "/logo.html", "/logo.html", "/styles.css", "/favicon.ico"):
            self.send_error(404, "Not found")
            return
        body = b""
        if path == "/templates.html":
            body = (ROOT / "templates.html").read_bytes()
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
        if path == "/packages.html":
            body = (ROOT / "packages.html").read_bytes()
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
        ip = self.client_address[0] if hasattr(self, "client_address") else "unknown"
        if not _check_rate_limit(ip):
            self.send_json(429, {"error": "Too many requests"})
            return
        if not self._verify_csrf():
            return self.send_json(403, {"error": "CSRF check failed"})
        path = urlparse(self.path).path
        if path == "/api/auth/email":
            return self._email_login()
        if path == "/api/generations":
            return self._handle_generation()
        if path == "/api/script/generate":
            return self._handle_script_generate()
        if path == "/api/product-page":
            return self._handle_product_page()
        if path == "/api/analytics/summary":
            token = urlparse(self.path).query.split("token=")[-1].split("&")[0] if "token=" in self.path else ""
            if token != "YO4DfXieWO5axgFYUleauA":
                return self.send_json(403, {"error": "Forbidden"})
            return self._handle_analytics_summary()
        if path == "/api/analytics/event":
            token = urlparse(self.path).query.split("token=")[-1].split("&")[0] if "token=" in self.path else ""
            if token != "YO4DfXieWO5axgFYUleauA":
                return self.send_json(403, {"error": "Forbidden"})
            return self._handle_analytics_event()
        if path == "/api/icount/create-payment":
            return self._handle_icount_payment()
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
        }
        items = read_projects()
        items.insert(0, project)
        write_projects(items[:100])
        return self.send_json(201, {"project": project})

    def _handle_product_page(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"error": "Request too large"})
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Invalid JSON"})

        product = self._sanitize(payload.get("product", "מוצר לדוגמה"), 120)
        product_url = self._sanitize(payload.get("product_url", ""), 500)
        headline = self._sanitize(payload.get("headline", product), 200)
        description = self._sanitize(payload.get("description", ""), 500)
        bullets = [self._sanitize(b, 120) for b in payload.get("bullets", [])][:8]
        cta_text = self._sanitize(payload.get("cta_text", "קנו עכשיו"), 80)
        cta_url = self._sanitize(payload.get("cta_url", product_url or "/packages.html"), 200)
        style = self._sanitize(payload.get("style", "UGC טבעי"), 80)
        video_url = self._sanitize(payload.get("video_url", ""), 500)

        page = {
            "id": uuid.uuid4().hex[:10],
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "product": product,
            "product_url": product_url,
            "headline": headline,
            "description": description,
            "bullets": bullets,
            "cta_text": cta_text,
            "cta_url": cta_url,
            "style": style,
            "video_url": video_url,
            "slug": uuid.uuid4().hex[:8],
        }
        pages_path = DATA_DIR / "product_pages.json"
        try:
            pages = json.loads(pages_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            pages = []
        pages.insert(0, page)
        pages_path.write_text(json.dumps(pages[:100], ensure_ascii=False, indent=2), encoding="utf-8")
        page_url = f"{_BASE_URL}/p/{page['slug']}"
        return self.send_json(201, {"ok": True, "page": page, "page_url": page_url})

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
        user_id = self._session_user_id() or self._sanitize(payload.get("user_id", "demo-user"), 40)
        user_email = self._sanitize(payload.get("email", ""), 120)

        # המחיר נקבע בשרת לפי מזהה החבילה. סכום שנשלח מהלקוח מתעלם.
        pkg = _token_packages.lookup(package_id)
        if pkg is None:
            return self.send_json(400, {"error": "Invalid package"})
        tokens = pkg["tokens"]
        amount = float(pkg["price_ils"])

        description = f"טוקנים - {tokens} טוקנים (חבילה {package_id})"
        result = _icount_create_payment_link(
            amount=amount,
            description=description,
            client_name=user_id,
            client_email=user_email or "customer@example.com",
        )

        if result.get("ok"):
            # Store pending payment
            pending = {
                "user_id": user_id,
                "package_id": package_id,
                "tokens": tokens,
                "amount": amount,
                "docnum": result.get("docnum"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            pending_file = DATA_DIR / "pending_payments.json"
            pending_list = []
            if pending_file.exists():
                try:
                    pending_list = json.loads(pending_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            pending_list.append(pending)
            pending_file.write_text(json.dumps(pending_list, ensure_ascii=False, indent=2), encoding="utf-8")

            # Build redirect URL with our success/failure URLs
            cc_url = result.get("cc_page_url", result.get("doc_url", ""))
            sep = "&" if "?" in cc_url else "?"
            redirect_url = (
                f"{cc_url}{sep}"
                f"success_url={_BASE_URL}/payment/success&"
                f"failure_url={_BASE_URL}/payment/failure&"
                f"cancel_url={_BASE_URL}/payment/cancel&"
                f"ipn_url={_BASE_URL}/api/icount/ipn"
            )
            return self.send_json(200, {"redirect_url": redirect_url, "docnum": result.get("docnum")})
        else:
            return self.send_json(500, {"error": result.get("error", "Failed")})

    def _handle_icount_ipn(self):
        # iCount sends form data with payment confirmation
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return self.send_json(200, {"status": "ok"})
        try:
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            data = {}
            for pair in raw.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    data[k] = v
        except Exception:
            return self.send_json(200, {"status": "ok"})

        # Verify minimum required fields
        docnum = data.get("docnum") or data.get("doc_number") or data.get("doc")
        confirmation = data.get("confirmation_code") or data.get("confirmation") or ""
        amount = data.get("sum") or data.get("amount") or "0"
        customer_id = data.get("customer_id") or data.get("client_id") or ""

        if not docnum:
            return self.send_json(200, {"status": "ok"})

        # Find pending payment by docnum
        pending_file = DATA_DIR / "pending_payments.json"
        pending_list = []
        if pending_file.exists():
            try:
                pending_list = json.loads(pending_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        matched = None
        remaining = []
        for p in pending_list:
            if str(p.get("docnum")) == str(docnum) and matched is None:
                matched = p
            else:
                remaining.append(p)

        if matched:
            user_id = matched.get("user_id", "demo-user")
            tokens_to_add = int(matched.get("tokens", 0))
            user = _get_user(user_id)
            if user:
                new_total = int(user.get("tokens", 0)) + tokens_to_add
                _update_user_tokens(user_id, new_total)

            # Save transaction record
            tx_file = DATA_DIR / "transactions.json"
            txs = []
            if tx_file.exists():
                try:
                    txs = json.loads(tx_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            txs.append({
                "docnum": docnum,
                "user_id": user_id,
                "tokens": tokens_to_add,
                "amount": amount,
                "confirmation": confirmation,
                "customer_id": customer_id,
                "status": "paid",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            tx_file.write_text(json.dumps(txs, ensure_ascii=False, indent=2), encoding="utf-8")

            # Update pending list
            pending_file.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")

        return self.send_json(200, {"status": "ok", "tokens_added": matched.get("tokens") if matched else 0})


    def _send_security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
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