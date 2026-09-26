from pathlib import Path
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from .pipeline import create_analysis_job
from ..auth import login_required
from ..database import get_db
from ..media.storage import safe_media_name, is_allowed_mime
from ..utils.paths import user_storage
from ..utils.validation import validate_upload

clips_bp = Blueprint("clips", __name__)


@clips_bp.get("/clips")
@login_required
def clips():
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        jobs = db.execute("SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall()
    return render_template("clips.html", jobs=jobs)


@clips_bp.get("/clips/create")
@login_required
def create_clips():
    return render_template("upload.html")


def handle_upload():
    if request.method == "GET":
        return render_template("upload.html")
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))
    file = request.files.get("video")
    try:
        validate_upload(file, current_app.config["MAX_CONTENT_LENGTH"])
        if not is_allowed_mime(file.mimetype):
            raise ValueError("Type MIME vidéo non autorisé.")
        stored_name = safe_media_name(file.filename)
        folder = user_storage(current_app.config["STORAGE_PATH"], session["user_id"])
        destination = folder / stored_name
        file.save(destination)
        if destination.stat().st_size > current_app.config["MAX_CONTENT_LENGTH"]:
            destination.unlink(missing_ok=True)
            raise ValueError("Fichier trop volumineux.")
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (session["user_id"], file.filename, str(destination), file.mimetype, destination.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()
        job_id = create_analysis_job(session["user_id"], media_id, str(destination), current_app.config["DATABASE_PATH"])
        flash(f"Vidéo reçue. Analyse créée (job #{job_id}).", "success")
        return redirect(url_for("clips.clips"))
    except ValueError as exc:
        flash(str(exc), "error")
        return render_template("upload.html"), 400
    except Exception:
        current_app.logger.exception("Upload failed")
        flash("L'import n'a pas pu être traité.", "error")
        return render_template("upload.html"), 500


@clips_bp.post("/clips/feedback")
@login_required
def feedback():
    candidate_id = request.form.get("candidate_id", "").strip()
    decision = request.form.get("decision")
    if not candidate_id or decision not in {"keep", "reject"}:
        return {"error": "Données invalides"}, 400
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        job_id = request.form.get("job_id") or None
        if job_id:
            owned = db.execute("SELECT 1 FROM jobs WHERE id=? AND user_id=?", (job_id, session["user_id"])).fetchone()
            if not owned:
                return {"error": "Job invalide"}, 404
        db.execute(
            "INSERT INTO clip_feedback(user_id,job_id,candidate_id,decision) VALUES(?,?,?,?)",
            (session["user_id"], job_id, candidate_id, decision),
        )
        db.commit()
    return {"ok": True}, 200
