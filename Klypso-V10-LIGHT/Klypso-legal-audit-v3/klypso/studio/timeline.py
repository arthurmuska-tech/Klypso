def validate_timeline(timeline):
    required = {"clips", "audio_tracks", "markers"}
    missing = required - set(timeline)
    if missing:
        raise ValueError(f"Timeline incomplète: {', '.join(sorted(missing))}")
    for clip in timeline["clips"]:
        if clip.get("duration", 0) <= 0 or clip.get("start", 0) < 0:
            raise ValueError("Clip timeline invalide.")
    return True
