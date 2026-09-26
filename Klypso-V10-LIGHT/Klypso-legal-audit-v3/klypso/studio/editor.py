def apply_edit(timeline, operation):
    result = {**timeline, "clips": [dict(c) for c in timeline.get("clips", [])], "audio_tracks": [dict(a) for a in timeline.get("audio_tracks", [])], "markers": [dict(m) for m in timeline.get("markers", [])]}
    op = operation.get("type")
    if op == "split":
        target = operation.get("clip_index")
        at = operation.get("at")
        if target is None or at is None:
            raise ValueError("split nécessite clip_index et at")
        clip = result["clips"][target]
        if not 0 < at < clip["duration"]:
            raise ValueError("Position de split invalide")
        first = dict(clip, duration=at)
        second = dict(clip, start=clip["start"] + at, duration=clip["duration"] - at)
        result["clips"][target:target + 1] = [first, second]
        return result
    if op == "delete":
        target = operation.get("clip_index")
        if target is None:
            raise ValueError("delete nécessite clip_index")
        del result["clips"][target]
        return result
    raise ValueError(f"Opération Studio non supportée: {op}")
