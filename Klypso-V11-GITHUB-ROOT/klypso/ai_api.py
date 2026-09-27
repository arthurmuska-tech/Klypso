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
from .clips.agents import build_montage_directive, run_agent_suite
from .clips.chat_intelligence import build_chat_signals, enrich_candidates_with_chat_signals, generate_chat_candidates, normalize_chat_messages
from .clips.media_intelligence import analyze_media_signals, enrich_candidates_with_media_signals, generate_signal_candidates
from .clips.renderer import concat_videos, render_candidate
from .clips.vision_tracking import analyze_face_tracking, enrich_candidates_with_face_tracking
from .clips.gameplay_intelligence import classify_game_context, enrich_gameplay_candidates
from .clips.audio_intelligence import analyze_audio_quality, enrich_candidates_with_audio_quality
from .social_connections import connection_status
from .social_profiles import clamp_candidate_to_profile, get_social_profile
from .ai_assets import asset_status, compose_assets, generate_broll_image, generate_voiceover


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


def _prompt(duration, candidates, transcript_data=None, memory=None, mode="ai_clips", preferences=None, agent_report=None):
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
        "PREUVES MULTIMODALES:\n"
        f"Media: {json.dumps(preferences.get('_media_signals', {}), ensure_ascii=False)[:12000]}\n"
        f"Vision/tracking: {json.dumps(preferences.get('_vision_tracking', {}), ensure_ascii=False)[:8000]}\n"
        f"Chat: {json.dumps(preferences.get('_chat_signals', {}), ensure_ascii=False)[:12000]}\n"
        f"Gameplay: {json.dumps(preferences.get('_game_context', {}), ensure_ascii=False)[:4000]}\n"
        f"Audio quality: {json.dumps(preferences.get('_audio_quality', {}), ensure_ascii=False)[:4000]}\n\n"
        "DOSSIER DES 15 AGENTS KLYPSO:\n"
        f"{json.dumps({'consensus_score': (agent_report or {}).get('consensus_score', 0), 'priority_archetypes': (agent_report or {}).get('priority_archetypes', []), 'agents': [{'name': a.get('name'), 'score': a.get('score'), 'signals': a.get('signals')} for a in (agent_report or {}).get('agents', [])]}, ensure_ascii=False)}\n\n"
        "RUBRIQUE DE SÉLECTION:\n"
        "1) hook compréhensible très vite; 2) payoff ou révélation; 3) émotion/réaction/changement de dynamique; "
        "4) nouveauté; 5) contexte suffisant sans intro inutile; 6) partageabilité/replay; 7) adéquation au style précédent; "
        "8) potentiel de captions; 9) diversité entre scènes.\n\n"
        f"CANDIDATS: {json.dumps(candidates[:60], ensure_ascii=False)}\n\n"
        f"TRANSCRIPTION: {str(transcript_data.get('text', ''))[:45000]}\n"
        f"SEGMENTS HORODATÉS: {json.dumps((transcript_data.get('segments') or [])[:500], ensure_ascii=False)}\n\n"
        "Réponds uniquement avec un objet JSON. Choisis uniquement des IDs présents dans CANDIDATS. "
        "Pour chaque clip: id,start,end,title,hook,reason,archetype,hook_score,payoff_score,emotion_score,novelty_score,"
        "context_score,shareability_score,creator_fit_score,replay_score,focus_x,focus_y,reframe_mode. "
        "focus_x et focus_y sont des coordonnées normalisées 0-1 du sujet principal à conserver dans le cadrage vertical; "
        "reframe_mode vaut smart_face, smart_gameplay, smart_center ou static_layout selon la preuve disponible. "
        "Tous les scores vont de 0 à 100. Ajoute summary et montage avec clip_ids/opening_clip_id/closing_clip_id."
    )


def _text(provider, key, duration, candidates, transcript_data, memory, mode, preferences, agent_report=None):
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
                                    "focus_x": {"type": "number"},
                                    "focus_y": {"type": "number"},
                                    "reframe_mode": {"type": "string"},
                                },
                                "required": [
                                    "id", "start", "end", "title", "hook", "reason", "archetype",
                                    "hook_score", "payoff_score", "emotion_score", "novelty_score",
                                    "context_score", "shareability_score", "creator_fit_score", "replay_score",
                                    "focus_x", "focus_y", "reframe_mode",
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
                {"role": "user", "content": _prompt(duration, candidates, transcript_data, memory, mode, preferences, agent_report)},
            ],
            "temperature": 0.18,
            "response_format": response_format,
        },
        timeout=240,
    )
    response.raise_for_status()
    return _json(response.json()["choices"][0]["message"]["content"])


def _gemini_video(video_path, duration, candidates, memory, mode, preferences, key, agent_report=None):
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
                    {"text": _prompt(duration, candidates, {}, memory, mode, preferences, agent_report)},
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


def _local_signal_result(candidates, mode="ai_clips"):
    """Keyless fallback using deterministic media/chat/face signals."""
    ranked = []
    for candidate in candidates or []:
        media = max(0.0, min(1.0, float(candidate.get("media_signal_score", 0.0) or 0.0)))
        chat = max(0.0, min(100.0, float(candidate.get("chat_signal_score", 0.0) or 0.0))) / 100.0
        base = max(0.0, min(100.0, float(candidate.get("base_score", 0.0) or 0.0))) / 100.0
        speech = max(0.0, min(1.0, float(candidate.get("speech_density", 0.0) or 0.0) / 3.0))
        score = 100.0 * (0.36 * base + 0.30 * media + 0.20 * chat + 0.14 * speech)
        ranked.append((score, candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)

    clips = []
    archetype_by_source = {
        "chat_spike": "reaction",
        "audio_peak": "reaction",
        "scene_change": "surprise",
        "media_event": "surprise",
        "speech_cluster": "story",
        "speech_focus": "punchline",
    }
    for index, (score, candidate) in enumerate(ranked[:5], start=1):
        context = " ".join(str(candidate.get("context", "")).split())
        source = str(candidate.get("source", "coverage_grid"))
        archetype = archetype_by_source.get(source, "surprise")
        hook = context[:150] if context else {
            "chat_spike": "Le chat a explosé à ce moment-là.",
            "reaction": "Réaction détectée.",
            "media_event": "Moment de rupture détecté.",
        }.get(source, "Moment fort détecté dans la VOD.")
        clips.append({
            "id": candidate["id"],
            "start": candidate["start"],
            "end": candidate["end"],
            "title": f"Moment {index}",
            "hook": hook,
            "reason": "Sélection locale à partir des signaux média, chat, activité et rythme.",
            "archetype": archetype,
            "hook_score": round(min(100, score + 6)),
            "payoff_score": round(min(100, score + 2)),
            "emotion_score": round(min(100, score + (14 if source in {"chat_spike", "audio_peak"} else 6))),
            "novelty_score": round(min(100, score)),
            "context_score": round(min(100, 50 + len(context) * 0.8)),
            "shareability_score": round(min(100, score)),
            "creator_fit_score": round(min(100, score)),
            "replay_score": round(min(100, score)),
            "focus_x": candidate.get("focus_x", 0.5),
            "focus_y": candidate.get("focus_y", 0.5),
            "reframe_mode": candidate.get("reframe_mode", "smart_center"),
        })
    ids = [clip["id"] for clip in clips]
    return {
        "clips": clips,
        "summary": "Analyse locale sans clé cloud: signaux média + chat + historique disponibles.",
        "montage": {
            "clip_ids": ids,
            "opening_clip_id": ids[0] if ids else None,
            "closing_clip_id": ids[-1] if ids else None,
        },
        "engine": "KLYPSO LOCAL VIRAL ENGINE v1",
    }


def _route(video_path, duration, candidates, memory, mode, preferences, agent_report=None):
    attempts = []
    for number, key in enumerate(_keys("GEMINI_API_KEY"), start=1):
        try:
            return (
                _gemini_video(video_path, duration, candidates, memory, mode, preferences, key, agent_report),
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
                    _text("groq", key, duration, candidates, transcript_data, memory, mode, preferences, agent_report),
                    {"provider": "groq", "key_slot": number, "attempts": attempts},
                    transcript_data,
                )
            except Exception as exc:
                attempts.append({"provider": "groq", "key_slot": number, "error": type(exc).__name__})
        for number, key in enumerate(_keys("OPENROUTER_API_KEY"), start=1):
            try:
                return (
                    _text("openrouter", key, duration, candidates, transcript_data, memory, mode, preferences, agent_report),
                    {"provider": "openrouter", "key_slot": number, "attempts": attempts},
                    transcript_data,
                )
            except Exception as exc:
                attempts.append({"provider": "openrouter", "key_slot": number, "error": type(exc).__name__})

    # No cloud provider is configured or all are unavailable: keep the workflow usable.
    return (
        _local_signal_result(candidates, mode),
        {"provider": "local_signal", "key_slot": 0, "attempts": attempts},
        {"text": "", "segments": []},
    )



def _saved_job_clip(job_id, clip_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?",
            (job_id, session["user_id"]),
        ).fetchone()
    if not job:
        raise LookupError("Projet introuvable.")
    if not job["result_json"]:
        raise RuntimeError("Lance d'abord l'analyse IA.")
    saved = json.loads(job["result_json"] or "{}")
    clips = saved.get("ai", {}).get("clips") or []
    clip = next((item for item in clips if str(item.get("id")) == str(clip_id)), None)
    if not clip:
        raise LookupError("Clip introuvable.")
    return job, saved, clip



@ai_bp.post("/api/ai/compose-assets/<int:job_id>")
@login_required
def compose_clip_assets(job_id):
    body = request.get_json(silent=True) or {}
    clip_id = str(body.get("clip_id") or "")
    if not clip_id:
        return jsonify({"error": "clip_id est requis."}), 400
    try:
        job, saved, clip = _saved_job_clip(job_id, clip_id)
        folder = Path(current_app.config["STORAGE_PATH"]) / "users" / str(session["user_id"]) / "ai-assets"
        folder.mkdir(parents=True, exist_ok=True)

        broll_prompt = " ".join(str(body.get("broll_prompt") or "").split())[:1200]
        if not broll_prompt:
            broll_prompt = (
                "Vertical social B-roll for a gaming creator. Illustrate the emotion or concept of this clip "
                "without showing the real creator and without inventing specific game events: "
                + str(clip.get("context") or clip.get("hook") or clip.get("title") or "")
            )[:1200]
        broll_path = folder / f"klypso-{job_id}-compose-{clip_id}.png"
        generate_broll_image(broll_prompt, broll_path, aspect_ratio="9:16")

        voice_text = " ".join(str(body.get("voice_text") or clip.get("hook") or clip.get("title") or "").split())[:5000]
        voice_path = folder / f"klypso-{job_id}-compose-{clip_id}.mp3"
        generate_voiceover(voice_text, voice_path, voice_id=body.get("voice_id"))

        rendered = _render_ai_clips(job, saved, requested_ids=[clip_id])
        if not rendered:
            raise RuntimeError("Impossible de rendre le clip de base.")
        base_media_id = rendered[0]["media_id"]
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            base_row = db.execute(
                "SELECT stored_path FROM media_files WHERE id=? AND user_id=?",
                (base_media_id, session["user_id"]),
            ).fetchone()
        if not base_row:
            raise RuntimeError("Clip de base introuvable.")

        output = folder / f"klypso-{job_id}-clip-{clip_id}-ai-assets.mp4"
        compose_assets(base_row["stored_path"], output, broll_image=broll_path, voiceover_audio=voice_path, broll_start=1.5, broll_duration=4.5)

        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (session["user_id"], f"{clip.get('title','Clip')} · AI assets.mp4", str(output), "video/mp4", output.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()
        saved.setdefault("ai_assets", {}).setdefault("composed", []).append({
            "clip_id": clip_id,
            "media_id": media_id,
            "broll_prompt": broll_prompt,
            "voice_text": voice_text,
        })
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(saved, ensure_ascii=False), job_id),
            )
            db.commit()
        return jsonify({
            "ok": True,
            "clip_id": clip_id,
            "media_id": media_id,
            "download_url": f"/studio/ai-download/{media_id}",
            "message": "B-roll + voiceover générés et composés dans un MP4.",
        }), 201
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        current_app.logger.exception("AI asset composition failed")
        return jsonify({"error": "La composition B-roll + voiceover a échoué. Vérifie Gemini, ElevenLabs et FFmpeg."}), 503


@ai_bp.get("/api/ai/assets/status")
@login_required
def assets_status():
    status = asset_status()
    return jsonify({
        "ok": True,
        "broll": status["ai_broll"],
        "voiceover": status["ai_voiceover"],
        "provider_state": {
            "gemini": status["ai_broll"],
            "elevenlabs": status["ai_voiceover"],
        },
    })


@ai_bp.post("/api/ai/broll/<int:job_id>")
@login_required
def generate_broll(job_id):
    body = request.get_json(silent=True) or {}
    clip_id = str(body.get("clip_id") or "")
    if not clip_id:
        return jsonify({"error": "clip_id est requis."}), 400
    try:
        job, saved, clip = _saved_job_clip(job_id, clip_id)
        prompt = " ".join(str(body.get("prompt") or "").split())[:1200]
        if not prompt:
            context = str(clip.get("context") or clip.get("hook") or clip.get("title") or "").strip()
            prompt = (
                f"Vertical social B-roll for a gaming creator. Illustrate this moment without "
                f"showing the real creator or inventing specific game footage: {context}"
            )[:1200]
        aspect_ratio = str(body.get("aspect_ratio") or "9:16")
        folder = Path(current_app.config["STORAGE_PATH"]) / "users" / str(session["user_id"]) / "ai-assets"
        output = folder / f"klypso-{job_id}-broll-{clip_id}.png"
        generate_broll_image(prompt, output, aspect_ratio=aspect_ratio)
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (session["user_id"], output.name, str(output), "image/png", output.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()
        saved.setdefault("ai_assets", {}).setdefault("broll", []).append({
            "clip_id": clip_id,
            "media_id": media_id,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        })
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(saved, ensure_ascii=False), job_id),
            )
            db.commit()
        return jsonify({
            "ok": True,
            "clip_id": clip_id,
            "media_id": media_id,
            "prompt": prompt,
            "download_url": f"/studio/ai-download/{media_id}",
        }), 201
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        current_app.logger.exception("B-roll generation failed")
        return jsonify({"error": "Le B-roll IA n'a pas pu être généré. Vérifie la configuration Gemini."}), 503


@ai_bp.post("/api/ai/voiceover/<int:job_id>")
@login_required
def generate_clip_voiceover(job_id):
    body = request.get_json(silent=True) or {}
    clip_id = str(body.get("clip_id") or "")
    try:
        if clip_id:
            job, saved, clip = _saved_job_clip(job_id, clip_id)
            default_text = str(clip.get("hook") or clip.get("title") or clip.get("context") or "")
        else:
            with get_db(current_app.config["DATABASE_PATH"]) as db:
                job = db.execute(
                    "SELECT * FROM jobs WHERE id=? AND user_id=?",
                    (job_id, session["user_id"]),
                ).fetchone()
            if not job or not job["result_json"]:
                return jsonify({"error": "Projet introuvable ou analyse absente."}), 404
            saved = json.loads(job["result_json"] or "{}")
            default_text = str(saved.get("ai", {}).get("summary") or "Voici le moment fort de la session.")
        text_value = " ".join(str(body.get("text") or default_text).split())[:5000]
        if not text_value:
            return jsonify({"error": "Aucun texte de voiceover."}), 400
        folder = Path(current_app.config["STORAGE_PATH"]) / "users" / str(session["user_id"]) / "ai-assets"
        output = folder / f"klypso-{job_id}-voiceover-{clip_id or 'summary'}.mp3"
        generate_voiceover(text_value, output, voice_id=body.get("voice_id"))
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (session["user_id"], output.name, str(output), "audio/mpeg", output.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()
        saved.setdefault("ai_assets", {}).setdefault("voiceover", []).append({
            "clip_id": clip_id or None,
            "media_id": media_id,
            "text": text_value,
        })
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(saved, ensure_ascii=False), job_id),
            )
            db.commit()
        return jsonify({
            "ok": True,
            "clip_id": clip_id or None,
            "media_id": media_id,
            "text": text_value,
            "download_url": f"/studio/ai-download/{media_id}",
        }), 201
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        current_app.logger.exception("Voiceover generation failed")
        return jsonify({"error": "Le voiceover IA n'a pas pu être généré. Vérifie ElevenLabs et ELEVENLABS_VOICE_ID."}), 503


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
    return None


@ai_bp.get("/api/ai/status")
@login_required
def status():
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    providers = []
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        social = connection_status(db, session["user_id"])
    native_platforms = [platform for platform, item in social.items() if item.get("connected") and item.get("adapter") == "oauth"]
    if _keys("GEMINI_API_KEY"):
        providers.append("gemini")
    if _keys("GROQ_API_KEY"):
        providers.append("groq")
    if _keys("OPENROUTER_API_KEY"):
        providers.append("openrouter")
    return jsonify({
        "plan": effective_plan_key(user),
        "enabled": effective_plan_key(user) in {"pro", "ultra"},
        "providers": providers,
        "local_fallback": True,
        "engine": "KLYPSO VIRAL ENGINE v3 · 15 agents + media/chat intelligence",
        "capabilities": {
            "ffmpeg_media_signals": True,
            "chat_import": True,
            "creator_dna": True,
            "performance_memory": True,
            "smart_reframe": True,
            "face_tracking": True,
            "gameplay_intelligence": True,
            "social_renderer": True,
            "scheduled_distribution": True,
            "native_platform_posting": bool(native_platforms),
            "native_platforms": native_platforms,
            "social_multi_render": True,
            "ai_broll": asset_status()["ai_broll"],
            "ai_voiceover": asset_status()["ai_voiceover"],
            "local_signal_fallback": True,
            **asset_status(),
        },
    })


@ai_bp.post("/api/ai/analyze/<int:job_id>")
@login_required
def analyze_job(job_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        job = db.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?",
            (job_id, session["user_id"]),
        ).fetchone()

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
    preferences = dict(payload.get("preferences") or {})
    preferences.setdefault("mode", mode)
    preferences.setdefault("output_format", output_format)
    preferences.setdefault("distribution_ready", False)

    try:
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            memory = build_creator_memory(db, session["user_id"])

        from .clips.analyzer import analyze_media

        analysis = analyze_media(path)

        # Local media intelligence: scene changes, silence regions, audio peaks.
        try:
            media_signals = analyze_media_signals(path)
        except Exception as signal_exc:
            current_app.logger.warning("Media signal analysis unavailable: %s", type(signal_exc).__name__)
            media_signals = {
                "engine": "ffmpeg-media-signals-v1",
                "scene_changes": [],
                "scene_change_count": 0,
                "silences": [],
                "silence_count": 0,
                "audio_peaks": [],
                "audio_peak_count": 0,
                "event_windows": [],
            }

        try:
            face_tracking = analyze_face_tracking(path)
        except Exception as vision_exc:
            current_app.logger.warning("Face tracking unavailable: %s", type(vision_exc).__name__)
            face_tracking = {"engine": "opencv-face-v1", "available": False, "tracks": []}

        chat_messages = normalize_chat_messages(payload.get("chat_messages") or [])
        chat_signals = build_chat_signals(chat_messages)
        transcript_preview = " ".join(str(item.get("text", "")) for item in chat_signals.get("hot_messages", [])[:30])
        game_context = classify_game_context(
            payload.get("game_title") or preferences.get("game_title") or "",
            transcript_preview,
            chat_signals.get("top_terms", []),
        )

        evidence_preferences = dict(preferences)
        evidence_preferences["_game_context"] = game_context
        evidence_preferences["_media_signals"] = media_signals
        evidence_preferences["_chat_signals"] = chat_signals
        evidence_preferences["_vision_tracking"] = face_tracking
        evidence_preferences["_audio_quality"] = audio_profile if "audio_profile" in locals() else {}

        # Broad deterministic coverage first, augmented by non-verbal media/chat events.
        candidates = generate_intelligent_candidates(analysis["duration"], [])
        signal_candidates = (
            generate_signal_candidates(analysis["duration"], media_signals)
            + generate_chat_candidates(analysis["duration"], chat_signals)
        )
        seen_windows = {(round(float(item.get("start", 0)), 1), round(float(item.get("end", 0)), 1)) for item in candidates}
        for item in signal_candidates:
            key = (round(float(item.get("start", 0)), 1), round(float(item.get("end", 0)), 1))
            if key not in seen_windows and len(candidates) < 90:
                candidates.append(item)
                seen_windows.add(key)
        audio_profile = analyze_audio_quality(analysis["duration"], [], media_signals.get("silences", []))
        candidates = enrich_candidates_with_media_signals(candidates, media_signals)
        candidates = enrich_candidates_with_chat_signals(candidates, chat_signals)
        candidates = enrich_candidates_with_audio_quality(candidates, audio_profile)
        candidates = enrich_candidates_with_face_tracking(candidates, face_tracking)
        candidates = enrich_gameplay_candidates(candidates, game_context)
        agent_report = run_agent_suite(
            analysis["duration"],
            analysis=analysis,
            segments=[],
            candidates=candidates,
            memory=memory,
            preferences=preferences,
            media_signals=media_signals,
            chat_signals=chat_signals,
        )

        result, router, transcript_data = _route(
            path, analysis["duration"], candidates, memory, mode, evidence_preferences, agent_report
        )

        # Timestamped transcript creates a second, tighter semantic pass.
        if transcript_data.get("segments"):
            candidates = generate_intelligent_candidates(analysis["duration"], transcript_data["segments"])
            for item in (
                generate_signal_candidates(analysis["duration"], media_signals)
                + generate_chat_candidates(analysis["duration"], chat_signals)
            ):
                key = (round(float(item.get("start", 0)), 1), round(float(item.get("end", 0)), 1))
                existing = {(round(float(candidate.get("start", 0)), 1), round(float(candidate.get("end", 0)), 1)) for candidate in candidates}
                if key not in existing and len(candidates) < 90:
                    candidates.append(item)
            audio_profile = analyze_audio_quality(analysis["duration"], transcript_data["segments"], media_signals.get("silences", []))
            candidates = enrich_candidates_with_media_signals(candidates, media_signals)
            candidates = enrich_candidates_with_chat_signals(candidates, chat_signals)
            candidates = enrich_candidates_with_audio_quality(candidates, audio_profile)
            candidates = enrich_candidates_with_face_tracking(candidates, face_tracking)
            agent_report = run_agent_suite(
                analysis["duration"],
                analysis=analysis,
                segments=transcript_data["segments"],
                candidates=candidates,
                memory=memory,
                preferences=preferences,
                media_signals=media_signals,
                chat_signals=chat_signals,
            )

        result = enrich_ai_result(
            result,
            candidates,
            memory,
            transcript_data.get("segments", []),
        )

        director = build_montage_directive(
            result.get("clips", []),
            memory=memory,
            preferences=preferences,
            agent_report=agent_report,
        )
        sequence_ids = [item["clip_id"] for item in director.get("sequence", [])]
        result["montage"] = {
            "clip_ids": sequence_ids,
            "opening_clip_id": sequence_ids[0] if sequence_ids else None,
            "closing_clip_id": sequence_ids[-1] if sequence_ids else None,
        }
        result["montage_director"] = director
        result["agents"] = agent_report
        result["media_intelligence"] = media_signals
        result["chat_intelligence"] = chat_signals
        result["vision_tracking"] = face_tracking
        result["gameplay_intelligence"] = game_context
        result["audio_quality"] = audio_profile

        saved = {
            "mode": mode,
            "router": router,
            "ai": result,
            "analysis": analysis,
            "candidates": candidates,
            "transcript": transcript_data,
            "chat": chat_signals,
            "output_format": output_format,
            "preferences": preferences,
            "media_signals": media_signals,
            "vision_tracking": face_tracking,
            "gameplay_intelligence": game_context,
            "audio_quality": audio_profile,
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
            "message": "Analyse terminée: signaux média, chat, Creator DNA, sélection IA et direction de montage croisés.",
        })
    except Exception:
        current_app.logger.exception("AI analysis failed")
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET status=?,error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                ("failed", "AI analysis failed", job_id),
            )
            db.commit()
        return jsonify({"error": "L'analyse IA a échoué. Vérifie les moteurs IA et FFmpeg configurés."}), 500

@ai_bp.post("/api/ai/chat/<int:job_id>")
@login_required
def import_chat(job_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?",
            (job_id, session["user_id"]),
        ).fetchone()
    if not job:
        return jsonify({"error": "Projet introuvable."}), 404

    body = request.get_json(silent=True) or {}
    messages = normalize_chat_messages(body.get("messages") or [])
    if not messages:
        return jsonify({"error": "Aucun message de chat exploitable."}), 400

    signals = build_chat_signals(messages)
    payload = json.loads(job["payload_json"] or "{}")
    payload["chat_messages"] = messages

    with get_db(current_app.config["DATABASE_PATH"]) as db:
        db.execute(
            "UPDATE jobs SET payload_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), job_id),
        )
        if job["result_json"]:
            saved = json.loads(job["result_json"] or "{}")
            saved["chat"] = signals
            saved["chat_intelligence"] = signals
            db.execute(
                "UPDATE jobs SET result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(saved, ensure_ascii=False), job_id),
            )
        db.commit()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "chat": signals,
        "message": "Chat importé. Relance l'analyse pour que la sélection IA recalcule les scores avec ces signaux.",
    }), 200


def _render_ai_clips(job, result, requested_ids=None, social_preset=None, caption_style=None, montage=False, social_profile=None):
    payload = json.loads(job["payload_json"] or "{}")
    source = Path(payload.get("path", ""))
    if not source.is_file():
        raise FileNotFoundError("Vidéo source introuvable.")

    output_format = payload.get("output_format", result.get("output_format", "9:16"))
    profile = get_social_profile(social_profile) if social_profile else None
    if profile:
        output_format = profile["output_format"]
    transcript = result.get("transcript", {}).get("segments", [])
    available = {str(c["id"]): c for c in result.get("ai", {}).get("clips", [])}
    ids = [str(value) for value in (requested_ids or []) if str(value) in available]
    if not ids:
        ids = [str(c["id"]) for c in result.get("ai", {}).get("clips", [])[:5]]

    folder = Path(current_app.config["STORAGE_PATH"]) / "users" / str(session["user_id"]) / "ai"
    folder.mkdir(parents=True, exist_ok=True)
    rendered = []
    for index, clip_id in enumerate(ids[:5], start=1):
        candidate = dict(available[clip_id])
        if profile:
            candidate = clamp_candidate_to_profile(candidate, profile)
        output = folder / f"klypso-{job['id']}-clip-{index}" + (f"-{social_profile}" if social_profile else "") + ".mp4"
        preferences = result.get("preferences") or payload.get("preferences") or {}
        preset = social_preset or (profile["preset"] if profile else None) or preferences.get("social_preset", "dynamic")
        captions = caption_style or (profile["caption_style"] if profile else None) or preferences.get("caption_style") or (
            (result.get("ai", {}).get("montage_director") or {}).get("caption_style")
            if montage else None
        )
        director_sequence = result.get("ai", {}).get("montage_director", {}).get("sequence") or []
        directed_item = next((item for item in director_sequence if str(item.get("clip_id")) == str(clip_id)), {})
        fade = float(directed_item.get("fade_seconds", 0.0) or 0.0)
        render_candidate(
            str(source),
            str(output),
            candidate,
            output_format=output_format,
            transcript_segments=transcript,
            subtitles=bool(transcript),
            social_preset=preset,
            caption_style=captions,
            zoom=directed_item.get("zoom"),
            fade_seconds=fade,
            reframe_plan={
                "focus_x": candidate.get("focus_x", 0.5),
                "focus_y": candidate.get("focus_y", 0.5),
                "mode": candidate.get("reframe_mode", "smart_center"),
            },
            audio_cleanup="broadcast" if candidate.get("audio_quality_score", 72) >= 82 else "clean",
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
            "platform": social_profile or "custom",
            "output_format": output_format,
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
    social_preset = str(body.get("social_preset") or "").strip().lower() or None
    caption_style = str(body.get("caption_style") or "").strip().lower() or None
    try:
        result = json.loads(job["result_json"])
        rendered = _render_ai_clips(job, result, requested_ids, social_preset, caption_style)
        result["rendered_clips"] = rendered
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute("UPDATE jobs SET result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(result, ensure_ascii=False), job_id))
            db.commit()
        return jsonify({"ok": True, "clips": rendered})
    except Exception:
        current_app.logger.exception("AI clip render failed")
        return jsonify({"error": "Le rendu des clips a échoué. Vérifie que FFmpeg est disponible."}), 500

@ai_bp.post("/api/ai/render-social/<int:job_id>")
@login_required
def render_social_variants(job_id):
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
    platforms = [str(value).strip().lower() for value in (body.get("platforms") or ["youtube", "tiktok", "instagram", "x"])]
    platforms = [value for value in dict.fromkeys(platforms) if value in {"youtube", "tiktok", "instagram", "x"}]
    if not platforms:
        return jsonify({"error": "Aucun réseau social valide."}), 400
    requested_ids = body.get("clip_ids") if isinstance(body.get("clip_ids"), list) else None

    try:
        result = json.loads(job["result_json"])
        variants = []
        for platform in platforms:
            rendered = _render_ai_clips(
                job,
                result,
                requested_ids=requested_ids,
                social_profile=platform,
            )
            variants.extend(rendered)
        result["social_variants"] = variants
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(result, ensure_ascii=False), job_id),
            )
            db.commit()
        return jsonify({
            "ok": True,
            "platforms": platforms,
            "variants": variants,
            "count": len(variants),
        })
    except Exception:
        current_app.logger.exception("Social variant render failed")
        return jsonify({"error": "Les variantes sociales n'ont pas pu être rendues."}), 500


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
        director = result.get("ai", {}).get("montage_director") or {}
        sequence = director.get("sequence") or []
        montage_ids = [str(item.get("clip_id")) for item in sequence if item.get("clip_id")][:5]
        if not montage_ids:
            montage_ids = [str(clip["id"]) for clip in result.get("ai", {}).get("clips", [])[:5]]

        social_preset = director.get("social_preset") or (result.get("preferences") or {}).get("social_preset") or "story"
        caption_style = director.get("caption_style") or (result.get("preferences") or {}).get("caption_style") or "classic"

        rendered = _render_ai_clips(
            job, result, montage_ids,
            social_preset=social_preset,
            caption_style=caption_style,
            montage=True,
        )
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
        return jsonify({
            "ok": True,
            "montage": result["rendered_montage"],
            "director": {
                "story_arc": director.get("story_arc", []),
                "social_preset": social_preset,
                "caption_style": caption_style,
            },
        })
    except Exception:
        current_app.logger.exception("AI montage render failed")
        return jsonify({"error": "Le montage IA n'a pas pu être exporté."}), 500
