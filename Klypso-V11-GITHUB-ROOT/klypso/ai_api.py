import json
import os
import subprocess
import tempfile
from pathlib import Path

import requests
from flask import Blueprint, current_app, jsonify, session

from .auth import login_required
from .database import get_db
from .promo import effective_plan_key

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
                data={"model": "whisper-large-v3"},
                timeout=180,
            )
        response.raise_for_status()
        return response.json().get("text", "")
    finally:
        audio.unlink(missing_ok=True)


def _prompt(duration, candidates, transcript=""):
    return (
        "Tu es le moteur IA de KLYPSO pour Twitch, YouTube Shorts, TikTok et Reels.\n"
        "Sélectionne les moments les plus forts: réactions, punchlines, victoires, fails, surprises et débats.\n"
        "Évite silences, menus, écrans fixes et répétitions.\n\n"
        f"Durée: {duration:.2f}s\n"
        f"Candidats: {json.dumps(candidates[:40], ensure_ascii=False)}\n"
        f"Transcription: {transcript[:30000]}\n\n"
        "Réponds uniquement avec un JSON valide contenant clips (1 à 5 éléments) et summary. "
        "Chaque clip doit contenir id, start, end, score sur 100, title, hook et reason."
    )


def _text(provider, key, duration, candidates, transcript):
    base = "https://api.groq.com/openai/v1" if provider == "groq" else "https://openrouter.ai/api/v1"
    response = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "KLYPSO"},
        json={
            "model": _model(provider),
            "messages": [
                {"role": "system", "content": "Tu es un éditeur vidéo expert. Réponds uniquement en JSON valide."},
                {"role": "user", "content": _prompt(duration, candidates, transcript)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=180,
    )
    response.raise_for_status()
    return _json(response.json()["choices"][0]["message"]["content"])


def _gemini_video(video_path, duration, candidates, key):
    path = Path(video_path)
    if path.stat().st_size >= 95 * 1024 * 1024:
        raise RuntimeError("inline_video_limit")
    mime = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".m4v": "video/mp4",
    }.get(path.suffix.lower(), "video/mp4")
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{_model('gemini')}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [
                {"inline_data": {"mime_type": mime, "data": __import__("base64").b64encode(path.read_bytes()).decode("ascii")}},
                {"text": _prompt(duration, candidates)},
            ]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        },
        timeout=300,
    )
    response.raise_for_status()
    parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = next((part.get("text", "") for part in parts if part.get("text")), "")
    return _json(text)


def _route(video_path, duration, candidates):
    attempts = []
    for number, key in enumerate(_keys("GEMINI_API_KEY"), start=1):
        try:
            return _gemini_video(video_path, duration, candidates, key), {"provider": "gemini", "key_slot": number, "attempts": attempts}
        except Exception as exc:
            attempts.append({"provider": "gemini", "key_slot": number, "error": type(exc).__name__})

    transcript = ""
    groq_keys = _keys("GROQ_API_KEY")
    for number, key in enumerate(groq_keys, start=1):
        try:
            transcript = _transcribe_groq(video_path, key)
            if transcript:
                break
        except Exception as exc:
            attempts.append({"provider": "groq-transcription", "key_slot": number, "error": type(exc).__name__})

    if transcript:
        for number, key in enumerate(groq_keys, start=1):
            try:
                return _text("groq", key, duration, candidates, transcript), {"provider": "groq", "key_slot": number, "attempts": attempts}
            except Exception as exc:
                attempts.append({"provider": "groq", "key_slot": number, "error": type(exc).__name__})
        for number, key in enumerate(_keys("OPENROUTER_API_KEY"), start=1):
            try:
                return _text("openrouter", key, duration, candidates, transcript), {"provider": "openrouter", "key_slot": number, "attempts": attempts}
            except Exception as exc:
                attempts.append({"provider": "openrouter", "key_slot": number, "error": type(exc).__name__})

    raise RuntimeError("AI router exhausted")


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
    })


@ai_bp.post("/api/ai/analyze/<int:job_id>")
@login_required
def analyze_job(job_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, session["user_id"])).fetchone()
    if effective_plan_key(user) not in {"pro", "ultra"}:
        return jsonify({"error": "L'IA avancée est réservée aux plans Pro et Ultra."}), 403
    if not job:
        return jsonify({"error": "Projet introuvable."}), 404
    payload = json.loads(job["payload_json"] or "{}")
    path = payload.get("path")
    if not path or not Path(path).exists():
        return jsonify({"error": "Vidéo introuvable."}), 404
    try:
        from .clips.analyzer import analyze_media
        from .clips.candidates import generate_candidates
        analysis = analyze_media(path)
        candidates = generate_candidates(analysis["duration"])
        result, router = _route(path, analysis["duration"], candidates)
        saved = {"mode": "ai-router", "router": router, "ai": result, "analysis": analysis, "candidates": candidates}
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET status=?,result_json=?,error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                ("completed", json.dumps(saved, ensure_ascii=False), job_id),
            )
            db.commit()
        return jsonify({"ok": True, "result": saved})
    except Exception:
        current_app.logger.exception("AI router failed")
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            db.execute(
                "UPDATE jobs SET status=?,error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                ("failed", "AI router exhausted", job_id),
            )
            db.commit()
        return jsonify({"error": "Toutes les IA configurées ont échoué ou atteint leurs limites."}), 500
