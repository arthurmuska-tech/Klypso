def generate_candidates(duration, window=35.0, stride=25.0):
    if duration <= 0:
        return []
    candidates = []
    start = 0.0
    index = 1
    while start < duration:
        end = min(start + window, duration)
        if end - start >= 8:
            candidates.append({"id": f"c{index}", "start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3)})
            index += 1
        start += stride
    return candidates
