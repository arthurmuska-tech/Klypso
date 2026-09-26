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
    return {"analysis": analysis, "candidates": candidates, "selected": selected, "note": "Les signaux IA avancés ne sont pas activés dans cette base minimale."}


def create_analysis_job(user_id, media_id, path, db_path):
    with get_db(db_path) as db:
        cur = db.execute("INSERT INTO jobs(user_id,job_type,status,payload_json) VALUES(?,?,?,?)", (user_id, "clip_analysis", "queued", json.dumps({"media_id": media_id, "path": path})))
        job_id = cur.lastrowid
        db.commit()
    return job_id
