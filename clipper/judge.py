"""Use Gemini (free API tier) to choose the best clips, trim them, and write titles.

Falls back to a simple rule-based pick when no GEMINI_API_KEY is set.
"""
from __future__ import annotations

import json
import os

from .transcribe import as_timed_text

PROFILES = {
    "funny": "a funny / variety streamer. Prioritise: big laughs, absurd moments, roasts, "
             "chat or donation interactions that go wrong, unexpected reactions.",
    "irl": "an IRL / travel streamer filming in public. Prioritise: interactions with strangers, "
           "chaotic or shocking public moments, wholesome moments, culture-clash humour, near-disasters.",
    "gaming": "a gaming streamer. Prioritise: rage moments, clutch plays, hilarious fails, "
              "jump scares, big wins, funny bugs.",
    "gta6": "a streamer playing GTA 6 in its first days after launch. Prioritise, in this order: "
            "(1) chaos and physics fails, police chases, wanted-level madness; "
            "(2) funny or weird NPC interactions; (3) first-reaction 'wow' moments to graphics, map, "
            "or features; (4) rage and mission fails; (5) secrets / easter eggs / 'you can do THIS'; "
            "(6) big story moments (mark these with spoiler=true).",
}

PROMPT = """You are an expert short-form video editor who makes viral clips (YouTube Shorts,
Instagram Reels, X) from livestream VODs. The streamer is {profile}

Below are {n} candidate moments from the stream. Each has an id, a loudness/hype signal
(higher = louder reaction or more viewer clips), and a transcript where [Ns] marks seconds
from the start of that candidate window (window length is about {wlen}s).

For EACH candidate decide if it can be a strong standalone clip that a stranger would watch
to the end and share. Rules:
- Clip length 15-60 seconds. Start 1-3 seconds before the setup so the first second already
  hooks the viewer; end right after the payoff/reaction. Never end mid-sentence.
- Score 1-10 for viral potential. Be strict: boring talk, ads, waiting, or unclear context = low.
- Title: punchy hook under 60 characters, curiosity-driven, no clickbait lies, max 1 emoji.
- Caption: one short line for the post plus 3-5 relevant hashtags.

Return ONLY JSON: a list of objects with keys
id (int), keep (bool), score (int), start (seconds from window start), end (seconds from
window start), title (str), caption (str), category (str), spoiler (bool).

Candidates:
{candidates}
"""


def _fallback(windows: list[dict]) -> list[dict]:
    picks = []
    for i, w in enumerate(windows):
        words = " ".join(x["w"] for x in w.get("words", [])[:10])
        picks.append({
            "id": i, "keep": True, "score": min(10, int(w["signal"] * 1.5) + 3),
            "start": max(0, w["peak"] - w["start"] - 25), "end": w["peak"] - w["start"] + 15,
            "title": (words[:57] + "...") if len(words) > 60 else (words or f"Moment at {w['peak'] // 60} min"),
            "caption": "#stream #clips #twitch", "category": "highlight", "spoiler": False,
        })
    return picks


def choose_clips(windows: list[dict], profile: str) -> list[dict]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("  (no GEMINI_API_KEY: using simple rule-based picks)")
        return _fallback(windows)

    from google import genai
    from google.genai import types

    blocks = []
    for i, w in enumerate(windows):
        blocks.append(f"--- id {i} | hype {w['signal']} ---\n{as_timed_text(w.get('words', []), w['start'])}")
    prompt = PROMPT.format(
        profile=PROFILES.get(profile, PROFILES["funny"]), n=len(windows),
        wlen=int(windows[0]["end"] - windows[0]["start"]) if windows else 90,
        candidates="\n\n".join(blocks),
    )
    client = genai.Client(api_key=key)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    try:
        resp = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4),
        )
        picks = json.loads(resp.text)
        if isinstance(picks, dict):
            picks = picks.get("clips") or list(picks.values())[0]
        return picks
    except Exception as exc:  # network/quota/format problems should not kill a 1-hour job
        print(f"  Gemini failed ({exc}); using rule-based picks instead")
        return _fallback(windows)


def finalize(windows: list[dict], picks: list[dict], max_clips: int, min_score: int) -> list[dict]:
    """Convert AI picks into absolute VOD times, drop weak ones, keep the best N."""
    clips = []
    for p in picks:
        try:
            w = windows[int(p["id"])]
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        if not p.get("keep", True) or int(p.get("score", 0)) < min_score:
            continue
        start = w["start"] + max(0.0, float(p.get("start", 0)))
        end = w["start"] + float(p.get("end", w["end"] - w["start"]))
        end = min(end, start + 60)
        if end - start < 8:
            continue
        clips.append({
            "start": round(start, 2), "end": round(end, 2),
            "score": int(p.get("score", 0)), "title": str(p.get("title", "")).strip(),
            "caption": str(p.get("caption", "")).strip(), "category": p.get("category", ""),
            "spoiler": bool(p.get("spoiler", False)),
            "words": [x for x in w.get("words", []) if start - 0.2 <= x["s"] <= end],
        })
    clips.sort(key=lambda c: c["score"], reverse=True)
    return clips[:max_clips]
