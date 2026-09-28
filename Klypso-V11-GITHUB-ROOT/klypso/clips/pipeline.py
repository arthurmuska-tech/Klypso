import json
from .analyzer import analyze_media
from .candidates import generate_candidates
from .scorer import score_candidate
from .selector import select_candidates
from ..database import get_db


def analyze_video(path):
    analysis = analyze_media(path)
    candidates = generate_candidates(analysis["duration"])
    for candidate in candidates:
        candidate["score"] = score_candidate(candidate)
    selected = select_candidates(candidates)
    return {
        "analysis": analysis,
        "candidates": candidates,
        "selected": selected,
        "engine": "KLYPSO STANDARD ENGINE",
        "note": "Sélection locale déterministe. L'IA avancée ajoute transcription, contexte créateur et scoring sémantique.",
    }


def create_analysis_job(user_id, media_id, path, db_path, metadata=None):
    metadata = metadata or {}
    mode = metadata.get("mode", "clip_only")
    job_type = {
        "ai_clips": "ai_clip_analysis",
        "ai_montage": "ai_montage_analysis",
        "clip_only": "clip_analysis",
        "montage_only": "montage_project",
    }.get(mode, "clip_analysis")
    payload = {"media_id": media_id, "path": path, **metadata}
    credit_cost = max(0, int(metadata.get("credit_cost", 0) or 0))
    with get_db(db_path) as db:
        cur = db.execute(
            "INSERT INTO jobs(user_id,job_type,status,payload_json,credit_cost) VALUES(?,?,?,?,?)",
            (user_id, job_type, "queued", json.dumps(payload, ensure_ascii=False), credit_cost),
        )
        job_id = cur.lastrowid
        db.commit()
    return job_id
