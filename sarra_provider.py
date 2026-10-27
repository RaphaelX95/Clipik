"""Sarra Pro adapter for Klipik - covert integration."""
import os
import json
import time
import uuid
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError


_API_BASE = "https://api.sarra.pro/v4"
_API_KEY = os.environ.get("SARRA_API_KEY", "")


class SarraError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
    }


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{_API_BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, headers=_headers(), method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except HTTPError as exc:
        try:
            err = json.loads(exc.read().decode())
        except Exception:
            err = {}
        raise SarraError(
            err.get("error", {}).get("code", "unknown"),
            err.get("error", {}).get("message", str(exc)),
            status=exc.code,
        ) from exc


def get_account() -> dict:
    """Get account balance and details."""
    return _request("GET", "/me")


def list_avatars() -> dict:
    """List available avatars."""
    return _request("GET", "/avatars")


def create_video(brief: str, style: str = "UGC טבעי", duration: int = 15,
                 reference_images: list[str] | None = None,
                 language: str = "he", avatar: str | None = None,
                 draft: bool = False) -> dict:
    """
    Create a video from a brief.
    
    Args:
        brief: The video description / script
        style: Visual style (mapped to Sarra concept)
        duration: Target duration in seconds
        reference_images: Base64 images or URLs
        language: Language code (he, en, ar, ru)
        avatar: Avatar ID or name
        draft: If True, creates draft (1 credit) instead of full video (4 credits)
    """
    # Map Klipik styles to Sarra concepts
    concept_map = {
        "UGC טבעי": "product_review",
        "הדגמת מוצר": "product_review",
        "פתיחת חבילה": "occasion",
        "קריינות ותקריבים": "explainer",
        "מדריך קצר": "explainer",
    }
    concept = concept_map.get(style, "product_review")
    
    payload = {
        "brief": brief,
        "concept": concept,
        "language": language,
        "draft": draft,
    }
    if reference_images:
        payload["reference_images"] = reference_images
    if avatar:
        payload["avatar"] = avatar
    
    return _request("POST", "/videos", payload)


def get_video(video_id: str) -> dict:
    """Get video status and details."""
    return _request("GET", f"/videos/{video_id}")


def edit_video(video_id: str, brief: str | None = None,
               reference_images: list[str] | None = None,
               render: bool = False) -> dict:
    """
    Edit a video.
    
    Args:
        video_id: The video to edit
        brief: New script/description
        reference_images: New reference images
        render: If True, renders immediately (1 credit). If False, draft mode.
    """
    payload = {"render": render}
    if brief:
        payload["brief"] = brief
    if reference_images:
        payload["reference_images"] = reference_images
    
    return _request("POST", f"/videos/{video_id}/edit", payload)


def render_video(video_id: str) -> dict:
    """Render a draft video (3 credits)."""
    return _request("POST", f"/videos/{video_id}/render")


def dub_video(video_id: str, language: str = "en") -> dict:
    """Translate/dub a video to another language (2 credits)."""
    return _request("POST", f"/videos/{video_id}/dub", {"language": language})


def publish_video(video_id: str, networks: list[str] | None = None,
                  schedule_at: str | None = None) -> dict:
    """
    Publish or schedule a video.
    
    Args:
        video_id: The video to publish
        networks: List of networks (instagram, tiktok, youtube, facebook, linkedin, x)
        schedule_at: ISO timestamp for scheduled post
    """
    payload = {}
    if networks:
        payload["networks"] = networks
    if schedule_at:
        payload["schedule_at"] = schedule_at
    
    return _request("POST", f"/videos/{video_id}/publish", payload)


def list_videos(limit: int = 20) -> dict:
    """List recent videos."""
    return _request("GET", f"/videos?limit={limit}")


def estimate_cost(duration: int = 15, draft: bool = False,
                  edits: dict | None = None) -> dict:
    """
    Estimate cost for a video.
    
    Args:
        duration: Target duration
        draft: Draft mode?
        edits: Dict with edit types and counts
    """
    cost = 1 if draft else 4
    if edits:
        cost += edits.get("words", 0) * 0.25
        cost += edits.get("images", 0) * 0.5
        cost += edits.get("render", 0) * 1
        cost += edits.get("translate", 0) * 2
    
    return {
        "credits": cost,
        "estimated_ils": round(cost * 2.70, 2),  # rough conversion
        "estimated_usd": round(cost * 0.75, 2),
    }


# Style/concept mapping for UI
STYLE_MAP = {
    "UGC טבעי": {"concept": "product_review", "icon": "🎬"},
    "הדגמת מוצר": {"concept": "product_review", "icon": "📦"},
    "פתיחת חבילה": {"concept": "occasion", "icon": "🎁"},
    "קריינות ותקריבים": {"concept": "explainer", "icon": "🎙️"},
    "מדריך קצר": {"concept": "explainer", "icon": "📚"},
}

LANGUAGE_MAP = {
    "עברית": "he",
    "English": "en",
    "العربية": "ar",
    "רוסית": "ru",
}
