"""Find the most likely highlight moments in a long stream.

Signals:
  * audio hype: seconds where the streamer is much louder than their own recent baseline
    (screaming, laughing, sudden reactions)
  * viewer clips: places in the VOD that viewers already clipped, weighted by views
"""
from __future__ import annotations

import subprocess

import numpy as np

from .tools import FFMPEG

RATE = 8000  # Hz, enough for loudness


def loudness_per_second(audio_path: str) -> np.ndarray:
    """RMS loudness in dB for every second of the audio, streamed so memory stays small."""
    cmd = [FFMPEG, "-v", "error", "-i", audio_path, "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    chunk = RATE * 2  # one second of 16-bit samples
    values: list[float] = []
    assert proc.stdout is not None
    while True:
        buf = proc.stdout.read(chunk)
        if not buf:
            break
        x = np.frombuffer(buf, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(x * x)) + 1e-6
        values.append(20 * np.log10(rms))
    proc.wait()
    return np.array(values, dtype=np.float32)


def _rolling_median(x: np.ndarray, window: int) -> np.ndarray:
    # Median over coarse 10 s blocks, then interpolated: fast enough for 10+ hour streams.
    block = 10
    n = len(x) // block
    if n < 3:
        return np.full_like(x, np.median(x))
    blocks = x[: n * block].reshape(n, block).mean(axis=1)
    half = max(1, window // block // 2)
    med = np.array([np.median(blocks[max(0, i - half): i + half + 1]) for i in range(n)])
    return np.interp(np.arange(len(x)), np.arange(n) * block + block / 2, med)


def hype_curve(db: np.ndarray, clips: list[dict]) -> np.ndarray:
    """Per-second highlight score (higher = more likely a strong moment)."""
    n = len(db)
    baseline = _rolling_median(db, window=600)       # streamer's normal volume over ~10 min
    spread = np.std(db - baseline) + 1e-3
    audio = np.clip((db - baseline) / spread, 0, 6)
    audio = np.convolve(audio, np.ones(5) / 5, mode="same")  # smooth over ~5 s

    score = audio.copy()
    if clips:
        density = np.zeros(n, dtype=np.float32)
        for c in clips:
            a, b = c["offset"], int(c["offset"] + c["duration"])
            if a < n:
                density[a:min(b, n)] += np.sqrt(max(c["views"], 1))
        if density.max() > 0:
            score += 6 * density / density.max()      # viewer clips are a strong signal
    # Ignore intros ("starting soon") and outros: 3 min, or less on short videos.
    trim = min(180, n // 10)
    score[:trim] = 0
    score[max(0, n - trim):] = 0
    return score


def pick_windows(score: np.ndarray, count: int, before: int = 50, after: int = 40,
                 min_gap: int = 120) -> list[dict]:
    """Greedy peak picking: the top `count` non-overlapping moments."""
    s = score.copy()
    windows = []
    for _ in range(count):
        peak = int(np.argmax(s))
        if s[peak] <= 0.5:
            break
        start = max(0, peak - before)
        end = min(len(score), peak + after)
        windows.append({"peak": peak, "start": start, "end": end, "signal": round(float(s[peak]), 2)})
        s[max(0, peak - min_gap): peak + min_gap] = 0
    windows.sort(key=lambda w: w["start"])
    return windows
