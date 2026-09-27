from pathlib import Path
import json
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from .pipeline import create_analysis_job
from ..auth import login_required
from ..credits import CreditError, consume_clip_credits, credit_cost_from_request, refund_clip_credits
from ..database import get_db
from ..media.storage import safe_media_name, is_allowed_mime
from ..promo import effective_plan_key
from ..plans import get_plan
from ..utils.paths import user_storage
from ..utils.validation import validate_upload

clips_bp = Blueprint("clips", __name__)


@clips_bp.get("/clips")
@login_required
def clips():
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        rows = db.execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC",
            (session["user_id"],),
        ).fetchall()
        jobs = []
        for row in rows:
            item = dict(row)
            payload = {}
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            project_id = payload.get("project_id")
            project = db.execute(
                "SELECT name FROM projects WHERE id=? AND user_id=?",
                (project_id, session["user_id"]),
            ).fetchone() if project_id else None
            item["project_name"] = project["name"] if project else f"Projet #{row['id']}"
            jobs.append(item)
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

    user_id = session["user_id"]
    file = request.files.get("video")
    mode = request.form.get("mode", "clip_only").strip()
    allowed_modes = {"ai_clips", "clip_only", "ai_montage", "montage_only"}
    if mode not in allowed_modes:
        mode = "clip_only"
    credit_cost = credit_cost_from_request(request)
    charged = False

    try:
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise ValueError("Compte introuvable.")

        plan_key = effective_plan_key(user)
        # A clip is metered by its requested characteristics before expensive
        # video processing starts.
        consume_clip_credits(
            user_id,
            plan_key,
            credit_cost,
            {
                "goal": request.form.get("goal", "clips"),
                "mode": mode,
                "format": request.form.get("output_format", "9:16"),
                "ai_style": request.form.get("ai_style", "auto"),
                "scene_priority": request.form.get("scene_priority", "balanced"),
                "pace": request.form.get("pace", "natural"),
                "social_preset": request.form.get("social_preset", "dynamic"),
                "caption_style": request.form.get("caption_style", "dynamic"),
            },
        )
        charged = True

        validate_upload(file, current_app.config["MAX_CONTENT_LENGTH"])
        if not is_allowed_mime(file.mimetype):
            raise ValueError("Type MIME vidéo non autorisé.")
        stored_name = safe_media_name(file.filename)
        folder = user_storage(current_app.config["STORAGE_PATH"], user_id)
        destination = folder / stored_name
        file.save(destination)
        if destination.stat().st_size > current_app.config["MAX_CONTENT_LENGTH"]:
            destination.unlink(missing_ok=True)
            raise ValueError("Fichier trop volumineux.")

        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (user_id, file.filename, str(destination), file.mimetype, destination.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()

        project_names = {
            "ai_clips": "Clips IA",
            "clip_only": "Clip seul",
            "ai_montage": "Montage IA",
            "montage_only": "Montage seul",
        }
        project_name = f"{project_names[mode]} · {Path(file.filename or 'vidéo').stem[:55]}"
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO projects(user_id,name,timeline_json) VALUES(?,?,?)",
                (user_id, project_name, json.dumps({
                    "mode": mode,
                    "output_format": request.form.get("output_format", "9:16"),
                    "preferences": {
                        "spoken": request.form.get("spoken") == "on",
                        "subtitles": request.form.get("subtitles") == "on",
                        "brand_kit": request.form.get("brand_kit") == "on",
                        "clean_audio": request.form.get("clean_audio") == "on",
                        "ai_style": request.form.get("ai_style", "auto"),
                        "scene_priority": request.form.get("scene_priority", "balanced"),
                        "pace": request.form.get("pace", "natural"),
                        "social_preset": request.form.get("social_preset", "dynamic"),
                        "caption_style": request.form.get("caption_style", "dynamic"),
                    },
                }, ensure_ascii=False)),
            )
            project_id = cur.lastrowid
            db.commit()

        job_id = create_analysis_job(
            user_id,
            media_id,
            str(destination),
            current_app.config["DATABASE_PATH"],
            metadata={
                "project_id": project_id,
                "mode": mode,
                "output_format": request.form.get("output_format", "9:16"),
                "goal": "clips" if mode in {"ai_clips", "clip_only"} else "studio",
                "preferences": {
                    "ai_style": request.form.get("ai_style", "auto"),
                    "scene_priority": request.form.get("scene_priority", "balanced"),
                    "pace": request.form.get("pace", "natural"),
                    "spoken": request.form.get("spoken") == "on",
                    "subtitles": request.form.get("subtitles") == "on",
                    "brand_kit": request.form.get("brand_kit") == "on",
                    "clean_audio": request.form.get("clean_audio") == "on",
                },
            },
        )
        target = url_for("clips.clips")
        if mode == "montage_only":
            target = url_for("studio.studio")
        flash(
            f"Projet « {project_name} » créé (#{job_id}). {credit_cost} crédits utilisés.",
            "success",
        )
        return redirect(target)

    except CreditError as exc:
        flash(str(exc), "error")
        return render_template("upload.html"), 402
    except ValueError as exc:
        if charged:
            refund_clip_credits(user_id, credit_cost, {"reason": "upload_validation_failed"})
        flash(str(exc), "error")
        return render_template("upload.html"), 400
    except Exception:
        if charged:
            refund_clip_credits(user_id, credit_cost, {"reason": "clip_creation_failed"})
        current_app.logger.exception("Upload failed")
        flash("L'import n'a pas pu être traité.", "error")
        return render_template("upload.html"), 500


@clips_bp.post("/api/clips/render-standard/<int:job_id>")
@login_required
def render_standard_clip(job_id):
    """Render one manually chosen clip without the semantic AI engine."""
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?",
            (job_id, session["user_id"]),
        ).fetchone()
    if not job:
        return {"error": "Projet introuvable."}, 404
    if job["job_type"] != "clip_analysis":
        return {"error": "Ce projet n'est pas un clip standard."}, 400

    payload = json.loads(job["payload_json"] or "{}")
    source = Path(payload.get("path", ""))
    if not source.is_file():
        return {"error": "Vidéo source introuvable."}, 404
    body = request.get_json(silent=True) or {}
    try:
        from .analyzer import analyze_media
        from .renderer import RATIOS, render_candidate

        start = max(0.0, float(body.get("start", 0)))
        end = float(body.get("end", start + 30))
        output_format = body.get("output_format", payload.get("output_format", "9:16"))
        if output_format not in RATIOS:
            output_format = "9:16"
        duration = float(analyze_media(str(source))["duration"])
        if duration <= 0:
            raise ValueError("Durée vidéo invalide.")
        start = min(start, max(0.0, duration - 1.0))
        end = max(start + 1.0, min(end, duration))
        if end - start < 1.0:
            raise ValueError("La durée du clip doit être positive.")

        folder = user_storage(current_app.config["STORAGE_PATH"], session["user_id"]) / "standard"
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / f"klypso-{job_id}-standard-{int(start * 10)}.mp4"
        render_candidate(
            str(source),
            str(output),
            {"start": start, "end": end, "duration": end - start},
            output_format=output_format,
            transcript_segments=None,
            subtitles=False,
            normalize_audio=True,
        )
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (session["user_id"], f"Clip standard #{job_id}.mp4", str(output), "video/mp4", output.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()
        return {
            "ok": True,
            "media_id": media_id,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "download_url": f"/studio/ai-download/{media_id}",
        }, 200
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except Exception:
        current_app.logger.exception("Standard clip render failed")
        return {"error": "Le rendu du clip standard a échoué."}, 500


@clips_bp.post("/clips/performance")
@login_required
def performance():
    body = request.get_json(silent=True) or {}
    candidate_id = str(body.get("candidate_id", "")).strip()
    decision_job_id = body.get("job_id")
    platform = str(body.get("platform", "unknown")).strip().lower()
    if platform not in {"youtube", "tiktok", "instagram", "x", "other", "unknown"}:
        platform = "other"
    if not candidate_id or not decision_job_id:
        return {"error": "Projet ou clip invalide."}, 400

    def non_negative_int(value):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    try:
        completion = float(body.get("completion_rate", 0) or 0)
    except (TypeError, ValueError):
        completion = 0.0
    completion = max(0.0, min(100.0, completion))

    with get_db(current_app.config["DATABASE_PATH"]) as db:
        job = db.execute(
            "SELECT result_json FROM jobs WHERE id=? AND user_id=?",
            (decision_job_id, session["user_id"]),
        ).fetchone()
        if not job:
            return {"error": "Projet invalide."}, 404
        saved = json.loads(job["result_json"] or "{}")
        known = {str(clip.get("id")) for clip in (saved.get("ai", {}).get("clips") or [])}
        if candidate_id not in known:
            return {"error": "Clip invalide pour ce projet."}, 400
        db.execute(
            "INSERT INTO clip_metrics(user_id,job_id,candidate_id,platform,views,likes,comments,shares,completion_rate) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                session["user_id"],
                decision_job_id,
                candidate_id,
                platform,
                non_negative_int(body.get("views")),
                non_negative_int(body.get("likes")),
                non_negative_int(body.get("comments")),
                non_negative_int(body.get("shares")),
                completion,
            ),
        )
        # Immediately refresh Creator DNA so the next analysis can use this result.
        try:
            from .intelligence import update_creator_memory
            saved_ai = saved.get("ai") or {}
            payload = db.execute(
                "SELECT payload_json FROM jobs WHERE id=? AND user_id=?",
                (decision_job_id, session["user_id"]),
            ).fetchone()
            output_format = "9:16"
            if payload:
                output_format = json.loads(payload["payload_json"] or "{}").get("output_format", "9:16")
            update_creator_memory(db, session["user_id"], saved_ai, output_format)
        except Exception:
            current_app.logger.exception("Unable to refresh Creator DNA from performance")
        db.commit()
    return {"ok": True, "message": "Performance enregistrée. Le Creator DNA est à jour."}, 200


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
