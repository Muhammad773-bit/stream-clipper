"""Usage:
    python -m clipper <VOD URL> [--profile funny|irl|gaming|gta6] [--layout facecam|full|center]
                      [--facecam x,y,w,h] [--preset NAME] [--max-clips 12] [--candidates 30]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time

from . import judge, render, signals, transcribe, twitch_api
from .tools import FFMPEG, download_audio, parse_twitch_vod_id, require, stream_urls, vod_info

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "clip"


def load_preset(name: str | None) -> dict:
    if not name:
        return {}
    with open(os.path.join(ROOT, "presets", "streamers.json"), encoding="utf-8") as f:
        presets = json.load(f)
    if name.lower() not in presets:
        raise SystemExit(f"No preset '{name}' in presets/streamers.json")
    return presets[name.lower()]


def main() -> None:
    ap = argparse.ArgumentParser(prog="clipper", description="Turn a stream VOD link into short vertical clips.")
    ap.add_argument("url")
    ap.add_argument("--preset", help="streamer name from presets/streamers.json (sets profile/layout/facecam)")
    ap.add_argument("--profile", choices=list(judge.PROFILES))
    ap.add_argument("--layout", choices=render.LAYOUTS)
    ap.add_argument("--facecam", help="facecam box as fractions x,y,w,h e.g. 0.75,0.70,0.25,0.30")
    ap.add_argument("--max-clips", type=int, default=12)
    ap.add_argument("--candidates", type=int, default=30, help="moments to analyse before choosing")
    ap.add_argument("--min-score", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(ROOT, "output"))
    ap.add_argument("--keep-audio", action="store_true")
    args = ap.parse_args()

    require(FFMPEG)
    preset = load_preset(args.preset)
    profile = args.profile or preset.get("profile", "funny")
    layout = args.layout or preset.get("layout", "full")
    cam_text = args.facecam or preset.get("facecam")
    cam = tuple(float(v) for v in cam_text.split(",")) if cam_text else None
    if layout == "facecam" and not cam:
        print("No facecam position given: falling back to the 'full' layout.")
        layout = "full"

    t0 = time.time()
    print("1/6 Reading VOD info...")
    info = vod_info(args.url)
    vod_id = parse_twitch_vod_id(args.url) or info.get("id", "vod")
    job_dir = os.path.join(args.out, f"{_slug(info.get('uploader') or 'stream')}-{vod_id}")
    work = os.path.join(job_dir, "_work")
    os.makedirs(work, exist_ok=True)
    print(f"    {info.get('title')!r} by {info.get('uploader')} ({(info.get('duration') or 0) / 3600:.1f} h)")

    print("2/6 Downloading audio only (not the video)...")
    audio = download_audio(args.url, work)

    print("3/6 Finding hype moments...")
    db = signals.loudness_per_second(audio)
    viewer_clips = twitch_api.viewer_clips(vod_id) if parse_twitch_vod_id(args.url) else []
    windows = signals.pick_windows(signals.hype_curve(db, viewer_clips), args.candidates)
    print(f"    {len(windows)} candidate moments")

    print("4/6 Transcribing candidate moments...")
    for i, w in enumerate(windows, 1):
        w["words"] = transcribe.transcribe_window(audio, w["start"], w["end"], work)
        print(f"    {i}/{len(windows)} done", flush=True)

    print("5/6 AI is choosing the best clips...")
    picks = judge.choose_clips(windows, profile)
    clips = judge.finalize(windows, picks, args.max_clips, args.min_score)
    if not clips:
        clips = judge.finalize(windows, picks, args.max_clips, 0)  # never return nothing
    print(f"    {len(clips)} clips selected")

    print(f"6/6 Rendering {len(clips)} vertical clips ({layout} layout)...")
    sources = stream_urls(args.url)
    results = []
    for i, clip in enumerate(clips, 1):
        name = f"{i:02d}-{_slug(clip['title'])}"
        try:
            path = render.render_clip(sources, clip, layout, cam, job_dir, name)
        except RuntimeError as exc:
            print(f"    clip {i} failed: {exc}")
            continue
        mm, ss = divmod(int(clip["start"]), 60)
        hh, mm = divmod(mm, 60)
        results.append({
            "file": os.path.basename(path), "title": clip["title"], "caption": clip["caption"],
            "score": clip["score"], "category": clip["category"], "spoiler": clip["spoiler"],
            "vod_time": f"{hh}:{mm:02d}:{ss:02d}", "length_s": round(clip["end"] - clip["start"], 1),
        })
        print(f"    [{i}/{len(clips)}] {clip['score']}/10  {clip['title']}")

    with open(os.path.join(job_dir, "clips.json"), "w", encoding="utf-8") as f:
        json.dump({"vod": args.url, "title": info.get("title"), "streamer": info.get("uploader"),
                   "profile": profile, "clips": results}, f, indent=2, ensure_ascii=False)
    with open(os.path.join(job_dir, "POST-THESE.md"), "w", encoding="utf-8") as f:
        f.write(f"# Clips from {info.get('uploader')}: {info.get('title')}\n\n")
        for r in results:
            spoiler = " **SPOILER**" if r["spoiler"] else ""
            f.write(f"## {r['file']}{spoiler}\n- **Title:** {r['title']}\n- **Caption:** {r['caption']}\n"
                    f"- Score {r['score']}/10 · {r['category']} · {r['length_s']}s · at {r['vod_time']} in VOD\n\n")
    if not args.keep_audio:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\nDone in {(time.time() - t0) / 60:.0f} min. Clips are in: {job_dir}")


if __name__ == "__main__":
    main()
