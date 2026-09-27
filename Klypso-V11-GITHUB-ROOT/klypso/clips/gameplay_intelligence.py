"""Gameplay-aware evidence layer for KLYPSO.

This is deliberately heuristic: it combines scene/audio/chat/transcript cues
and optional game title metadata. It does not claim game-specific object
recognition unless a vision provider supplies that evidence.
"""
import re


_GAME_TERMS = {
    "fps": ("kill", "headshot", "clutch", "ace", "round", "recoil", "enemy", "zone", "rank"),
    "battle_royale": ("zone", "storm", "last", "squad", "knock", "kill", "clutch", "win"),
    "moba": ("tower", "baron", "dragon", "gank", "ace", "pentakill", "objective"),
    "football": ("goal", "penalty", "save", "assist", "match", "winner"),
    "variety": ("win", "fails", "challenge", "reaction", "wtf", "insane"),
}


def classify_game_context(game_title="", transcript="", chat_terms=None):
    text = " ".join(str(transcript or "").lower().split())
    extra = " ".join(str(item) for item in (chat_terms or [])).lower()
    haystack = f"{text} {extra}"
    if not haystack.strip() and not str(game_title).strip():
        return {"genre": "unknown", "confidence": 0.0, "matched_terms": []}
    title = str(game_title or "").lower()
    matches = {}
    for genre, terms in _GAME_TERMS.items():
        hits = [term for term in terms if re.search(rf"\b{re.escape(term)}\b", haystack)]
        title_hits = [term for term in terms if term in title]
        matches[genre] = list(dict.fromkeys(hits + title_hits))
    genre, hits = max(matches.items(), key=lambda pair: len(pair[1]))
    total = len(hits)
    return {
        "genre": genre,
        "confidence": round(min(1.0, total / 5.0), 3),
        "matched_terms": hits[:20],
        "game_title": str(game_title)[:120],
    }


def enrich_gameplay_candidates(candidates, game_context):
    context = game_context or {}
    genre = context.get("genre", "unknown")
    terms = set(context.get("matched_terms") or [])
    enriched = []
    for candidate in candidates or []:
        item = dict(candidate)
        text = str(candidate.get("context") or "").lower()
        hits = sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", text))
        source_bonus = 0.12 if candidate.get("source") in {"chat_spike", "media_event"} else 0.0
        semantic_bonus = min(0.65, hits * 0.13)
        item["gameplay_signal"] = round(min(1.0, source_bonus + semantic_bonus), 3)
        item["gameplay_genre"] = genre
        if genre != "unknown" and item["gameplay_signal"] >= 0.35:
            item["scene_type"] = "gameplay_event"
        enriched.append(item)
    return enriched
