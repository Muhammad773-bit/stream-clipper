"""Speech-to-text for candidate windows only (runs on CPU, no graphics card needed)."""
from __future__ import annotations

import os

from .tools import FFMPEG, run

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        size = os.environ.get("WHISPER_MODEL", "small")
        print(f"  loading Whisper '{size}' model (CPU)...")
        _model = WhisperModel(size, device="cpu", compute_type="int8")
    return _model


def transcribe_window(audio_path: str, start: float, end: float, work_dir: str) -> list[dict]:
    """Words with timestamps relative to the VOD: [{'w': 'hello', 's': 123.4, 'e': 123.8}]."""
    wav = os.path.join(work_dir, f"win_{int(start)}.wav")
    run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", str(end - start),
         "-i", audio_path, "-ac", "1", "-ar", "16000", wav])
    segments, _info = _get_model().transcribe(wav, word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"w": text, "s": round(start + w.start, 2), "e": round(start + w.end, 2)})
    os.remove(wav)
    return words


def as_timed_text(words: list[dict], origin: float) -> str:
    """Compact transcript with [seconds] markers every few words, for the AI to read."""
    out, last = [], -10.0
    for w in words:
        if w["s"] - last >= 4:
            out.append(f"[{w['s'] - origin:.0f}s]")
            last = w["s"]
        out.append(w["w"])
    return " ".join(out) if out else "(no speech; possibly gameplay sounds, music or screaming)"
