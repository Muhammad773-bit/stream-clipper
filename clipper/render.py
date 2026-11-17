"""Cut a clip straight from the online VOD and render it as a 1080x1920 vertical video
with bold word-by-word captions. Only the clip's seconds are downloaded."""
from __future__ import annotations

import os

from .tools import FFMPEG, run

W, H = 1080, 1920
CAM_H = 640  # facecam strip height in the "facecam" layout

LAYOUTS = ("facecam", "full", "center")


def _video_filter(layout: str, cam: tuple[float, float, float, float] | None) -> str:
    if layout == "facecam":
        if not cam:
            raise ValueError("The 'facecam' layout needs --facecam x,y,w,h (fractions of the frame).")
        x, y, w, h = cam
        return (
            f"[0:v]split[a][b];"
            f"[a]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale={W}:{CAM_H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{CAM_H}[cam];"
            f"[b]scale=-2:{H - CAM_H},crop={W}:{H - CAM_H}[game];"
            f"[cam][game]vstack,setsar=1[base]"
        )
    if layout == "center":  # just the middle of the screen, full height
        return f"[0:v]scale=-2:{H},crop={W}:{H},setsar=1[base]"
    # "full": whole 16:9 picture in the middle on a blurred copy of itself
    return (
        f"[0:v]split[a][b];"
        f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:3[bg];"
        f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
    )


def _caption_style(layout: str) -> tuple[int, int]:
    """ASS (alignment, vertical margin) so captions never cover the facecam."""
    if layout == "facecam":
        return 8, CAM_H + 140   # just below the facecam strip
    if layout == "full":
        return 2, 420           # under the video, above the bottom UI of the apps
    return 2, 560


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def write_captions(words: list[dict], clip_start: float, clip_end: float, layout: str, path: str) -> bool:
    if not words:
        return False
    align, margin = _caption_style(layout)
    font = os.environ.get("CAPTION_FONT", "Arial")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{font},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,"
        f"{align},60,60,{margin},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    # group words into short chunks of up to 3 words, breaking on pauses
    chunks: list[list[dict]] = []
    for w in words:
        if chunks and len(chunks[-1]) < 3 and w["s"] - chunks[-1][-1]["e"] < 0.6:
            chunks[-1].append(w)
        else:
            chunks.append([w])
    for chunk in chunks:
        for i, w in enumerate(chunk):
            start = w["s"] - clip_start
            end = (chunk[i + 1]["s"] if i + 1 < len(chunk) else w["e"] + 0.25) - clip_start
            if end <= 0 or start >= clip_end - clip_start:
                continue
            parts = []
            for j, x in enumerate(chunk):
                word = _esc(x["w"].upper())
                parts.append("{\\c&H00E5FF&\\fscx112\\fscy112}" + word + "{\\r}" if j == i else word)
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{' '.join(parts)}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return True


def render_clip(sources: list[str], clip: dict, layout: str, cam, out_dir: str, name: str) -> str:
    start, end = clip["start"], clip["end"]
    dur = end - start
    inputs = []
    for src in sources[:2]:
        inputs += ["-ss", f"{start:.2f}", "-i", src]
    audio_map = "1:a:0" if len(sources) > 1 else "0:a:0?"

    filt = _video_filter(layout, cam)
    ass_name = f"{name}.ass"
    if write_captions(clip.get("words", []), start, end, layout, os.path.join(out_dir, ass_name)):
        filt += f";[base]ass={ass_name}[v]"
    else:
        filt += ";[base]null[v]"

    out_name = f"{name}.mp4"
    run([FFMPEG, "-y", "-v", "error", *inputs, "-t", f"{dur:.2f}",
         "-filter_complex", filt, "-map", "[v]", "-map", audio_map,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_name],
        cwd=out_dir)
    if os.path.exists(os.path.join(out_dir, ass_name)):
        os.remove(os.path.join(out_dir, ass_name))
    return os.path.join(out_dir, out_name)
