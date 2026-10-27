#!/usr/bin/env python3
"""Tiny dependency-free local server for the Clipic MVP."""
from __future__ import annotations
import json
from decimal import Decimal
import os
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(_Path(__file__).resolve().parent / ".env"), override=False)
except Exception:
    pass
import fal_provider as _fal_provider
import requests as _requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "projects.json"
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


_USERS_PATH = Path(__file__).with_name('users.json')

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

        user_id = payload.get('user_id', 'demo-user')
        
        # Check if user can use free trial (demo video instead of real generation)
        if _has_free_trial_available(user_id):
            _mark_free_trial_used(user_id)
            tokens_required = _fal_provider.estimate_tokens(int(payload.get("duration", 15)))
            user = _get_user(user_id)
            new_tokens = 0
            if user:
                new_tokens = max(0, int(user.get('tokens', 0)) - tokens_required)
                _update_user_tokens(user_id, new_tokens)
            
            project = {
                "id": uuid.uuid4().hex[:10],
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "product": str(payload.get("product", "מוצר לדוגמה"))[:120],
                "product_url": str(payload.get("product_url", ""))[:500],
                "audience": str(payload.get("audience", ""))[:300],
                "language": str(payload.get("language", "עברית"))[:40],
                "platform": str(payload.get("platform", "אנכי · 9:16"))[:40],
                "duration": str(payload.get("duration", "15"))[:20],
                "script": str(payload.get("script", ""))[:750],
                "captions": str(payload.get("captions", ""))[:50],
                "music": str(payload.get("music", "ללא מוזיקה"))[:40],
                "style": str(payload.get("style", "UGC טבעי"))[:80],
                "creator": str(payload.get("creator", "דמות AI"))[:80],
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
        )
        duration = int(payload.get("duration", 15))

        try:
            video_url = _fal_provider.generate_clip(
                image_bytes=image_bytes,
                content_type=content_type,
                prompt=prompt,
                duration=duration,
            )
        except RuntimeError as exc:
            return self.send_json(500, {"error": str(exc)})
        except Exception as exc:
            return self.send_json(500, {"error": f" Generation failed: {exc}"})

        project = {
            "id": uuid.uuid4().hex[:10],
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "product": str(payload.get("product", "מוצר לדוגמה"))[:120],
            "product_url": str(payload.get("product_url", ""))[:500],
            "audience": str(payload.get("audience", ""))[:300],
            "language": str(payload.get("language", "עברית"))[:40],
            "platform": str(payload.get("platform", "אנכי · 9:16"))[:40],
            "duration": str(duration)[:20],
            "script": str(payload.get("script", ""))[:750],
            "captions": str(payload.get("captions", ""))[:50],
            "music": str(payload.get("music", "ללא מוזיקה"))[:40],
            "style": str(payload.get("style", "UGC טבעי"))[:80],
            "creator": str(payload.get("creator", "דמות AI"))[:80],
            "status": "completed",
            "video_url": video_url,
        }
        # Deduct tokens after successful generation
        user_id = payload.get('user_id', 'demo-user')
        tokens_required = _fal_provider.estimate_tokens(duration)
        user = _get_user(user_id)
        if user:
            new_tokens = max(0, int(user.get('tokens', 0)) - tokens_required)
            _update_user_tokens(user_id, new_tokens)
        
        items = read_projects()
        items.insert(0, project)
        write_projects(items[:100])
        return self.send_json(201, {"project": project, "video_url": video_url, "tokens_remaining": new_tokens if user else 0, "tokens_spent": tokens_required})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "app": "clipic-mvp"})
        if path == "/api/fal/status":
            configured = bool(os.environ.get("FAL_KEY"))
            return self.send_json(200, {"configured": configured, "model": _fal_provider.MODEL_ID})
        if path == "/api/projects":
            return self.send_json(200, {"projects": read_projects()})
        if path == "/api/users/me":
            user_id = self.headers.get('X-User-Id', 'demo-user')
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
            try:
                duration = int(urlparse(self.path).query.split("duration=")[-1].split("&")[0])
            except Exception:
                duration = 15
            try:
                cost = _fal_provider.estimate_cost_usd(duration)
                tokens = _fal_provider.estimate_tokens(duration)
                cost_ils = float((cost * _fal_provider.USD_TO_ILS).quantize(Decimal("0.01")))
            except Exception as exc:
                return self.send_json(400, {"error": str(exc)})
            return self.send_json(200, {"estimated_cost_usd": f"{cost:.3f}", "estimated_cost_ils": cost_ils, "tokens_required": tokens, "model": _fal_provider.MODEL_ID, "duration": duration})
        if path not in ("/", "/index.html", "/packages.html", "/tips.html", "/templates.html", "/create.html", "/payment_success.html", "/payment_failure.html", "/payment_cancel.html", "/sitemap.xml", "/robots.txt", "/google7cfae0c73b4d1768.html"):
            self.send_error(404, "Not found")
            return
        if path == "/tips.html":
            body = (ROOT / "tips.html").read_bytes()
        if path == "/templates.html":
            body = (ROOT / "templates.html").read_bytes()
        if path == "/create.html":
            body = (ROOT / "create.html").read_bytes()
        if path == "/google7cfae0c73b4d1768.html":
            body = (ROOT / "google7cfae0c73b4d1768.html").read_bytes()
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
            body = (ROOT / "index.html").read_bytes()
        elif path == "/packages.html":
            body = (ROOT / "packages.html").read_bytes()
        
        # Set correct content type for non-HTML files
        if path == "/sitemap.xml":
            content_type = "application/xml; charset=utf-8"
        elif path == "/robots.txt":
            content_type = "text/plain; charset=utf-8"
        else:
            content_type = "text/html; charset=utf-8"
        
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/generations":
            return self._handle_generation()
        if path == "/api/script/generate":
            return self._handle_script_generate()
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
            "product": str(payload.get("product", "מוצר לדוגמה"))[:120],
            "product_url": str(payload.get("product_url", ""))[:500],
            "audience": str(payload.get("audience", ""))[:300],
            "language": str(payload.get("language", "עברית"))[:40],
            "platform": str(payload.get("platform", "אנכי · 9:16"))[:40],
            "duration": str(payload.get("duration", "15"))[:20],
            "script": str(payload.get("script", ""))[:750],
            "captions": str(payload.get("captions", ""))[:50],
            "music": str(payload.get("music", "ללא מוזיקה"))[:40],
            "style": str(payload.get("style", "UGC טבעי"))[:80],
            "creator": str(payload.get("creator", "דמות AI"))[:80],
            "status": "draft",
        }
        items = read_projects()
        items.insert(0, project)
        write_projects(items[:100])
        return self.send_json(201, {"project": project})

    def _handle_script_generate(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"error": "Request too large"})
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Invalid JSON"})

        product = str(payload.get("product", "")).strip()
        audience = str(payload.get("audience", "")).strip()
        style = str(payload.get("style", "UGC טבעי")).strip()
        language = str(payload.get("language", "he")).strip()
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

    def _handle_icount_payment(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"error": "Request too large"})
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Invalid JSON"})

        package_id = payload.get("package_id", "")
        amount = float(payload.get("amount", 0))
        user_id = payload.get("user_id", "demo-user")
        user_email = payload.get("email", "")

        # Package token mapping
        package_tokens = {
            "trial": 6,
            "3": 6,
            "5": 10,
            "10": 20,
            "50": 50,
            "120": 120,
            "250": 250,
            "500": 500,
        }
        tokens = package_tokens.get(str(package_id), 0)
        if tokens <= 0 or amount < 0:
            return self.send_json(400, {"error": "Invalid package"})

        # Free trial - add tokens directly without payment
        if package_id == "trial" and amount == 0:
            user = _get_user(user_id)
            if user:
                new_total = int(user.get("tokens", 0)) + tokens
                user['free_trial_used'] = False
                _save_users(_load_users())
                _update_user_tokens(user_id, new_total)
                return self.send_json(200, {"ok": True, "tokens_added": tokens, "tokens_total": new_total, "message": "סרטון ראשון במבצע 9.99 ש״ח! הטוקנים הופעלו."})
            return self.send_json(404, {"error": "User not found"})

        description = f"טוקנים - {tokens} טוקנים (חבילת {package_id})"
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
            pending_file = ROOT / "pending_payments.json"
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
        pending_file = ROOT / "pending_payments.json"
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
            tx_file = ROOT / "transactions.json"
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