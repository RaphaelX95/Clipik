"""אחסון נתוני האתר (משתמשים, פרויקטים, תשלומים).

אם SUPABASE_URL ו-SUPABASE_SERVICE_KEY מוגדרים, הנתונים נשמרים בטבלה
clipik_store ב-Supabase. אחרת הם נשמרים בקבצי JSON בתיקיית הנתונים (למחשב מקומי ולבדיקות).
"""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

_TABLE = "clipik_store"


def _supabase_config():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if url and key:
        return url, key
    return None


def _request(method: str, url: str, key: str, body=None, extra_headers=None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def load(name: str, default, data_dir: Path):
    """קורא את הנתונים בשם name. מחזיר default אם אין נתונים."""
    cfg = _supabase_config()
    if cfg:
        url, key = cfg
        query = urllib.parse.urlencode({"name": f"eq.{name}", "select": "data"})
        rows = _request("GET", f"{url}/rest/v1/{_TABLE}?{query}", key) or []
        return rows[0]["data"] if rows else default
    path = Path(data_dir) / f"{name}.json"
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save(name: str, value, data_dir: Path) -> None:
    """שומר את הנתונים בשם name."""
    cfg = _supabase_config()
    if cfg:
        url, key = cfg
        _request(
            "POST",
            f"{url}/rest/v1/{_TABLE}?on_conflict=name",
            key,
            body=[{"name": name, "data": value}],
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        return
    path = Path(data_dir) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
