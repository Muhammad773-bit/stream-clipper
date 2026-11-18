"""Speech-to-text for candidate windows only (runs on CPU, no graphics card needed)."""
from __future__ import annotations

import os
import subprocess

import numpy as np

from .tools import FFMPEG

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
    # Decode with ffmpeg ourselves and hand Whisper raw samples, so it never touches
    # PyAV (newer PyAV versions break faster-whisper's own audio loader).
    res = subprocess.run(
        [FFMPEG, "-v", "error", "-ss", str(start), "-t", str(end - start), "-i", audio_path,
         "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read audio window at {start}s: {res.stderr[-500:]!r}")
    samples = np.frombuffer(res.stdout, dtype=np.float32)
    if samples.size < 16000:  # less than a second of audio
        return []
    segments, _info = _get_model().transcribe(samples, word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"w": text, "s": round(float(start + w.start), 2),
                              "e": round(float(start + w.end), 2)})
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
