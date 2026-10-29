"""ייבוא פרטי מוצר מקישור לחנות: שם, תיאור, מחיר ותמונות, לתוך תבנית דף מוצר."""
from __future__ import annotations

import base64
import html as _html
import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlparse

import requests

MAX_PAGE_BYTES = 2_000_000
MAX_IMAGE_BYTES = 1_000_000  # תואם למגבלת התמונות בדף המוצר
MAX_IMAGES = 3
TIMEOUT = (5, 10)
USER_AGENT = "Mozilla/5.0 (compatible; ClipikProductImport/1.0)"
_CURRENCY = {"ILS": "₪", "NIS": "₪", "USD": "$", "EUR": "€", "GBP": "£"}
_IMG_TYPES = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp"}


class ImportError_(Exception):
    """שגיאה שמוצגת למשתמש בעברית."""


def is_public_url(url: str) -> bool:
    """מאשר רק כתובות http/https שמצביעות לכתובות ציבוריות, כדי למנוע גישה לרשת הפנימית."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            return False
    return True


def _get(url: str, accept: str, limit: int) -> tuple[bytes, str]:
    if not is_public_url(url):
        raise ImportError_("הקישור הזה לא נראה כמו כתובת ציבורית של חנות")
    try:
        r = requests.get(url, timeout=TIMEOUT, allow_redirects=False, stream=True,
                         headers={"User-Agent": USER_AGENT, "Accept": accept})
    except requests.RequestException:
        raise ImportError_("לא הצלחנו לפתוח את הקישור")
    try:
        if 300 <= r.status_code < 400:
            raise ImportError_("הקישור מעביר לכתובת אחרת, הדביקו את הכתובת הסופית של המוצר")
        if r.status_code != 200:
            raise ImportError_("הקישור לא זמין כרגע")
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > limit:
                raise ImportError_("הקובץ גדול מדי")
        return data, ctype
    finally:
        r.close()


def _meta_map(page: str) -> dict:
    out: dict[str, str] = {}
    for tag in re.findall(r"<meta\b[^>]*>", page, flags=re.I):
        attrs = dict((k.lower(), v) for k, v in re.findall(r"([\w:-]+)\s*=\s*[\"']([^\"']*)[\"']", tag))
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            out.setdefault(key.lower(), _html.unescape(attrs["content"]).strip())
    return out


def _json_ld_products(page: str) -> list[dict]:
    found: list[dict] = []

    def walk(node):
        if isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Product" in types:
                found.append(node)
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v)

    for raw in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", page, flags=re.I | re.S):
        try:
            walk(json.loads(raw.strip()))
        except ValueError:
            continue
    return found


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _clip(text: str, n: int) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", _html.unescape(text)).strip()
    return text[:n].rstrip()


def parse_product(page: str, base_url: str) -> dict:
    """מוציא שם, תיאור, מחיר וכתובות תמונות מדף מוצר. קודם JSON-LD, ואחר כך תגיות Open Graph."""
    meta = _meta_map(page)
    ld = _json_ld_products(page)
    prod = ld[0] if ld else {}
    offers = _first(prod.get("offers")) or {}

    name = _clip(prod.get("name") or meta.get("og:title") or "", 80)
    if not name:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
        name = _clip(m.group(1) if m else "", 80)

    description = _clip(prod.get("description") or meta.get("og:description") or meta.get("description") or "", 300)

    amount = offers.get("price") or offers.get("lowPrice") or meta.get("product:price:amount") or ""
    currency = offers.get("priceCurrency") or meta.get("product:price:currency") or "ILS"
    price = ""
    if str(amount).strip():
        try:
            num = float(str(amount).replace(",", ""))
            shown = str(int(num)) if num.is_integer() else f"{num:.2f}"
        except ValueError:
            shown = str(amount).strip()
        price = f"{_CURRENCY.get(str(currency).upper(), str(currency) + ' ')}{shown}"

    raw_imgs = []
    img = prod.get("image")
    if isinstance(img, dict):
        img = img.get("url")
    if isinstance(img, list):
        raw_imgs += [x.get("url") if isinstance(x, dict) else x for x in img]
    elif img:
        raw_imgs.append(img)
    raw_imgs += [meta.get("og:image:secure_url"), meta.get("og:image")]
    images: list[str] = []
    for u in raw_imgs:
        if isinstance(u, str) and u.strip():
            absolute = urljoin(base_url, u.strip())
            if absolute not in images and urlparse(absolute).scheme in ("http", "https"):
                images.append(absolute)
    return {"product": name, "description": description, "price": price, "image_urls": images[:MAX_IMAGES]}


def _image_data_uri(url: str) -> str | None:
    try:
        data, ctype = _get(url, "image/*", MAX_IMAGE_BYTES)
    except ImportError_:
        return None
    kind = _IMG_TYPES.get(ctype)
    if not kind or not data:
        return None
    return f"data:image/{kind};base64," + base64.b64encode(data).decode("ascii")


def import_product(url: str) -> dict:
    """מחזיר את פרטי המוצר מהקישור. זורק ImportError_ עם הודעה בעברית אם לא מצליחים."""
    url = (url or "").strip()
    if not url or len(url) > 500:
        raise ImportError_("הדביקו קישור מלא למוצר")
    if not re.match(r"^https?://", url, flags=re.I):
        url = "https://" + url
    data, ctype = _get(url, "text/html", MAX_PAGE_BYTES)
    if ctype and "html" not in ctype:
        raise ImportError_("הקישור לא מוביל לדף מוצר")
    page = data.decode("utf-8", errors="replace")
    info = parse_product(page, url)
    if not info["product"]:
        raise ImportError_("לא מצאנו פרטי מוצר בקישור הזה")
    images = []
    for u in info.pop("image_urls"):
        uri = _image_data_uri(u)
        if uri:
            images.append(uri)
    info["images"] = images
    info["url"] = url
    return info
