from pathlib import Path
from flask import Blueprint, current_app, jsonify, render_template, request, send_file, session
from ..auth import login_required
from ..database import get_db
from ..media.ffprobe import probe
from ..media.ffmpeg import run
from ..media.storage import safe_media_name, is_allowed_mime
from ..utils.paths import user_storage
from ..utils.validation import validate_upload

studio_bp = Blueprint("studio", __name__)


@studio_bp.get("/studio")
@login_required
def studio():
    return render_template("studio.html")


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
