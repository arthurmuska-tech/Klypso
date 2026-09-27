"""KLYPSO media signal intelligence.

Uses FFmpeg-native analysis so VODs gain timestamped visual/audio evidence even
when no cloud vision provider is configured. These are media signals, not claims
of semantic understanding.
"""
import re
import shutil
import subprocess
from pathlib import Path


_NUMBER = r"(-?\d+(?:\.\d+)?)"


def _run(args):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg est introuvable dans le PATH.")
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _scene_changes(path, threshold=0.35):
    result = _run([
        "-i", str(path),
        "-vf", f"select='gt(scene,{float(threshold):.3f})',showinfo",
        "-an", "-f", "null", "-",
    ])
    values = []
    for match in re.finditer(r"pts_time:" + _NUMBER, result.stderr or ""):
        try:
            values.append(round(float(match.group(1)), 3))
        except ValueError:
            continue
    return sorted(set(values))


def _silences(path, noise_db=-32, min_duration=0.45):
    result = _run([
        "-i", str(path),
        "-af", f"silencedetect=noise={float(noise_db):.1f}dB:d={float(min_duration):.2f}",
        "-vn", "-f", "null", "-",
    ])
    starts = []
    regions = []
    pending = None
    for line in (result.stderr or "").splitlines():
        start_match = re.search(r"silence_start:\s*" + _NUMBER, line)
        if start_match:
            try:
                pending = float(start_match.group(1))
                starts.append(round(pending, 3))
            except ValueError:
                pending = None
        end_match = re.search(r"silence_end:\s*" + _NUMBER, line)
        if end_match and pending is not None:
            try:
                end = float(end_match.group(1))
                if end > pending:
                    regions.append({
                        "start": round(pending, 3),
                        "end": round(end, 3),
                        "duration": round(end - pending, 3),
                    })
            except ValueError:
                pass
            pending = None
    return regions


def _rms_events(path):
    """Extract short-window RMS markers when the installed FFmpeg exposes astats metadata."""
    result = _run([
        "-i", str(path),
        "-vn",
        "-af", "astats=metadata=1:reset=0.5,ametadata=print:key=lavfi.astats.Overall.RMS_level",
        "-f", "null", "-",
    ])
    markers = []
    current_time = None
    for line in (result.stderr or "").splitlines():
        time_match = re.search(r"pts_time:" + _NUMBER, line)
        if time_match:
            try:
                current_time = float(time_match.group(1))
            except ValueError:
                current_time = None
        rms_match = re.search(r"lavfi\.astats\.Overall\.RMS_level=?" + _NUMBER, line)
        if rms_match and current_time is not None:
            try:
                rms = float(rms_match.group(1))
                if rms < 0:
                    markers.append({"time": round(current_time, 3), "rms_db": rms})
            except ValueError:
                continue
    if not markers:
        return []
    strongest = sorted(markers, key=lambda item: item["rms_db"], reverse=True)
    floor = min(item["rms_db"] for item in markers)
    ceiling = max(item["rms_db"] for item in markers)
    span = max(1.0, ceiling - floor)
    for item in markers:
        item["energy"] = round((item["rms_db"] - floor) / span, 3)
    return sorted(
        [item for item in markers if item["energy"] >= 0.72],
        key=lambda item: item["time"],
    )


def _merge_windows(windows, max_gap=2.5):
    ordered = sorted(
        [
            {"start": float(item["start"]), "end": float(item["end"]), "source": item.get("source", "signal")}
            for item in windows
            if float(item.get("end", 0)) > float(item.get("start", 0))
        ],
        key=lambda item: item["start"],
    )
    merged = []
    for item in ordered:
        if not merged or item["start"] - merged[-1]["end"] > max_gap:
            merged.append(item)
        else:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
            sources = {merged[-1]["source"], item["source"]}
            merged[-1]["source"] = "+".join(sorted(sources))
    return [
        {
            "start": round(item["start"], 3),
            "end": round(item["end"], 3),
            "duration": round(item["end"] - item["start"], 3),
            "source": item["source"],
        }
        for item in merged
    ]


def analyze_media_signals(path, scene_threshold=0.35, silence_noise_db=-32, silence_min_duration=0.45):
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError("Vidéo source introuvable.")

    scenes = _scene_changes(source, scene_threshold)
    silences = _silences(source, silence_noise_db, silence_min_duration)
    audio_peaks = _rms_events(source)

    event_windows = []
    for point in scenes:
        event_windows.append({"start": point - 4.0, "end": point + 7.0, "source": "scene_change"})
    for point in audio_peaks:
        event_windows.append({"start": point - 5.0, "end": point + 7.0, "source": "audio_peak"})

    return {
        "engine": "ffmpeg-media-signals-v1",
        "scene_changes": scenes[:120],
        "scene_change_count": len(scenes),
        "silences": silences[:120],
        "silence_count": len(silences),
        "audio_peaks": audio_peaks[:120],
        "audio_peak_count": len(audio_peaks),
        "event_windows": _merge_windows(event_windows),
    }


def _overlap_fraction(start, end, regions):
    length = max(0.001, end - start)
    overlap = 0.0
    for item in regions:
        left = max(start, float(item["start"]))
        right = min(end, float(item["end"]))
        if right > left:
            overlap += right - left
    return min(1.0, overlap / length)


def generate_signal_candidates(duration, signals, limit=36):
    """Create candidate windows from non-verbal audio/visual events."""
    duration = max(0.0, float(duration or 0))
    if duration <= 0:
        return []

    raw_events = []
    for event in (signals or {}).get("event_windows") or []:
        start = max(0.0, float(event.get("start", 0)) - 3.0)
        end = min(duration, float(event.get("end", start)) + 4.0)
        if end - start >= 8.0:
            raw_events.append({
                "start": start,
                "end": end,
                "source": "media_event",
                "signal_source": event.get("source", "signal"),
            })

    raw_events.sort(key=lambda item: (item["start"], item["end"]))
    merged = []
    for event in raw_events:
        if not merged or event["start"] - merged[-1]["end"] > 4.0:
            merged.append(dict(event))
        else:
            merged[-1]["end"] = max(merged[-1]["end"], event["end"])
            merged[-1]["signal_source"] = "+".join(sorted({
                merged[-1]["signal_source"],
                event["signal_source"],
            }))

    candidates = []
    seen = set()
    for item in merged:
        start = round(max(0.0, item["start"]), 3)
        end = round(min(duration, item["end"]), 3)
        key = (start, end)
        if key in seen or end - start < 8.0:
            continue
        seen.add(key)
        candidates.append({
            "id": f"signal-{len(candidates)+1}",
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "speech_words": 0,
            "speech_density": 0.0,
            "context": "",
            "source": item["signal_source"],
            "base_score": 62,
        })
        if len(candidates) >= limit:
            break
    return candidates


def enrich_candidates_with_media_signals(candidates, signals):
    signals = signals or {}
    scenes = [float(value) for value in signals.get("scene_changes", [])]
    silences = signals.get("silences") or []
    peaks = signals.get("audio_peaks") or []
    events = signals.get("event_windows") or []

    enriched = []
    for candidate in candidates or []:
        item = dict(candidate)
        start = float(item.get("start", 0))
        end = float(item.get("end", start))
        scene_hits = sum(start <= point <= end for point in scenes)
        peak_hits = [peak for peak in peaks if start <= float(peak.get("time", -1)) <= end]
        event_hits = sum(
            max(0.0, min(end, float(event["end"])) - max(start, float(event["start"])))
            for event in events
            if float(event["end"]) > start and float(event["start"]) < end
        )
        silence_fraction = _overlap_fraction(start, end, silences)
        item.update({
            "visual_change": round(min(1.0, scene_hits / 3.0), 3),
            "audio_peak": round(min(1.0, len(peak_hits) / 3.0), 3),
            "event_density": round(min(1.0, event_hits / max(8.0, end - start)), 3),
            "silence_fraction": round(silence_fraction, 3),
            "signal_sources": sorted({
                event.get("source", "signal")
                for event in events
                if float(event["end"]) > start and float(event["start"]) < end
            }),
        })
        signal_bonus = (
            0.34 * item["audio_peak"]
            + 0.28 * item["visual_change"]
            + 0.26 * item["event_density"]
            - 0.20 * item["silence_fraction"]
        )
        item["media_signal_score"] = round(max(0.0, min(1.0, 0.5 + signal_bonus)), 3)
        enriched.append(item)
    return enriched
