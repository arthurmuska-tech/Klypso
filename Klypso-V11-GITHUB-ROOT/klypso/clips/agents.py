"""KLYPSO multi-agent creator engine.

The 15 specialists are lightweight, deterministic editorial agents. They share a
single evidence packet and produce a consensus dossier before/after an LLM pass.
This keeps the product fast and cost-aware: the architecture has 15 reasoning
roles without requiring 15 external model calls for every VOD.
"""
from collections import Counter
from statistics import mean


AGENT_NAMES = (
    "media_ingest",
    "transcript",
    "audio_rhythm",
    "vision_activity",
    "gameplay_context",
    "reaction_detector",
    "chat_context",
    "hook_lab",
    "retention",
    "novelty_diversity",
    "creator_dna",
    "performance_memory",
    "montage_director",
    "social_renderer",
    "distribution_loop",
)


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip_context(clip):
    return str(clip.get("context") or "").strip()


def _speech_density(candidates):
    values = [_num(c.get("speech_density")) for c in candidates if _num(c.get("speech_density")) > 0]
    return mean(values) if values else 0.0


def _duration_fit(candidates):
    if not candidates:
        return 0.0
    fits = [max(0.0, 1.0 - abs(_num(c.get("duration")) - 30.0) / 30.0) for c in candidates]
    return min(1.0, mean(fits))


def _word_count(segments):
    return sum(len(str(s.get("text") or "").split()) for s in segments or [])


def _reaction_terms(text):
    lowered = text.lower()
    terms = (
        "wtf", "what", "no way", "oh my", "let's go", "go go", "incroyable",
        "putain", "bordel", "énorme", "incroyable", "non", "jamais", "ouf",
        "clutch", "gg", "mdr", "lol", "mdrr", "wow",
    )
    return sum(1 for term in terms if term in lowered)


def _build_agent(name, score, signals, note):
    return {
        "name": name,
        "score": int(max(0, min(100, round(score)))),
        "signals": signals,
        "note": note,
    }


def build_montage_directive(clips, memory=None, preferences=None, agent_report=None):
    """Turn selected clips into a directed mini-story instead of a raw concat."""
    clips = [dict(c) for c in (clips or [])]
    if not clips:
        return {
            "story_arc": ["hook", "payoff"],
            "sequence": [],
            "transition": "fade",
            "caption_style": "dynamic",
            "social_preset": "dynamic",
        }

    prefs = preferences or {}
    ordered = sorted(clips, key=lambda c: _num(c.get("opportunity_score", c.get("score", 0))), reverse=True)
    by_type = {}
    for clip in clips:
        by_type.setdefault(clip.get("archetype", "surprise"), []).append(clip)

    def take(preferred, fallback_index):
        pool = by_type.get(preferred) or []
        if pool:
            return sorted(pool, key=lambda c: _num(c.get("opportunity_score", c.get("score", 0))), reverse=True)[0]
        return ordered[min(fallback_index, len(ordered) - 1)]

    roles = []
    opening = take("reaction", 0)
    roles.append(("hook", opening))
    setup = next((c for c in ordered if c["id"] != opening["id"] and c.get("archetype") in {"story", "tip", "debate", "challenge"}), None)
    if setup:
        roles.append(("setup", setup))
    escalation = next((c for c in ordered if c["id"] not in {x[1]["id"] for x in roles} and c.get("archetype") in {"win", "clutch", "surprise", "punchline"}), None)
    if escalation:
        roles.append(("escalation", escalation))
    payoff = take("clutch", min(2, len(ordered) - 1))
    if payoff["id"] not in {x[1]["id"] for x in roles}:
        roles.append(("payoff", payoff))
    closer = next((c for c in ordered if c["id"] not in {x[1]["id"] for x in roles}), None)
    if closer:
        roles.append(("closer", closer))

    seen = set()
    sequence = []
    for role, clip in roles:
        if clip["id"] in seen:
            continue
        seen.add(clip["id"])
        sequence.append({
            "clip_id": clip["id"],
            "role": role,
            "duration": round(_num(clip.get("duration")), 1),
            "transition_in": "fade" if role != "hook" else "hard_cut",
            "fade_seconds": 0.0 if role == "hook" else 0.12,
            "zoom": 1.06 if role in {"hook", "payoff"} else 1.02,
            "caption_style": prefs.get("caption_style", "dynamic"),
            "social_preset": prefs.get("social_preset", "dynamic"),
        })
        if len(sequence) >= 5:
            break

    return {
        "story_arc": [item["role"] for item in sequence],
        "sequence": sequence,
        "transition": "fade",
        "caption_style": prefs.get("caption_style", "dynamic"),
        "social_preset": prefs.get("social_preset", "dynamic"),
        "director_note": "Hook immédiat → contexte utile → montée → payoff → sortie mémorable.",
        "agent_consensus": round(_num((agent_report or {}).get("consensus_score"), 0)),
    }


def run_agent_suite(duration, analysis=None, segments=None, candidates=None, memory=None, preferences=None):
    """Run 15 specialized passes over the same evidence packet."""
    analysis = analysis or {}
    segments = segments or []
    candidates = candidates or []
    memory = memory or {}
    preferences = preferences or {}

    duration = max(0.0, _num(duration))
    words = _word_count(segments)
    density = _speech_density(candidates)
    context_text = " ".join(_clip_context(c) for c in candidates[:20])
    reaction_hits = _reaction_terms(context_text)
    streams = analysis.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    width = _num(video_stream.get("width"), 0)
    height = _num(video_stream.get("height"), 0)
    fps_text = str(video_stream.get("avg_frame_rate") or "")
    source_landscape = width >= height if width and height else True

    preferred_archetypes = set(memory.get("preferred_archetypes") or [])
    performance_by_type = memory.get("performance_by_archetype") or {}
    rejected = memory.get("rejected_archetypes") or {}

    agent_inputs = {
        "media_ingest": (
            98 if analysis.get("has_video") else 20,
            {"duration": round(duration, 2), "video": bool(analysis.get("has_video")), "audio": bool(analysis.get("has_audio")), "resolution": f"{int(width)}x{int(height)}" if width and height else "unknown"},
            "Vérifie la matière et le format source.",
        ),
        "transcript": (
            min(100, 35 + min(65, words / max(1.0, duration) * 11)),
            {"words": words, "timestamped_segments": len(segments)},
            "Mesure la matière dialoguée et sa précision temporelle.",
        ),
        "audio_rhythm": (
            min(100, 42 + density * 13),
            {"speech_density": round(density, 2), "audio_present": bool(analysis.get("has_audio"))},
            "Repère le rythme et les passages où la bande-son porte le moment.",
        ),
        "vision_activity": (
            min(100, 46 + (18 if source_landscape else 8) + min(34, len(candidates) * 0.5)),
            {"scene_candidates": len(candidates), "landscape_source": source_landscape, "fps": fps_text or "unknown"},
            "Couverture visuelle sans dépendre du dialogue.",
        ),
        "gameplay_context": (
            min(100, 35 + reaction_hits * 3 + (18 if "gameplay" == preferences.get("scene_priority") else 0)),
            {"reaction_markers": reaction_hits, "priority": preferences.get("scene_priority", "balanced")},
            "Détecte les passages compatibles avec gameplay/action/réaction.",
        ),
        "reaction_detector": (
            min(100, 32 + reaction_hits * 5),
            {"reaction_markers": reaction_hits},
            "Cherche les ruptures émotionnelles et exclamations.",
        ),
        "chat_context": (
            min(100, 40 + min(60, len(context_text.split()) / 45)),
            {"context_words": len(context_text.split()), "chat_signal": "not_connected"},
            "Prépare un canal de signaux chat quand il sera branché.",
        ),
        "hook_lab": (
            min(100, 48 + len(candidates) * 0.55 + (10 if preferences.get("ai_style") == "punchy" else 0)),
            {"candidate_pool": len(candidates), "style": preferences.get("ai_style", "auto")},
            "Cherche les ouvertures immédiatement compréhensibles.",
        ),
        "retention": (
            52 + _duration_fit(candidates) * 38,
            {"duration_fit": round(_duration_fit(candidates), 3)},
            "Privilégie un setup court et un payoff identifiable.",
        ),
        "novelty_diversity": (
            min(100, 48 + len({c.get("archetype") for c in candidates if c.get("archetype")}) * 4),
            {"distinct_signals": len({c.get("source") for c in candidates}), "candidate_types": len({c.get("archetype") for c in candidates if c.get("archetype")})},
            "Évite les cinq variantes du même moment.",
        ),
        "creator_dna": (
            min(100, 38 + len(preferred_archetypes) * 9 + min(25, memory.get("projects_analyzed", 0) * 3)),
            {"projects_learned": memory.get("projects_analyzed", 0), "preferred_archetypes": sorted(preferred_archetypes)[:6]},
            "Ancre les choix dans les goûts déjà observés.",
        ),
        "performance_memory": (
            min(100, 42 + min(58, len(performance_by_type) * 8)),
            {"tracked_archetypes": len(performance_by_type), "best_known": sorted(performance_by_type.items(), key=lambda x: x[1], reverse=True)[:4]},
            "Utilise les performances réelles quand elles existent.",
        ),
        "montage_director": (
            min(100, 45 + min(55, len(candidates) * 0.7)),
            {"target_scenes": min(5, len(candidates)), "mode": preferences.get("mode", "ai_clips")},
            "Construit une progression plutôt qu'une simple concaténation.",
        ),
        "social_renderer": (
            min(100, 54 + (16 if preferences.get("subtitles", True) else 4) + (12 if preferences.get("brand_kit") else 0)),
            {"format": preferences.get("output_format", "9:16"), "caption_style": preferences.get("caption_style", "dynamic"), "preset": preferences.get("social_preset", "dynamic")},
            "Optimise le rendu natif social: cadrage, captions et audio.",
        ),
        "distribution_loop": (
            min(100, 44 + (20 if preferences.get("distribution_ready") else 0) + min(36, memory.get("performance_count", 0) * 2)),
            {"ready": bool(preferences.get("distribution_ready")), "performance_events": memory.get("performance_count", 0)},
            "Prépare publication, feedback et apprentissage post-publication.",
        ),
    }

    agents = [_build_agent(name, *agent_inputs[name]) for name in AGENT_NAMES]
    consensus = round(mean(agent["score"] for agent in agents)) if agents else 0

    favored = sorted(
        ((key, value) for key, value in performance_by_type.items() if key not in rejected),
        key=lambda item: item[1],
        reverse=True,
    )[:4]

    return {
        "version": "KLYPSO AGENT GRID v1",
        "agent_count": len(AGENT_NAMES),
        "agents": agents,
        "consensus_score": consensus,
        "priority_archetypes": [key for key, _ in favored] or list(preferred_archetypes)[:4],
        "coverage": {
            "duration": round(duration, 2),
            "candidate_count": len(candidates),
            "speech_words": words,
            "speech_density": round(density, 3),
            "reaction_markers": reaction_hits,
        },
    }
