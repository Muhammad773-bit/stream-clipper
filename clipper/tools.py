"""Thin wrappers around the external programs we rely on (yt-dlp, ffmpeg)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def require(binary: str) -> None:
    if shutil.which(binary) is None:
        sys.exit(f"'{binary}' was not found. Install it first (see README).")


def run(cmd: list[str], cwd: str | None = None, quiet: bool = True) -> subprocess.CompletedProcess:
    print("  $", " ".join(cmd[:6]), "..." if len(cmd) > 6 else "", flush=True)
    res = subprocess.run(cmd, cwd=cwd, capture_output=quiet, text=True)
    if res.returncode != 0:
        tail = (res.stderr or "")[-2000:]
        raise RuntimeError(f"Command failed ({cmd[0]}):\n{tail}")
    return res


def ytdlp_base() -> list[str]:
    return [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist"]


def stream_urls(url: str, max_height: int = 1080) -> list[str]:
    """Direct media URL(s) for the VOD: one combined URL (Twitch) or video+audio (YouTube)."""
    fmt = f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"
    res = run(ytdlp_base() + ["-g", "-f", fmt, url])
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def download_audio(url: str, out_dir: str) -> str:
    """Download only the audio track of the VOD (about 300-600 MB for 7 hours)."""
    template = os.path.join(out_dir, "audio.%(ext)s")
    run(ytdlp_base() + [
        "-f", "Audio_Only/ba/worst",
        "--concurrent-fragments", "8",
        "--no-progress",
        "-o", template,
        url,
    ], quiet=False)
    for name in os.listdir(out_dir):
        if name.startswith("audio."):
            return os.path.join(out_dir, name)
    raise RuntimeError("Audio download finished but no audio file was found.")


def vod_info(url: str) -> dict:
    import json
    res = run(ytdlp_base() + ["-J", "--skip-download", url])
    return json.loads(res.stdout)


def parse_twitch_vod_id(url: str) -> str | None:
    m = re.search(r"twitch\.tv/(?:[^/]+/)?videos?/(\d+)", url)
    return m.group(1) if m else None
