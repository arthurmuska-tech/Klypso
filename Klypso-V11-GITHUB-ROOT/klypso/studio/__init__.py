from pathlib import Path
import json
import secrets
from flask import Blueprint, current_app, jsonify, render_template, request, send_file, session
from ..auth import login_required
from ..database import get_db
from ..media.ffprobe import probe
from ..media.ffmpeg import run
from ..media.storage import safe_media_name, is_allowed_mime
from ..clips.renderer import render_candidate, concat_videos
from ..utils.paths import user_storage
from ..utils.validation import validate_upload

studio_bp = Blueprint("studio", __name__)


@studio_bp.get("/studio")
@login_required
def studio():
    project = None
    project_id = request.args.get("project_id")
    job_id = request.args.get("job_id")
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        if project_id:
            project = db.execute(
                "SELECT * FROM projects WHERE id=? AND user_id=?",
                (project_id, session["user_id"]),
            ).fetchone()
        elif job_id:
            job = db.execute(
                "SELECT * FROM jobs WHERE id=? AND user_id=?",
                (job_id, session["user_id"]),
            ).fetchone()
            if job:
                payload = json.loads(job["payload_json"] or "{}")
                project_id = payload.get("project_id")
                if project_id:
                    project = db.execute(
                        "SELECT * FROM projects WHERE id=? AND user_id=?",
                        (project_id, session["user_id"]),
                    ).fetchone()
    project_payload = None
    if project:
        try:
            project_payload = json.loads(project["timeline_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            project_payload = {}
    return render_template(
        "studio.html",
        current_project=project,
        project_payload=project_payload or {"clips": [], "audio_tracks": [], "markers": []},
    )



@studio_bp.post("/api/studio/projects")
@login_required
def create_studio_project():
    body = request.get_json(silent=True) or {}
    name = " ".join(str(body.get("name") or "Projet Klypso").split())[:120] or "Projet Klypso"
    timeline = body.get("timeline") if isinstance(body.get("timeline"), dict) else {"clips": [], "audio_tracks": [], "markers": []}
    from .timeline import validate_timeline
    try:
        validate_timeline(timeline)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        cur = db.execute(
            "INSERT INTO projects(user_id,name,timeline_json) VALUES(?,?,?)",
            (session["user_id"], name, json.dumps(timeline, ensure_ascii=False)),
        )
        db.commit()
    return jsonify({"ok": True, "project_id": cur.lastrowid, "name": name, "timeline": timeline}), 201


@studio_bp.get("/api/studio/projects/<int:project_id>")
@login_required
def get_studio_project(project_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        row = db.execute(
            "SELECT id,name,timeline_json,updated_at FROM projects WHERE id=? AND user_id=?",
            (project_id, session["user_id"]),
        ).fetchone()
    if not row:
        return jsonify({"error": "Projet introuvable."}), 404
    try:
        timeline = json.loads(row["timeline_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        timeline = {"clips": [], "audio_tracks": [], "markers": []}
    return jsonify({"ok": True, "project_id": row["id"], "name": row["name"], "timeline": timeline, "updated_at": row["updated_at"]})


@studio_bp.post("/api/studio/projects/<int:project_id>/save")
@login_required
def save_studio_project(project_id):
    body = request.get_json(silent=True) or {}
    timeline = body.get("timeline")
    if not isinstance(timeline, dict):
        return jsonify({"error": "Timeline invalide."}), 400
    from .timeline import validate_timeline
    try:
        validate_timeline(timeline)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    name = " ".join(str(body.get("name") or "Projet Klypso").split())[:120] or "Projet Klypso"
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        owned = db.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, session["user_id"])).fetchone()
        if not owned:
            return jsonify({"error": "Projet introuvable."}), 404
        db.execute(
            "UPDATE projects SET name=?, timeline_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (name, json.dumps(timeline, ensure_ascii=False), project_id, session["user_id"]),
        )
        db.commit()
    return jsonify({"ok": True, "project_id": project_id, "name": name, "timeline": timeline})


@studio_bp.post("/api/studio/projects/<int:project_id>/edit")
@login_required
def edit_studio_project(project_id):
    body = request.get_json(silent=True) or {}
    operation = body.get("operation")
    if not isinstance(operation, dict):
        return jsonify({"error": "Opération Studio invalide."}), 400
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        row = db.execute("SELECT timeline_json FROM projects WHERE id=? AND user_id=?", (project_id, session["user_id"])).fetchone()
    if not row:
        return jsonify({"error": "Projet introuvable."}), 404
    try:
        timeline = json.loads(row["timeline_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        timeline = {"clips": [], "audio_tracks": [], "markers": []}
    try:
        from .editor import apply_edit
        updated = apply_edit(timeline, operation)
        from .timeline import validate_timeline
        validate_timeline(updated)
    except (ValueError, IndexError, KeyError) as exc:
        return jsonify({"error": str(exc)}), 400
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        db.execute(
            "UPDATE projects SET timeline_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (json.dumps(updated, ensure_ascii=False), project_id, session["user_id"]),
        )
        db.commit()
    return jsonify({"ok": True, "project_id": project_id, "timeline": updated})


@studio_bp.post("/api/studio/projects/<int:project_id>/render")
@login_required
def render_studio_project(project_id):
    body = request.get_json(silent=True) or {}
    timeline = body.get("timeline") if isinstance(body.get("timeline"), dict) else None
    if not timeline:
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            row = db.execute(
                "SELECT timeline_json FROM projects WHERE id=? AND user_id=?",
                (project_id, session["user_id"]),
            ).fetchone()
        if not row:
            return jsonify({"error": "Projet introuvable."}), 404
        try:
            timeline = json.loads(row["timeline_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            timeline = {"clips": [], "audio_tracks": [], "markers": []}

    from .timeline import validate_timeline
    try:
        validate_timeline(timeline)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    clips = timeline.get("clips") or []
    if not clips:
        return jsonify({"error": "La timeline est vide."}), 400

    ratio = str((timeline.get("settings") or {}).get("ratio") or "9:16")
    cleanup = str((timeline.get("settings") or {}).get("audio_cleanup") or "clean")
    preset = str((timeline.get("settings") or {}).get("social_preset") or "dynamic")
    output_format = ratio if ratio in {"9:16", "4:5", "1:1", "16:9"} else "9:16"

    folder = user_storage(current_app.config["STORAGE_PATH"], session["user_id"])
    temp_folder = folder / f"studio-render-{project_id}"
    temp_folder.mkdir(parents=True, exist_ok=True)
    rendered_paths = []
    try:
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            for index, clip in enumerate(clips):
                media_id = clip.get("media_id")
                if not media_id:
                    raise ValueError(f"Clip {index + 1} n'a pas de media_id.")
                media = db.execute(
                    "SELECT stored_path,original_name FROM media_files WHERE id=? AND user_id=?",
                    (int(media_id), session["user_id"]),
                ).fetchone()
                if not media or not Path(media["stored_path"]).is_file():
                    raise ValueError(f"Média du clip {index + 1} introuvable.")
                source_start = float(clip.get("source_start", clip.get("start", 0)) or 0)
                duration = float(clip.get("duration", 0) or 0)
                if source_start < 0 or duration <= 0:
                    raise ValueError(f"Durée/source invalide pour le clip {index + 1}.")
                output = temp_folder / f"segment-{index:03d}.mp4"
                render_candidate(
                    media["stored_path"],
                    output,
                    {"start": source_start, "end": source_start + duration},
                    output_format=output_format,
                    transcript_segments=[],
                    subtitles=False,
                    normalize_audio=True,
                    social_preset=preset,
                    reframe_plan=clip.get("reframe_plan") or {
                        "focus_x": clip.get("focus_x", 0.5),
                        "focus_y": clip.get("focus_y", 0.5),
                        "mode": clip.get("reframe_mode", "smart_center"),
                    },
                    audio_cleanup=cleanup,
                )
                rendered_paths.append(output)

        output = folder / f"klypso-studio-{project_id}-{secrets.token_hex(4)}.mp4"
        if len(rendered_paths) == 1:
            rendered_paths[0].replace(output)
        else:
            concat_videos(rendered_paths, output)

        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes,status) VALUES(?,?,?,?,?,'rendered')",
                (session["user_id"], f"Klypso Studio #{project_id}.mp4", str(output), "video/mp4", output.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()
        return jsonify({
            "ok": True,
            "project_id": project_id,
            "media_id": media_id,
            "download_url": f"/studio/ai-download/{media_id}",
            "clip_count": len(rendered_paths),
            "output_format": output_format,
        })
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        for path in rendered_paths:
            if path.exists():
                path.unlink(missing_ok=True)
        try:
            temp_folder.rmdir()
        except OSError:
            pass

@studio_bp.post("/studio/ai-edit")
@login_required
def ai_edit():
    """Create a real first-pass media output using locally available FFmpeg operations.

    This intentionally avoids claiming transcript/LLM/B-roll generation. The endpoint
    only applies operations it can execute on the deployed server.
    """
    video = request.files.get("video")
    source = None
    try:
        validate_upload(video, current_app.config["MAX_CONTENT_LENGTH"])
        if not is_allowed_mime(video.mimetype):
            raise ValueError("Type MIME vidéo non autorisé.")
        original_name = video.filename or "video"
        stored_name = safe_media_name(original_name)
        folder = user_storage(current_app.config["STORAGE_PATH"], session["user_id"])
        source = folder / stored_name
        video.save(source)
        if source.stat().st_size > current_app.config["MAX_CONTENT_LENGTH"]:
            source.unlink(missing_ok=True)
            raise ValueError("Fichier trop volumineux.")

        info = probe(str(source))
        duration = float(info.get("format", {}).get("duration") or 0)
        streams = info.get("streams", [])
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        has_video = any(s.get("codec_type") == "video" for s in streams)
        if duration <= 0 or not has_video:
            raise ValueError("La vidéo ne peut pas être analysée correctement.")

        remove_silence = request.form.get("remove_silence") == "1"
        normalize_audio = request.form.get("normalize_audio") == "1"
        prepare_captions = request.form.get("prepare_captions") == "1"

        operations = ["Analyse média"]
        filters = []
        if has_audio and remove_silence:
            filters.append("silenceremove=start_periods=1:start_duration=0.35:start_threshold=-45dB:stop_periods=-1:stop_duration=0.65:stop_threshold=-38dB")
            operations.append("réduction des silences")
        if has_audio and normalize_audio:
            filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")
            operations.append("normalisation audio")
        if prepare_captions:
            operations.append("préparation des sous-titres à réaliser avec un moteur de transcription")

        output_name = f"klypso-v10-ai-{Path(stored_name).stem}.mp4"
        output = folder / output_name
        args = ["-i", str(source), "-map", "0:v:0"]
        if has_audio:
            args += ["-map", "0:a:0?"]
        if filters and has_audio:
            args += ["-af", ",".join(filters)]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        if has_audio:
            args += ["-c:a", "aac"]
        else:
            args += ["-an"]
        args += ["-movflags", "+faststart", str(output)]
        run(args)

        with get_db(current_app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (session["user_id"], original_name, str(output), "video/mp4", output.stat().st_size),
            )
            media_id = cur.lastrowid
            db.commit()

        return jsonify({
            "ok": True,
            "media_id": media_id,
            "duration_label": f"{int(duration // 60):02d}:{int(duration % 60):02d}",
            "operations": operations,
            "download_url": f"/studio/ai-download/{media_id}",
            "has_audio": has_audio,
            "duration": float(duration),
        })
    except ValueError as exc:
        if source and source.exists() and source.stat().st_size > current_app.config["MAX_CONTENT_LENGTH"]:
            source.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Studio V10 AI edit failed")
        return jsonify({"error": "Le moteur de montage local a rencontré une erreur. Vérifie que FFmpeg/FFprobe sont disponibles."}), 500


@studio_bp.get("/studio/ai-download/<int:media_id>")
@login_required
def ai_download(media_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        row = db.execute(
            "SELECT original_name,stored_path,mime_type FROM media_files WHERE id=? AND user_id=?",
            (media_id, session["user_id"]),
        ).fetchone()
    if not row or not Path(row["stored_path"]).is_file():
        return jsonify({"error": "Fichier introuvable"}), 404
    return send_file(
        row["stored_path"],
        as_attachment=True,
        download_name=f"klypso-montage-{Path(row['original_name']).stem}.mp4",
        mimetype="video/mp4",
    )
