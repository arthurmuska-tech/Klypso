"""FFmpeg renderer for AI-selected KLYPSO clips and montages."""
from pathlib import Path
import tempfile

from ..media.ffmpeg import run


RATIOS = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
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


def write_srt(segments, start, end, path):
    selected = []
    for segment in segments or []:
        seg_start = max(float(segment.get("start", 0)), start)
        seg_end = min(float(segment.get("end", 0)), end)
        if seg_end <= seg_start:
            continue
        text = " ".join(str(segment.get("text", "")).split()).strip()
        if text:
            selected.append((seg_start - start, seg_end - start, text))

    with open(path, "w", encoding="utf-8") as handle:
        for index, (seg_start, seg_end, text) in enumerate(selected, start=1):
            handle.write(f"{index}\n{_srt_time(seg_start)} --> {_srt_time(seg_end)}\n{text}\n\n")
    return bool(selected)


def _video_filter(output_size, subtitle_file=None):
    width, height = output_size
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ]
    if subtitle_file:
        filters.append(f"subtitles=filename='{_escape_filter_path(subtitle_file)}'")
    return ",".join(filters)


def render_candidate(
    input_path,
    output_path,
    candidate,
    output_format="9:16",
    transcript_segments=None,
    subtitles=True,
    normalize_audio=True,
):
    width, height = RATIOS.get(output_format, RATIOS["9:16"])
    start = max(0.0, float(candidate["start"]))
    if "end" in candidate:
        duration = max(1.0, float(candidate["end"]) - start)
    else:
        duration = max(1.0, float(candidate.get("duration", 1)))

    subtitle_path = None
    try:
        if subtitles and transcript_segments:
            handle = tempfile.NamedTemporaryFile(suffix=".srt", delete=False)
            subtitle_path = handle.name
            handle.close()
            if not write_srt(transcript_segments, start, start + duration, subtitle_path):
                Path(subtitle_path).unlink(missing_ok=True)
                subtitle_path = None

        args = [
            "-ss", str(start),
            "-i", str(input_path),
            "-t", str(duration),
            "-vf", _video_filter((width, height), subtitle_path),
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
