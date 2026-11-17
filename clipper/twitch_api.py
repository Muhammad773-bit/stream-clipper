"""Official Twitch Helix API: VOD details and the clips viewers already made from it.

Needs a free Twitch developer app (TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET).
Without those, the clipper still works using audio + transcript signals only.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import requests

HELIX = "https://api.twitch.tv/helix"


def _token(client_id: str, secret: str) -> str:
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={"client_id": client_id, "client_secret": secret, "grant_type": "client_credentials"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _duration_seconds(text: str) -> int:
    total = 0
    for value, unit in re.findall(r"(\d+)([hms])", text):
        total += int(value) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total


def viewer_clips(vod_id: str) -> list[dict]:
    """Return [{'offset': sec, 'duration': sec, 'views': n, 'title': str}] for clips made from this VOD."""
    client_id = os.environ.get("TWITCH_CLIENT_ID")
    secret = os.environ.get("TWITCH_CLIENT_SECRET")
    if not client_id or not secret:
        print("  (no Twitch API keys set: skipping viewer-clips signal)")
        return []

    headers = {"Client-ID": client_id, "Authorization": f"Bearer {_token(client_id, secret)}"}
    v = requests.get(f"{HELIX}/videos", params={"id": vod_id}, headers=headers, timeout=20)
    v.raise_for_status()
    data = v.json().get("data") or []
    if not data:
        print("  (VOD not found in Twitch API)")
        return []
    video = data[0]
    start = datetime.fromisoformat(video["created_at"].replace("Z", "+00:00"))
    end = start + timedelta(seconds=_duration_seconds(video["duration"])) + timedelta(days=3)
    end = min(end, datetime.now(timezone.utc))

    clips: list[dict] = []
    cursor = None
    for _ in range(20):  # up to 2000 clips
        params = {
            "broadcaster_id": video["user_id"],
            "started_at": start.isoformat().replace("+00:00", "Z"),
            "ended_at": end.isoformat().replace("+00:00", "Z"),
            "first": 100,
        }
        if cursor:
            params["after"] = cursor
        r = requests.get(f"{HELIX}/clips", params=params, headers=headers, timeout=20)
        r.raise_for_status()
        body = r.json()
        for c in body.get("data", []):
            if c.get("video_id") == vod_id and c.get("vod_offset") is not None:
                clips.append({
                    "offset": int(c["vod_offset"]),
                    "duration": float(c.get("duration") or 30),
                    "views": int(c.get("view_count") or 0),
                    "title": c.get("title", ""),
                })
        cursor = (body.get("pagination") or {}).get("cursor")
        if not cursor:
            break
    print(f"  found {len(clips)} viewer clips from this VOD")
    return clips
