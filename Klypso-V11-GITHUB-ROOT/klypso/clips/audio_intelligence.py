"""Audio-quality intelligence for KLYPSO.

Keeps automatic clips punchy without changing the original event. The layer
scores silence, speech continuity and filler-word density from evidence already
available in the VOD analysis.
"""
import re


_FILLERS = {
    "fr": {"euh", "heu", "hum", "bah", "ben", "genre"},
    "en": {"uh", "um", "erm", "hmm", "like"},
}


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _words(text):
    return re.findall(r"[A-Za-zÀ-ÿ0-9']+", str(text or "").lower())


def analyze_audio_quality(duration, transcript_segments=None, silences=None):
    duration = max(0.0, _num(duration))
    segments = []
    filler_count = 0
    speech_seconds = 0.0
    for segment in transcript_segments or []:
        start = max(0.0, _num(segment.get("start")))
        end = max(start, _num(segment.get("end"), start))
        text = " ".join(str(segment.get("text", "")).split())
        if end <= start or not text:
            continue
        segments.append({"start": start, "end": end, "text": text})
        speech_seconds += min(max(0.0, end - start), duration if duration else end - start)
        words = _words(text)
        filler_count += sum(
            1 for word in words
            if word in _FILLERS["fr"] or word in _FILLERS["en"]
        )
    silence_seconds = 0.0
    for silence in silences or []:
        start = max(0.0, _num(silence.get("start")))
        end = max(start, _num(silence.get("end"), start))
        silence_seconds += max(0.0, end - start)
    clipped_duration = max(1.0, duration or max(
        [item["end"] for item in segments] or [1.0]
    ))
    speech_ratio = min(1.0, speech_seconds / clipped_duration)
    silence_ratio = min(1.0, silence_seconds / clipped_duration)
    word_count = sum(len(_words(item["text"])) for item in segments)
    filler_rate = filler_count / max(1, word_count)
    # Prefer continuous speech and low dead-air/filler density, but never
    # punish gameplay-only clips simply because they are quiet.
    score = 72.0
    score += min(16.0, speech_ratio * 22.0)
    score -= min(20.0, silence_ratio * 34.0)
    score -= min(15.0, filler_rate * 160.0)
    return {
        "engine": "klypso-audio-quality-v1",
        "speech_ratio": round(speech_ratio, 3),
        "silence_ratio": round(silence_ratio, 3),
        "filler_count": filler_count,
        "filler_rate": round(filler_rate, 4),
        "speech_segments": len(segments),
        "score": round(max(0.0, min(100.0, score)), 1),
    }


def enrich_candidates_with_audio_quality(candidates, audio_profile):
    profile = audio_profile or {}
    base = _num(profile.get("score"), 72.0)
    silence_ratio = min(1.0, _num(profile.get("silence_ratio"), 0.0))
    filler_rate = max(0.0, _num(profile.get("filler_rate"), 0.0))
    enriched = []
    for candidate in candidates or []:
        item = dict(candidate)
        candidate_silence = min(
            1.0,
            max(
                silence_ratio,
                _num(candidate.get("silence_fraction"), 0.0),
            ),
        )
        local_score = base - min(18.0, candidate_silence * 26.0) - min(12.0, filler_rate * 120.0)
        if candidate.get("audio_peak"):
            local_score += min(10.0, _num(candidate.get("audio_peak")) * 10.0)
        item["audio_quality_score"] = round(max(0.0, min(100.0, local_score)), 1)
        item["filler_rate"] = round(filler_rate, 4)
        item["filler_count"] = int(profile.get("filler_count", 0) or 0)
        enriched.append(item)
    return enriched
