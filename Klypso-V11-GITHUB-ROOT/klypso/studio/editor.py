"""Server-side non-destructive Studio timeline operations."""


def _positive_number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} doit être numérique.")
    if number <= 0:
        raise ValueError(f"{label} doit être positif.")
    return number


def apply_edit(timeline, operation):
    result = {
        **timeline,
        "clips": [dict(c) for c in timeline.get("clips", [])],
        "audio_tracks": [dict(a) for a in timeline.get("audio_tracks", [])],
        "markers": [dict(m) for m in timeline.get("markers", [])],
    }
    result.setdefault("settings", dict(timeline.get("settings") or {}))
    op = operation.get("type")
    if op == "split":
        target = operation.get("clip_index")
        at = operation.get("at")
        if target is None or at is None:
            raise ValueError("split nécessite clip_index et at")
        clip = result["clips"][int(target)]
        at = float(at)
        if not 0 < at < float(clip["duration"]):
            raise ValueError("Position de split invalide")
        first = dict(clip, duration=at)
        second = dict(clip, start=float(clip["start"]) + at, duration=float(clip["duration"]) - at)
        result["clips"][int(target):int(target) + 1] = [first, second]
        return result
    if op == "trim":
        target = operation.get("clip_index")
        in_point = float(operation.get("in_point", 0))
        out_point = float(operation.get("out_point", 0))
        clip = result["clips"][int(target)]
        duration = float(clip["duration"])
        if in_point < 0 or out_point <= in_point or out_point > duration:
            raise ValueError("Trim invalide")
        clip["start"] = float(clip["start"]) + in_point
        clip["duration"] = out_point - in_point
        return result
    if op == "move":
        target = operation.get("clip_index")
        new_start = float(operation.get("new_start", -1))
        if target is None or new_start < 0:
            raise ValueError("move nécessite clip_index et new_start")
        result["clips"][int(target)]["start"] = new_start
        result["clips"].sort(key=lambda clip: float(clip.get("start", 0)))
        return result
    if op == "duplicate":
        target = operation.get("clip_index")
        if target is None:
            raise ValueError("duplicate nécessite clip_index")
        clip = dict(result["clips"][int(target)])
        gap = float(clip["duration"]) + 0.25
        clip["start"] = float(clip["start"]) + gap
        result["clips"].insert(int(target) + 1, clip)
        return result
    if op == "add_marker":
        time = float(operation.get("time", -1))
        if time < 0:
            raise ValueError("Marker invalide")
        label = " ".join(str(operation.get("label") or "Marker").split())[:80] or "Marker"
        result["markers"].append({"time": time, "label": label})
        result["markers"].sort(key=lambda marker: float(marker.get("time", 0)))
        return result
    if op == "set_setting":
        key = str(operation.get("key") or "").strip()
        if not key or key not in {"ratio", "audio_cleanup", "caption_style", "social_preset"}:
            raise ValueError("Réglage Studio non autorisé")
        result["settings"][key] = operation.get("value")
        return result
    if op == "delete":
        target = operation.get("clip_index")
        if target is None:
            raise ValueError("delete nécessite clip_index")
        del result["clips"][int(target)]
        return result
    raise ValueError(f"Opération Studio non supportée: {op}")
