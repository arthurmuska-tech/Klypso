"""KLYPSO creator intelligence: candidate generation, scoring and creator memory.

The engine deliberately treats "viral" as an optimization target, not a promise.
It combines deterministic media/transcript signals, an LLM's semantic judgement,
and the creator's own history/feedback so each new project becomes more personal.
"""
from collections import Counter
import json
import math
from statistics import mean


ARCHETYPES = (
    "reaction",
    "punchline",
    "win",
    "fail",
    "surprise",
    "debate",
    "story",
    "tip",
    "challenge",
    "clutch",
)


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value, limit=220):
    return " ".join(str(value or "").split())[:limit]


def _safe_json(value):
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _segment_words(segment):
    return len(_text(segment.get("text", ""), 2000).split())


def _clip_text(segments, start, end, limit=260):
    bits = []
    for segment in segments:
        if _number(segment.get("end")) <= start or _number(segment.get("start")) >= end:
            continue
        text = _text(segment.get("text", ""), 180)
        if text:
            bits.append(text)
    return _text(" ".join(bits), limit)


def generate_intelligent_candidates(duration, segments=None, limit=60):
    """Build candidate windows around conversational/activity clusters.

    When timestamped transcription is available, windows follow speech clusters
    instead of blindly slicing the VOD every N seconds. We still add a sparse
    fallback grid so non-verbal moments are not ignored.
    """
    duration = _number(duration)
    if duration <= 0:
        return []

    valid = []
    for segment in segments or []:
        start = max(0.0, _number(segment.get("start")))
        end = min(duration, _number(segment.get("end")))
        if end <= start:
            continue
        valid.append({"start": start, "end": end, "text": _text(segment.get("text", ""), 2200)})
    valid.sort(key=lambda item: item["start"])

    candidates = []
    seen = set()

    def add(start, end, source):
        start = max(0.0, min(duration, start))
        end = max(start, min(duration, end))
        length = end - start
        if length < 10:
            return
        # Keep social-first windows compact; a long context window is less useful
        # unless it is unavoidable near the start/end of the source.
        if length > 58:
            end = min(duration, start + 58)
        key = (round(start, 1), round(end, 1))
        if key in seen:
            return
        seen.add(key)
        speech_words = sum(_segment_words(seg) for seg in valid if seg["end"] > start and seg["start"] < end)
        speech_density = speech_words / max(1.0, end - start)
        candidates.append(
            {
                "id": f"c{len(candidates) + 1}",
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "speech_words": speech_words,
                "speech_density": round(speech_density, 3),
                "context": _clip_text(valid, start, end),
                "source": source,
            }
        )

    if valid:
        group_start = valid[0]["start"]
        group_end = valid[0]["end"]
        for segment in valid[1:]:
            gap = segment["start"] - group_end
            proposed_end = segment["end"]
            if gap <= 2.3 and proposed_end - group_start <= 54:
                group_end = proposed_end
            else:
                add(group_start - 2.5, group_end + 2.8, "speech_cluster")
                group_start, group_end = segment["start"], segment["end"]
        add(group_start - 2.5, group_end + 2.8, "speech_cluster")

        # Focus windows around the densest passages as well as clusters.
        top_segments = sorted(valid, key=lambda s: _segment_words(s) / max(0.8, s["end"] - s["start"]), reverse=True)[:18]
        for segment in top_segments:
            center = (segment["start"] + segment["end"]) / 2
            add(center - 13.0, center + 15.0, "speech_focus")

    # Sparse grid preserves coverage for gameplay/reaction moments without speech.
    step = 24.0
    cursor = 0.0
    while cursor < duration and len(candidates) < limit + 12:
        add(cursor, min(duration, cursor + 34.0), "coverage_grid")
        cursor += step

    # Deterministically prioritize speech density and ideal social duration.
    def base_score(candidate):
        dur = candidate["duration"]
        duration_fit = max(0.0, 1.0 - abs(dur - 31.0) / 31.0)
        speech_fit = min(1.0, candidate["speech_density"] / 3.1)
        return round(100 * (0.58 * speech_fit + 0.30 * duration_fit + 0.12 * (1.0 if candidate["source"] != "coverage_grid" else 0.55)))

    for candidate in candidates:
        candidate["base_score"] = base_score(candidate)
    candidates.sort(key=lambda item: (item["base_score"], item["speech_density"]), reverse=True)
    for index, candidate in enumerate(candidates[:limit], start=1):
        candidate["id"] = f"c{index}"
    return candidates[:limit]


def _feedback_summary(db, user_id, limit=16):
    rows = db.execute(
        "SELECT candidate_id, decision, created_at, job_id FROM clip_feedback "
        "WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    feedback = []
    for row in rows:
        item = {
            "candidate_id": row["candidate_id"],
            "decision": row["decision"],
            "created_at": row["created_at"],
        }
        if row["job_id"]:
            job = db.execute(
                "SELECT result_json FROM jobs WHERE id=? AND user_id=?",
                (row["job_id"], user_id),
            ).fetchone()
            if job:
                saved = _safe_json(job["result_json"])
                for clip in (saved.get("ai", {}).get("clips") or []):
                    if str(clip.get("id")) == str(row["candidate_id"]):
                        item.update({
                            "title": _text(clip.get("title"), 90),
                            "hook": _text(clip.get("hook"), 130),
                            "archetype": clip.get("archetype", "unknown"),
                            "score": int(_number(clip.get("opportunity_score", clip.get("score", 0)))),
                        })
                        break
        feedback.append(item)
    return feedback


def _performance_summary(db, user_id, limit=24):
    rows = db.execute(
        "SELECT id, job_id, candidate_id, platform, views, likes, comments, shares, completion_rate "
        "FROM clip_metrics WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    if not rows:
        return {"metrics": [], "by_archetype": {}, "winners": []}

    max_views = max(int(row["views"] or 0) for row in rows) or 1
    metrics = []
    for row in rows:
        archetype = "unknown"
        title = ""
        hook = ""
        if row["job_id"]:
            job = db.execute(
                "SELECT result_json FROM jobs WHERE id=? AND user_id=?",
                (row["job_id"], user_id),
            ).fetchone()
            if job:
                saved = _safe_json(job["result_json"])
                for clip in (saved.get("ai", {}).get("clips") or []):
                    if str(clip.get("id")) == str(row["candidate_id"]):
                        archetype = clip.get("archetype", "unknown")
                        title = _text(clip.get("title"), 90)
                        hook = _text(clip.get("hook"), 130)
                        break

        views = max(0, int(row["views"] or 0))
        interactions = max(0, int(row["likes"] or 0)) + max(0, int(row["comments"] or 0)) + max(0, int(row["shares"] or 0))
        engagement_pct = (interactions / max(views, 1)) * 100.0
        completion = max(0.0, min(100.0, _number(row["completion_rate"], 0)))
        view_score = math.log1p(views) / math.log1p(max_views) * 100.0
        engagement_score = min(100.0, engagement_pct * 10.0)
        performance_score = 0.55 * view_score + 0.25 * engagement_score + 0.20 * completion
        metrics.append({
            "platform": row["platform"],
            "views": views,
            "likes": max(0, int(row["likes"] or 0)),
            "comments": max(0, int(row["comments"] or 0)),
            "shares": max(0, int(row["shares"] or 0)),
            "completion_rate": round(completion, 1),
            "performance_score": round(performance_score, 1),
            "archetype": archetype,
            "title": title,
            "hook": hook,
        })

    grouped = {}
    for metric in metrics:
        grouped.setdefault(metric["archetype"], []).append(metric["performance_score"])
    by_archetype = {key: round(mean(values), 1) for key, values in grouped.items()}
    winners = sorted(metrics, key=lambda item: item["performance_score"], reverse=True)[:5]
    return {"metrics": metrics, "by_archetype": by_archetype, "winners": winners}


def build_creator_memory(db, user_id, limit=8):
    """Read prior AI projects + feedback + persisted profile into creator DNA."""
    profile_row = db.execute(
        "SELECT profile_json FROM creator_ai_profiles WHERE user_id=?",
        (user_id,),
    ).fetchone()
    persisted = _safe_json(profile_row["profile_json"]) if profile_row else {}
    rows = db.execute(
        "SELECT id, payload_json, result_json, created_at FROM jobs "
        "WHERE user_id=? AND status='completed' AND result_json IS NOT NULL "
        "AND job_type IN ('ai_clip_analysis','ai_montage_analysis') "
        "ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()

    examples = []
    durations = []
    formats = Counter()
    archetypes = Counter()

    for row in rows:
        result = _safe_json(row["result_json"])
        ai = result.get("ai") or {}
        payload = _safe_json(row["payload_json"])
        output_format = payload.get("output_format")
        if output_format:
            formats[output_format] += 1
        for clip in (ai.get("clips") or [])[:5]:
            duration = _number(clip.get("end")) - _number(clip.get("start"))
            if duration > 0:
                durations.append(duration)
            archetype = clip.get("archetype")
            if archetype:
                archetypes[archetype] += 1
            if clip.get("title") or clip.get("hook"):
                examples.append(
                    {
                        "title": _text(clip.get("title"), 90),
                        "hook": _text(clip.get("hook"), 130),
                        "archetype": archetype or "unknown",
                        "score": int(_number(clip.get("opportunity_score", clip.get("score", 0)))),
                    }
                )

    persisted_examples = persisted.get("recent_winners") or []
    examples.extend(persisted_examples[-6:])
    examples = sorted(examples, key=lambda item: item.get("score", 0), reverse=True)[:6]
    feedback = _feedback_summary(db, user_id)
    performance = _performance_summary(db, user_id)
    kept = sum(item["decision"] == "keep" for item in feedback)
    rejected = sum(item["decision"] == "reject" for item in feedback)
    kept_archetypes = Counter(
        item.get("archetype") for item in feedback
        if item["decision"] == "keep" and item.get("archetype")
    )
    rejected_archetypes = Counter(
        item.get("archetype") for item in feedback
        if item["decision"] == "reject" and item.get("archetype")
    )

    return {
        "projects_analyzed": len(rows),
        "preferred_clip_duration_seconds": (
            float(persisted.get("preferred_clip_duration_seconds"))
            if persisted.get("preferred_clip_duration_seconds")
            else round(mean(durations), 1) if durations else 31.0
        ),
        "preferred_formats": list(dict.fromkeys(
            (persisted.get("preferred_formats") or []) + [item[0] for item in formats.most_common(3)]
        ))[:4],
        "preferred_archetypes": list(dict.fromkeys(
            (persisted.get("preferred_archetypes") or []) + [item[0] for item in archetypes.most_common(5)]
        ))[:6] or ["reaction", "punchline", "surprise"],
        "winning_examples": examples,
        "feedback": feedback,
        "feedback_kept": kept,
        "feedback_rejected": rejected,
        "kept_archetypes": dict(kept_archetypes),
        "rejected_archetypes": dict(rejected_archetypes),
        "performance_by_archetype": performance["by_archetype"],
        "performance_winners": performance["winners"],
        "performance_count": len(performance["metrics"]),
    }


def creator_memory_for_prompt(memory):
    if not memory:
        return "Aucun historique exploitable: découvre le style du créateur."
    lines = [
        f"- durée moyenne des clips retenus: {memory.get('preferred_clip_duration_seconds', 31)}s",
        f"- formats souvent utilisés: {', '.join(memory.get('preferred_formats') or ['9:16'])}",
        f"- scènes déjà appréciées: {', '.join(memory.get('preferred_archetypes') or ['reaction', 'punchline', 'surprise'])}",
        f"- feedback manuel: {memory.get('feedback_kept', 0)} conservés / {memory.get('feedback_rejected', 0)} rejetés",
        f"- archetypes explicitement gardés: {', '.join(memory.get('kept_archetypes', {}).keys()) or 'aucun encore'}",
        f"- archetypes explicitement rejetés: {', '.join(memory.get('rejected_archetypes', {}).keys()) or 'aucun encore'}",
    ]
    for example in memory.get("winning_examples", [])[:5]:
        lines.append(f"- gagnant historique: [{example['archetype']}] {example['title']} — {example['hook']}")
    for example in (memory.get("feedback") or [])[:4]:
        if example.get("title"):
            lines.append(f"- feedback {example['decision']}: [{example.get('archetype','unknown')}] {example.get('title')} — {example.get('hook','')}")
    if memory.get("performance_count"):
        lines.append(f"- performances réelles enregistrées: {memory['performance_count']}")
        for archetype, score in sorted((memory.get("performance_by_archetype") or {}).items(), key=lambda item: item[1], reverse=True)[:5]:
            lines.append(f"- performance {archetype}: {score}/100")
        for example in memory.get("performance_winners", [])[:3]:
            if example.get("title"):
                lines.append(f"- vidéo performante {example.get('platform')}: {example['title']} · {example['views']} vues · {example['performance_score']}/100")
    return "\n".join(lines)


def _context_similarity(left, right):
    left_tokens = {token.lower() for token in _text(left, 500).split() if len(token) > 2}
    right_tokens = {token.lower() for token in _text(right, 500).split() if len(token) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def tighten_clip_boundaries(clip, segments, pad_before=1.8, pad_after=3.0, min_duration=8.0):
    """Remove dead-air lead-in/out when timestamped speech is available."""
    if not segments:
        return clip
    start = _number(clip.get("start"))
    end = _number(clip.get("end"))
    overlapping = [
        segment for segment in segments
        if _number(segment.get("end")) > start and _number(segment.get("start")) < end
    ]
    if not overlapping:
        return clip
    speech_start = min(_number(segment.get("start")) for segment in overlapping)
    speech_end = max(_number(segment.get("end")) for segment in overlapping)
    new_start = max(start, speech_start - pad_before)
    new_end = min(end, speech_end + pad_after)
    if new_end - new_start < min_duration:
        return clip
    return {
        **clip,
        "start": round(new_start, 3),
        "end": round(new_end, 3),
        "duration": round(new_end - new_start, 3),
    }


def enrich_ai_result(result, candidates, memory, transcript_segments=None):
    """Validate model output and turn raw AI scores into an explainable ranking."""
    result = result if isinstance(result, dict) else {}
    by_id = {str(candidate["id"]): candidate for candidate in candidates}
    raw_clips = result.get("clips") or []
    normalized = []

    weights = {
        "hook_score": 0.16,
        "payoff_score": 0.14,
        "emotion_score": 0.11,
        "novelty_score": 0.10,
        "context_score": 0.10,
        "shareability_score": 0.10,
        "creator_fit_score": 0.11,
        "replay_score": 0.08,
        "base_score": 0.10,
    }

    for raw in raw_clips[:8]:
        candidate = by_id.get(str(raw.get("id")))
        if not candidate:
            continue
        start = max(candidate["start"] - 2.0, _number(raw.get("start"), candidate["start"]))
        end = min(candidate["end"] + 2.0, _number(raw.get("end"), candidate["end"]))
        start = min(start, candidate["end"] - 1.0)
        end = max(end, start + 8.0)
        end = min(end, candidate["end"] + 2.0)
        if end - start < 8:
            start, end = candidate["start"], candidate["end"]
        scores = {key: max(0, min(100, int(_number(raw.get(key), 60 if key != "base_score" else candidate["base_score"])))) for key in weights}
        weighted = sum(scores[key] * weight for key, weight in weights.items())
        item = {
                "id": candidate["id"],
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "score": int(round(weighted)),
                "opportunity_score": int(round(weighted)),
                "title": _text(raw.get("title"), 90) or "Moment fort",
                "hook": _text(raw.get("hook"), 150) or _text(candidate.get("context"), 120),
                "reason": _text(raw.get("reason"), 220) or "Contexte + densité + potentiel de payoff.",
                "archetype": raw.get("archetype") if raw.get("archetype") in ARCHETYPES else "surprise",
                "scores": scores,
                "context": candidate.get("context", ""),
            }
        if transcript_segments:
            item = tighten_clip_boundaries(item, transcript_segments)
        normalized.append(item)

    # Diversity gate: avoid producing five clips that are basically the same scene.
    normalized.sort(key=lambda item: (item["opportunity_score"], item["score"]), reverse=True)
    selected = []
    archetype_counts = Counter()
    for clip in normalized:
        overlap = any(
            abs(clip["start"] - kept["start"]) < 9
            or _context_similarity(clip.get("context", ""), kept.get("context", "")) >= 0.62
            for kept in selected
        )
        if overlap:
            continue
        if archetype_counts[clip["archetype"]] >= 2:
            continue
        selected.append(clip)
        archetype_counts[clip["archetype"]] += 1
        if len(selected) == 5:
            break

    # If the model was conservative, fill from deterministic candidates.
    if not raw_clips and len(selected) < min(3, len(candidates)):
        for candidate in candidates:
            if any(abs(candidate["start"] - clip["start"]) < 9 for clip in selected):
                continue
            selected.append(
                {
                    "id": candidate["id"],
                    "start": candidate["start"],
                    "end": candidate["end"],
                    "duration": candidate["duration"],
                    "score": candidate["base_score"],
                    "opportunity_score": candidate["base_score"],
                    "title": "Moment à tester",
                    "hook": _text(candidate.get("context"), 150) or "Passage dense ou prometteur.",
                    "reason": "Ajout de sécurité pour conserver une couverture de la VOD.",
                    "archetype": "surprise",
                    "scores": {key: candidate["base_score"] for key in weights if key != "base_score"} | {"base_score": candidate["base_score"]},
                    "context": candidate.get("context", ""),
                }
            )
            if len(selected) == 5:
                break

    kept_bias = memory.get("kept_archetypes", {}) if memory else {}
    rejected_bias = memory.get("rejected_archetypes", {}) if memory else {}
    performance_bias = memory.get("performance_by_archetype", {}) if memory else {}
    for clip in selected:
        bonus = min(8, int(kept_bias.get(clip["archetype"], 0)) * 2)
        penalty = min(8, int(rejected_bias.get(clip["archetype"], 0)) * 2)
        performance_adjustment = 0
        if clip["archetype"] in performance_bias:
            performance_adjustment = max(-6, min(6, round((performance_bias[clip["archetype"]] - 50.0) / 8.0)))
        clip["opportunity_score"] = max(0, min(100, clip["opportunity_score"] + bonus - penalty + performance_adjustment))
        clip["score"] = clip["opportunity_score"]
        clip["creator_fit_adjustment"] = bonus - penalty + performance_adjustment
        clip["performance_adjustment"] = performance_adjustment

    selected.sort(key=lambda item: item["opportunity_score"], reverse=True)
    selected_by_id = {str(clip["id"]): clip for clip in selected}
    requested_montage = (result.get("montage") or {}).get("clip_ids") or []
    montage_order = [str(clip_id) for clip_id in requested_montage if str(clip_id) in selected_by_id]
    montage_order.extend(
        clip["id"] for clip in selected if clip["id"] not in montage_order
    )
    montage_ids = montage_order[:5]

    return {
        "clips": selected,
        "montage": {
            "clip_ids": montage_ids,
            "opening_clip_id": montage_ids[0] if montage_ids else None,
            "closing_clip_id": montage_ids[-1] if montage_ids else None,
        },
        "summary": _text(result.get("summary"), 500) or "Sélection optimisée à partir des signaux disponibles.",
        "creator_memory_used": memory,
        "engine": "KLYPSO VIRAL ENGINE v1",
    }


def update_creator_memory(db, user_id, result, output_format):
    """Persist the latest successful selection without storing raw media."""
    row = db.execute(
        "SELECT profile_json FROM creator_ai_profiles WHERE user_id=?",
        (user_id,),
    ).fetchone()
    existing = _safe_json(row["profile_json"]) if row else {}
    recent = existing.get("recent_winners", [])
    for clip in (result.get("clips") or [])[:5]:
        recent.append(
            {
                "title": _text(clip.get("title"), 90),
                "hook": _text(clip.get("hook"), 140),
                "archetype": clip.get("archetype", "surprise"),
                "duration": round(_number(clip.get("duration")), 1),
                "score": int(_number(clip.get("opportunity_score"))),
            }
        )
    recent = recent[-12:]
    durations = [item["duration"] for item in recent if item.get("duration")]
    archetype_counts = Counter(item.get("archetype") for item in recent if item.get("archetype"))
    profile = {
        "preferred_clip_duration_seconds": round(mean(durations), 1) if durations else 31.0,
        "preferred_formats": list(dict.fromkeys([output_format] + existing.get("preferred_formats", [])))[:4],
        "preferred_archetypes": [item[0] for item in archetype_counts.most_common(6)],
        "recent_winners": recent,
        "updated_from_engine": "KLYPSO VIRAL ENGINE v1",
    }
    db.execute(
        "INSERT INTO creator_ai_profiles(user_id,profile_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
        "ON CONFLICT(user_id) DO UPDATE SET profile_json=excluded.profile_json,updated_at=CURRENT_TIMESTAMP",
        (user_id, json.dumps(profile, ensure_ascii=False)),
    )
