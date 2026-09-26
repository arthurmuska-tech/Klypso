def score_candidate(candidate, signals=None):
    signals = signals or {}
    components = {
        "audio": float(signals.get("audio", 0.0)),
        "reaction": float(signals.get("reaction", 0.0)),
        "language": float(signals.get("language", 0.0)),
        "context": float(signals.get("context", 0.0)),
        "rhythm": float(signals.get("rhythm", 0.0)),
        "visual_change": float(signals.get("visual_change", 0.0)),
        "repetition_penalty": float(signals.get("repetition_penalty", 0.0)),
        "silence_penalty": float(signals.get("silence_penalty", 0.0)),
    }
    raw = components["audio"] + components["reaction"] + components["language"] + components["context"] + components["rhythm"] + components["visual_change"] - components["repetition_penalty"] - components["silence_penalty"]
    potential = max(0.0, min(100.0, raw * 100.0 / 6.0))
    reasons = []
    labels = [("audio", "Forte réaction audio"), ("reaction", "Réaction détectée"), ("language", "Phrase exploitable détectée"), ("context", "Contexte intéressant"), ("rhythm", "Bon rythme"), ("visual_change", "Transition visuelle")]
    for key, label in labels:
        if components[key] >= 0.6:
            reasons.append(label)
    if not reasons:
        reasons.append("Moment candidat à vérifier")
    return {"potential": round(potential, 1), "components": components, "reasons": reasons}
