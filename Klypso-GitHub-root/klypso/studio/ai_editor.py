def suggest_edits(timeline):
    suggestions = []
    if timeline.get("clips"):
        suggestions.append({"id": "remove-silence", "title": "Réduire les blancs", "reason": "Analyse audio à effectuer avant application.", "status": "proposal_only"})
        suggestions.append({"id": "hook", "title": "Renforcer l'introduction", "reason": "Le système peut proposer un autre début sans écraser l'original.", "status": "proposal_only"})
    return suggestions
