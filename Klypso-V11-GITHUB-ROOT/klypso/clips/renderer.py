"""Social-first FFmpeg renderer for KLYPSO clips and montages."""
from pathlib import Path
import tempfile

from ..media.ffmpeg import run


RATIOS = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

SOCIAL_PRESETS = {
    "clean": {"zoom": 1.00, "sharpen": False, "saturation": 1.00, "contrast": 1.00, "fade": 0.00, "caption_style": "classic"},
    "dynamic": {"zoom": 1.04, "sharpen": True, "saturation": 1.03, "contrast": 1.02, "fade": 0.00, "caption_style": "dynamic"},
    "gaming": {"zoom": 1.06, "sharpen": True, "saturation": 1.08, "contrast": 1.04, "fade": 0.00, "caption_style": "dynamic"},
    "story": {"zoom": 1.02, "sharpen": False, "saturation": 0.99, "contrast": 1.01, "fade": 0.12, "caption_style": "classic"},
}

CAPTION_STYLES = {
    "dynamic": {"fontsize": 54, "outline": 6, "margin_v": 150, "bold": 1, "shadow": 0},
    "classic": {"fontsize": 46, "outline": 4, "margin_v": 105, "bold": 1, "shadow": 1},
    "minimal": {"fontsize": 40, "outline": 2, "margin_v": 82, "bold": 0, "shadow": 1},
}


def _escape_filter_path(path):
    return str(Path(path).as_posix()).replace("\\", "/").replace(":", "\\:")


def _srt_time(seconds):
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    milliseconds = int(round((seconds - whole) * 1000))
    if milliseconds == 1000:
        whole += 1
        milliseconds = 0
    minutes, sec = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d},{milliseconds:03d}"


def _caption_chunks(start, end, text, max_words=6, max_chars=42):
    words = text.split()
    if not words:
        return []
    chunks = []
    current = []
    for word in words:
        proposal = " ".join(current + [word])
        if current and (len(current) >= max_words or len(proposal) > max_chars):
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))
    duration = max(0.2, end - start)
    total_weight = sum(max(1, len(chunk.split())) for chunk in chunks) or 1
    cursor = start
    output = []
    for index, chunk in enumerate(chunks):
        portion = duration * (max(1, len(chunk.split())) / total_weight)
        chunk_end = end if index == len(chunks) - 1 else min(end, cursor + portion)
        output.append((cursor, chunk_end, chunk))
        cursor = chunk_end
    return output


def write_srt(segments, start, end, path):
    selected = []
    for segment in segments or []:
        seg_start = max(float(segment.get("start", 0)), start)
        seg_end = min(float(segment.get("end", 0)), end)
        if seg_end <= seg_start:
            continue
        text = " ".join(str(segment.get("text", "")).split()).strip()
        if text:
            selected.extend(_caption_chunks(seg_start - start, seg_end - start, text))

    with open(path, "w", encoding="utf-8") as handle:
        for index, (seg_start, seg_end, text) in enumerate(selected, start=1):
            handle.write(f"{index}\n{_srt_time(seg_start)} --> {_srt_time(seg_end)}\n{text}\n\n")
    return bool(selected)


def _subtitle_filter(subtitle_file, caption_style):
    style = CAPTION_STYLES.get(caption_style, CAPTION_STYLES["dynamic"])
    force = (
        f"FontName=DejaVu Sans,FontSize={style['fontsize']},"
        f"Bold={style['bold']},Outline={style['outline']},Shadow={style['shadow']},"
        f"Alignment=2,MarginV={style['margin_v']},PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&HB0000000,BorderStyle=1"
    )
    return f"subtitles=filename='{_escape_filter_path(subtitle_file)}':force_style='{force}'"


def _video_filter(output_size, social_preset="dynamic", subtitle_file=None, caption_style=None, zoom=None, fade_seconds=0.0):
    width, height = output_size
    preset = SOCIAL_PRESETS.get(social_preset, SOCIAL_PRESETS["dynamic"])
    zoom_factor = max(1.0, float(zoom if zoom is not None else preset["zoom"]))
    zoom_width = int(round(width * zoom_factor))
    zoom_height = int(round(height * zoom_factor))
    filters = [
        f"scale={zoom_width}:{zoom_height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ]
    if preset["saturation"] != 1.0 or preset["contrast"] != 1.0:
        filters.append(f"eq=saturation={preset['saturation']}:contrast={preset['contrast']}")
    if preset["sharpen"]:
        filters.append("unsharp=5:5:0.35:5:5:0")
    if subtitle_file:
        filters.append(_subtitle_filter(subtitle_file, caption_style or preset["caption_style"]))
    fade = max(0.0, float(fade_seconds if fade_seconds is not None else preset["fade"]))
    return filters, fade


def render_candidate(
    input_path,
    output_path,
    candidate,
    output_format="9:16",
    transcript_segments=None,
    subtitles=True,
    normalize_audio=True,
    social_preset="dynamic",
    caption_style=None,
    zoom=None,
    fade_seconds=0.0,
):
    width, height = RATIOS.get(output_format, RATIOS["9:16"])
    start = max(0.0, float(candidate["start"]))
    duration = max(1.0, float(candidate.get("end", start + candidate.get("duration", 1))) - start)

    subtitle_path = None
    try:
        if subtitles and transcript_segments:
            handle = tempfile.NamedTemporaryFile(suffix=".srt", delete=False)
            subtitle_path = handle.name
            handle.close()
            if not write_srt(transcript_segments, start, start + duration, subtitle_path):
                Path(subtitle_path).unlink(missing_ok=True)
                subtitle_path = None

        filters, fade = _video_filter(
            (width, height),
            social_preset=social_preset,
            subtitle_file=subtitle_path,
            caption_style=caption_style,
            zoom=zoom,
            fade_seconds=fade_seconds,
        )
        if fade:
            fade = min(float(fade), duration / 3.0)
            if fade > 0:
                filters.append(f"fade=t=in:st=0:d={fade:.3f}")
                filters.append(f"fade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}")

        args = [
            "-ss", str(start),
            "-i", str(input_path),
            "-t", str(duration),
            "-vf", ",".join(filters),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "19",
            "-pix_fmt", "yuv420p",
        ]
        if normalize_audio:
            args += ["-c:a", "aac", "-b:a", "160k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
        else:
            args += ["-c:a", "aac", "-b:a", "160k"]
        args += ["-movflags", "+faststart", str(output_path)]
        return run(args)
    finally:
        if subtitle_path:
            Path(subtitle_path).unlink(missing_ok=True)


def concat_videos(video_paths, output_path):
    handle = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8")
    list_path = Path(handle.name)
    try:
        for video_path in video_paths:
            safe = str(Path(video_path).resolve()).replace("'", "'\\''")
            handle.write(f"file '{safe}'\n")
        handle.close()
        run([
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ])
    finally:
        list_path.unlink(missing_ok=True)
