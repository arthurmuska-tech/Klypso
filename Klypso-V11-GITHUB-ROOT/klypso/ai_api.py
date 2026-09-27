import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

import requests
from flask import Blueprint, current_app, jsonify, request, session

from .auth import login_required
from .database import get_db
from .promo import effective_plan_key
from .clips.intelligence import (
    build_creator_memory,
    creator_memory_for_prompt,
    enrich_ai_result,
    generate_intelligent_candidates,
    update_creator_memory,
)
from .clips.renderer import concat_videos, render_candidate


ai_bp = Blueprint("ai_api", __name__)


def _keys(name):
    values = []
    for value in [os.getenv(name, "")] + [os.getenv(f"{name}_{i}", "") for i in range(1, 6)]:
        value = (value or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def _model(provider):
    return {
        "gemini": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "groq": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        "openrouter": os.getenv("OPENROUTER_MODEL", "openrouter/free"),
    }[provider]


def _json(value):
    return json.loads((value or "").strip())


def _audio(video_path):
    handle = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    audio = Path(handle.name)
    handle.close()
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(audio)],
        check=True,
        capture_output=True,
        text=True,
    )
    return audio


def _transcribe_groq(video_path, key):
    audio = _audio(video_path)
    try:
        with audio.open("rb") as stream:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (audio.name, stream, "audio/mpeg")},
                data={
                    "model": os.getenv("AI_TRANSCRIPTION_MODEL", "whisper-large-v3"),
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
                timeout=240,
            )
        response.raise_for_status()
        payload = response.json()
        segments = []
        for segment in payload.get("segments", []) or []:
            segments.append(
                {
                    "start": float(segment.get("start", 0)),
                    "end": float(segment.get("end", 0)),
                    "text": " ".join(str(segment.get("text", "")).split()),
                }
            )
        return {"text": payload.get("text", ""), "segments": segments}
    finally:
        audio.unlink(missing_ok=True)


def _prompt(duration, candidates, transcript_data=None, memory=None, mode="ai_clips", preferences=None):
    transcript_data = transcript_data or {}
    preferences = preferences or {}
    memory_text = creator_memory_for_prompt(memory or {})
    style = preferences.get("ai_style", "auto")
    scene_priority = preferences.get("scene_priority", "balanced")
    pace = preferences.get("pace", "natural")
    mode_text = (
        "CLIPS IA: produire 3 à 5 clips sociaux autonomes, chacun avec hook immédiat et payoff clair."
        if mode == "ai_clips"
        else "MONTAGE IA: sélectionner 3 à 5 scènes complémentaires qui racontent une mini-histoire et évitent les doublons."
    )
    return (
        "Tu es KLYPSO VIRAL ENGINE, monteur senior spécialisé Twitch, YouTube Shorts, TikTok et Reels.\n"
        "Objectif: maximiser les signaux de rétention, compréhension, émotion, partage et replay sans inventer un événement. "
        "Un score élevé est une opportunité éditoriale, pas une garantie de viralité.\n\n"
        f"MODE: {mode_text}\n"
        f"DURÉE SOURCE: {duration:.2f}s\n\n"
        "ADN DU CRÉATEUR (apprendre des projets précédents):\n"
        f"{memory_text}\n\n"
        "PRÉFÉRENCES DE CETTE PRODUCTION:\n"
        f"- style: {style}; priorité: {scene_priority}; rythme: {pace}\n"
        "Respecte ces préférences sans jamais inventer un événement.\n\n"
        "RUBRIQUE DE SÉLECTION:\n"
        "1) hook compréhensible très vite; 2) payoff ou révélation; 3) émotion/réaction/changement de dynamique; "
        "4) nouveauté; 5) contexte suffisant sans intro inutile; 6) partageabilité/replay; 7) adéquation au style précédent; "
        "8) potentiel de captions; 9) diversité entre scènes.\n\n"
        f"CANDIDATS: {json.dumps(candidates[:60], ensure_ascii=False)}\n\n"
        f"TRANSCRIPTION: {str(transcript_data.get('text', ''))[:45000]}\n"
        f"SEGMENTS HORODATÉS: {json.dumps((transcript_data.get('segments') or [])[:500], ensure_ascii=False)}\n\n"
        "Réponds uniquement avec un objet JSON. Choisis uniquement des IDs présents dans CANDIDATS. "
        "Pour chaque clip: id,start,end,title,hook,reason,archetype,hook_score,payoff_score,emotion_score,novelty_score,"
        "context_score,shareability_score,creator_fit_score,replay_score. Tous les scores 0-100. "
        "Ajoute summary et montage avec clip_ids/opening_clip_id/closing_clip_id."
    )


def _text(provider, key, duration, candidates, transcript_data, memory, mode, preferences):
    base = "https://api.groq.com/openai/v1" if provider == "groq" else "https://openrouter.ai/api/v1"
    response_format = {"type": "json_object"}
    if provider == "groq":
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "klypso_clip_selection",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "clips": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "start": {"type": "number"},
                                    "end": {"type": "number"},
                                    "title": {"type": "string"},
                                    "hook": {"type": "string"},
                                    "reason": {"type": "string"},
                                    "archetype": {"type": "string"},
                                    "hook_score": {"type": "number"},
                                    "payoff_score": {"type": "number"},
                                    "emotion_score": {"type": "number"},
                                    "novelty_score": {"type": "number"},
                                    "context_score": {"type": "number"},
                                    "shareability_score": {"type": "number"},
                                    "creator_fit_score": {"type": "number"},
                                    "replay_score": {"type": "number"},
                                },
                                "required": [
                                    "id", "start", "end", "title", "hook", "reason", "archetype",
                                    "hook_score", "payoff_score", "emotion_score", "novelty_score",
                                    "context_score", "shareability_score", "creator_fit_score", "replay_score",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "summary": {"type": "string"},
                        "montage": {
                            "type": "object",
                            "properties": {
                                "clip_ids": {"type": "array", "items": {"type": "string"}},
                                "opening_clip_id": {"type": ["string", "null"]},
                                "closing_clip_id": {"type": ["string", "null"]},
                            },
                            "required": ["clip_ids", "opening_clip_id", "closing_clip_id"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["clips", "summary", "montage"],
                    "additionalProperties": False,
                },
            },
        }

    response = requests.post(
        f"{base}/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "KLYPSO",
        },
        json={
            "model": _model(provider),
            "messages": [
                {
                    "role": "system",
                    "content": "Tu es un moteur de montage. Tu dois respecter strictement les timestamps et produire du JSON exploitable.",
                },
                {"role": "user", "content": _prompt(duration, candidates, transcript_data, memory, mode, preferences)},
            ],
            "temperature": 0.18,
            "response_format": response_format,
        },
        timeout=240,
    )
    response.raise_for_status()
    return _json(response.json()["choices"][0]["message"]["content"])


def _gemini_video(video_path, duration, candidates, memory, mode, preferences, key):
    path = Path(video_path)
    if path.stat().st_size >= 95 * 1024 * 1024:
        raise RuntimeError("inline_video_limit")
    mime = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".m4v": "video/mp4",
        ".avi": "video/x-msvideo",
    }.get(path.suffix.lower(), "video/mp4")
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{_model('gemini')}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": mime, "data": base64.b64encode(path.read_bytes()).decode("ascii")}},
                    {"text": _prompt(duration, candidates, {}, memory, mode, preferences)},
                ]
            }],
            "generationConfig": {"temperature": 0.18, "responseMimeType": "application/json"},
        },
        timeout=360,
    )
    response.raise_for_status()
    parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = next((part.get("text", "") for part in parts if part.get("text")), "")
    return _json(text)


def _route(video_path, duration, candidates, memory, mode, preferences):
    attempts = []
    for number, key in enumerate(_keys("GEMINI_API_KEY"), start=1):
        try:
            return (
                _gemini_video(video_path, duration, candidates, memory, mode, preferences, key),
                {"provider": "gemini", "key_slot": number, "attempts": attempts},
                {"text": "", "segments": []},
            )
        except Exception as exc:
            attempts.append({"provider": "gemini", "key_slot": number, "error": type(exc).__name__})

    transcript_data = {"text": "", "segments": []}
    groq_keys = _keys("GROQ_API_KEY")
    for number, key in enumerate(groq_keys, start=1):
        try:
            transcript_data = _transcribe_groq(video_path, key)
            if transcript_data.get("text") or transcript_data.get("segments"):
                break
        except Exception as exc:
            attempts.append({"provider": "groq-transcription", "key_slot": number, "error": type(exc).__name__})

    if transcript_data.get("text") or transcript_data.get("segments"):
        for number, key in enumerate(groq_keys, start=1):
            try:
                return (
                    _text("groq", key, duration, candidates, transcript_data, memory, mode, preferences),
                    {"provider": "groq", "key_slot": number, "attempts": attempts},
                    transcript_data,
                )
            except Exception as exc:
                attempts.append({"provider": "groq", "key_slot": number, "error": type(exc).__name__})
        for number, key in enumerate(_keys("OPENROUTER_API_KEY"), start=1):
            try:
                return (
                    _text("openrouter", key, duration, candidates, transcript_data, memory, mode, preferences),
                    {"provider": "openrouter", "key_slot": number, "attempts": attempts},
                    transcript_data,
                )
            except Exception as exc:
                attempts.append({"provider": "openrouter", "key_slot": number, "error": type(exc).__name__})

    raise RuntimeError("AI router exhausted")


def _job_for_user(job_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        row = db.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?",
            (job_id, session["user_id"]),
        ).fetchone()
    return row


def _load_ai_payload(job):
    payload = json.loads(job["payload_json"] or "{}")
    result = json.loads(job["result_json"] or "{}") if job["result_json"] else {}
    return payload, result


def _assert_advanced(user):
    if effective_plan_key(user) not in {"pro", "ultra"}:
        return jsonify({"error": "L'IA avancée est réservée aux plans Pro et Ultra."}), 403
    if not (_keys("GEMINI_API_KEY") or _keys("GROQ_API_KEY") or _keys("OPENROUTER_API_KEY")):
        return jsonify({"error": "Aucun moteur IA n'est configuré sur KLYPSO."}), 503
    return None


@ai_bp.get("/api/ai/status")
@login_required
def status():
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    providers = []
    if _keys("GEMINI_API_KEY"):
        providers.append("gemini")
    if _keys("GROQ_API_KEY"):
        providers.append("groq")
    if _keys("OPENROUTER_API_KEY"):
        providers.append("openrouter")
    return jsonify({
        "plan": effective_plan_key(user),
        "enabled": effective_plan_key(user) in {"pro", "ultra"} and bool(providers),
        "providers": providers,
        "engine": "KLYPSO VIRAL ENGINE v1",
    })


@ai_bp.post("/api/ai/analyze/<int:job_id>")
@login_required
def analyze_job(job_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, session["user_id"])).fetchone()
    denied = _assert_advanced(user)
    if denied:
        return denied
    if not job:
        return jsonify({"error": "Projet introuvable."}), 404

    payload = json.loads(job["payload_json"] or "{}")
    path = payload.get("path")
    if not path or not Path(path).exists():
        return jsonify({"error": "Vidéo introuvable."}), 404

    mode = payload.get("mode", "ai_clips")
    output_format = payload.get("output_format", "9:16")
    preferences = payload.get("preferences") or {}
    try:
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            memory = build_creator_memory(db, session["user_id"])
        from .clips.analyzer import analyze_media

        analysis = analyze_media(path)
        transcript_seed = []
        # When Gemini is selected, candidates still need deterministic coverage.
        candidates = generate_intelligent_candidates(analysis["duration"], transcript_seed)
        result, router, transcript_data = _route(path, analysis["duration"], candidates, memory, mode, preferences)

        # Groq transcription gives timestamped speech clusters; regenerate candidates
        # with these richer anchors and make one final deterministic selection pass.
        if transcript_data.get("segments"):
            candidates = generate_intelligent_candidates(analysis["duration"], transcript_data["segments"])
            result = enrich_ai_result(result, candidates, memory, transcript_data.get("segments", []))
        else:
            result = enrich_ai_result(result, candidates, memory)

        saved = {
            "mode": mode,
            "router": router,
            "ai": result,
            "analysis": analysis,
            "candidates": candidates,
            "transcript": transcript_data,
            "output_format": output_format,
            "preferences": preferences,
        }
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET status=?,result_json=?,error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                ("completed", json.dumps(saved, ensure_ascii=False), job_id),
            )
            update_creator_memory(db, session["user_id"], result, output_format)
            db.commit()
        return jsonify({
            "ok": True,
            "job_id": job_id,
            "result": saved,
            "message": "Analyse terminée: KLYPSO a appris du contexte précédent et classé les scènes.",
        })
    except Exception:
        current_app.logger.exception("AI router failed")
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET status=?,error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                ("failed", "AI router exhausted", job_id),
            )
            db.commit()
        return jsonify({"error": "Toutes les IA configurées ont échoué ou atteint leurs limites."}), 500


def _render_ai_clips(job, result, requested_ids=None):
    payload = json.loads(job["payload_json"] or "{}")
    source = Path(payload.get("path", ""))
    if not source.is_file():
        raise FileNotFoundError("Vidéo source introuvable.")

    output_format = payload.get("output_format", result.get("output_format", "9:16"))
    transcript = result.get("transcript", {}).get("segments", [])
    available = {str(c["id"]): c for c in result.get("ai", {}).get("clips", [])}
    ids = [str(value) for value in (requested_ids or []) if str(value) in available]
    if not ids:
        ids = [str(c["id"]) for c in result.get("ai", {}).get("clips", [])[:5]]

    folder = Path(current_app.config["STORAGE_PATH"]) / "users" / str(session["user_id"]) / "ai"
    folder.mkdir(parents=True, exist_ok=True)
    rendered = []
    for index, clip_id in enumerate(ids[:5], start=1):
        candidate = available[clip_id]
        output = folder / f"klypso-{job['id']}-clip-{index}.mp4"
        render_candidate(
            str(source),
            str(output),
            candidate,
            output_format=output_format,
            transcript_segments=transcript,
            subtitles=bool(transcript),
        )
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (session["user_id"], f"{candidate['title']}.mp4", str(output), "video/mp4", output.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()
        rendered.append({
            "id": clip_id,
            "media_id": media_id,
            "title": candidate["title"],
            "hook": candidate["hook"],
            "score": candidate["opportunity_score"],
            "download_url": f"/studio/ai-download/{media_id}",
        })
    return rendered


@ai_bp.post("/api/ai/render-clips/<int:job_id>")
@login_required
def render_clips(job_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, session["user_id"])).fetchone()
    denied = _assert_advanced(user)
    if denied:
        return denied
    if not job:
        return jsonify({"error": "Projet introuvable."}), 404
    if not job["result_json"]:
        return jsonify({"error": "Lance d'abord l'analyse IA."}), 409

    body = request.get_json(silent=True) or {}
    requested_ids = body.get("clip_ids") if isinstance(body.get("clip_ids"), list) else None
    try:
        result = json.loads(job["result_json"])
        rendered = _render_ai_clips(job, result, requested_ids)
        result["rendered_clips"] = rendered
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute("UPDATE jobs SET result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(result, ensure_ascii=False), job_id))
            db.commit()
        return jsonify({"ok": True, "clips": rendered})
    except Exception:
        current_app.logger.exception("AI clip render failed")
        return jsonify({"error": "Le rendu des clips a échoué. Vérifie que FFmpeg est disponible."}), 500


@ai_bp.post("/api/ai/render-montage/<int:job_id>")
@login_required
def render_montage(job_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, session["user_id"])).fetchone()
    denied = _assert_advanced(user)
    if denied:
        return denied
    if not job:
        return jsonify({"error": "Projet introuvable."}), 404
    if not job["result_json"]:
        return jsonify({"error": "Lance d'abord l'analyse IA."}), 409

    try:
        result = json.loads(job["result_json"])
        montage_ids = (result.get("ai", {}).get("montage", {}).get("clip_ids") or [])[:5]
        if not montage_ids:
            montage_ids = [clip["id"] for clip in result.get("ai", {}).get("clips", [])[:5]]

        rendered = _render_ai_clips(job, result, montage_ids)
        paths = []
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            for item in rendered:
                row = db.execute("SELECT stored_path FROM media_files WHERE id=? AND user_id=?", (item["media_id"], session["user_id"])).fetchone()
                if row:
                    paths.append(row["stored_path"])
        if not paths:
            raise RuntimeError("Aucun clip à concaténer.")

        folder = Path(current_app.config["STORAGE_PATH"]) / "users" / str(session["user_id"]) / "ai"
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / f"klypso-{job['id']}-montage-ia.mp4"
        concat_videos(paths, str(output))

        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (session["user_id"], f"Montage IA #{job['id']}.mp4", str(output), "video/mp4", output.stat().st_size),
            )
            media_id = cur.lastrowid
            result["rendered_montage"] = {
                "media_id": media_id,
                "download_url": f"/studio/ai-download/{media_id}",
                "clip_count": len(paths),
            }
            db.execute("UPDATE jobs SET result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(result, ensure_ascii=False), job_id))
            db.commit()
        return jsonify({"ok": True, "montage": result["rendered_montage"]})
    except Exception:
        current_app.logger.exception("AI montage render failed")
        return jsonify({"error": "Le montage IA n'a pas pu être exporté."}), 500
