def select_candidates(candidates, limit=20, min_gap=8.0):
    selected = []
    for candidate in sorted(candidates, key=lambda c: c.get("score", {}).get("potential", 0), reverse=True):
        if all(abs(candidate["start"] - other["start"]) >= min_gap for other in selected):
            selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected
