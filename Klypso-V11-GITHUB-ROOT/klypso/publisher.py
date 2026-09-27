"""KLYPSO Distribution Center: scheduling, native OAuth publishing, adapters and feedback loop.

YouTube and TikTok can use first-party OAuth connections when their developer
credentials are configured. Instagram and X remain adapter-based until their
platform app credentials are configured. End-user tokens are encrypted at rest.
"""
import calendar
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .auth import login_required
from .database import get_db
from .media.object_storage import materialize_media_path, send_stored_file
from .clips.intelligence import update_creator_memory
from .social_profiles import get_social_profile
from .clips.distribution_intelligence import build_distribution_strategy
from .social_connections import (
    connection_for,
    connection_status,
    disconnect_connection,
    ensure_fresh_token,
    tiktok_authorize_url,
    tiktok_exchange,
    tiktok_publish,
    tiktok_creator_info,
    tiktok_publish_status,
    tiktok_user_info,
    upsert_connection,
    youtube_authorize,
    youtube_callback as youtube_oauth_callback,
    youtube_channel,
    youtube_upload,
)


publisher_bp = Blueprint("publisher", __name__)

PLATFORMS = ("youtube", "tiktok", "instagram", "x")
FREQUENCIES = ("daily", "weekly", "monthly")

STATUS_LABELS = {
    "scheduled": "Programmé",
    "processing": "Publication…",
    "published": "Publié",
    "needs_connection": "Connexion requise",
    "failed": "Échec",
    "cancelled": "Annulé",
}


def _now():
    return datetime.now(timezone.utc)


def _parse_dt(value):
    if not value:
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value):
    parsed = value if isinstance(value, datetime) else _parse_dt(value)
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z") if parsed else None


def _platform_webhook(platform):
    key = f"KLYPSO_PUBLISH_{platform.upper()}_WEBHOOK_URL"
    return os.getenv(key, "").strip()


def platform_status(user_id=None):
    native = {}
    if user_id is not None:
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            native = connection_status(db, user_id)
    out = {}
    for platform in PLATFORMS:
        item = dict(native.get(platform) or {})
        webhook = bool(_platform_webhook(platform))
        if item.get("connected"):
            item.update({"adapter": "oauth", "connected": True})
        elif webhook:
            item.update({"adapter": "webhook", "connected": True, "account_name": None})
        else:
            item.update({"adapter": None, "connected": False, "account_name": None})
        item["native_supported"] = platform in {"youtube", "tiktok"}
        item["connect_url"] = (
            "/publisher/connect/youtube" if platform == "youtube"
            else "/publisher/connect/tiktok" if platform == "tiktok"
            else None
        )
        out[platform] = item
    return out


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="klypso-publisher-media")


def signed_media_token(user_id, media_id):
    return _serializer().dumps({"user_id": int(user_id), "media_id": int(media_id)})


def signed_media_url(user_id, media_id):
    token = signed_media_token(user_id, media_id)
    base = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    return f"{base}/publisher/media/{token}"


def _post_package(db, item):
    title = item["title"] or "Nouveau clip KLYPSO"
    caption = item["caption"] or title
    hashtags = item["hashtags"] or "#KLYPSO #gaming #shorts"
    payload = {
        "queue_id": item["id"],
        "platform": item["platform"],
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "scheduled_for": item["scheduled_for"],
        "media_url": signed_media_url(item["user_id"], item["media_id"]),
        "metadata": {
            **json.loads(item["metadata_json"] or "{}"),
            "social_profile": get_social_profile(item["platform"]),
        },
    }
    return payload


def _record_metrics(db, item, metrics):
    if not isinstance(metrics, dict):
        return
    def integer(name):
        try:
            return max(0, int(metrics.get(name, 0) or 0))
        except (TypeError, ValueError):
            return 0
    try:
        completion = float(metrics.get("completion_rate", 0) or 0)
    except (TypeError, ValueError):
        completion = 0.0
    completion = max(0.0, min(100.0, completion))
    db.execute(
        "INSERT INTO clip_metrics(user_id,job_id,candidate_id,queue_id,platform,views,likes,comments,shares,completion_rate) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            item["user_id"],
            item["job_id"],
            item["candidate_id"],
            item["id"],
            item["platform"],
            integer("views"),
            integer("likes"),
            integer("comments"),
            integer("shares"),
            completion,
        ),
    )
    try:
        update_creator_memory(db, item["user_id"], json.loads(
            db.execute("SELECT result_json FROM jobs WHERE id=?", (item["job_id"],)).fetchone()["result_json"] or "{}"
        ).get("ai", {}), "9:16")
    except Exception:
        # Metrics remain persisted even when memory refresh is unavailable.
        pass


def publish_queue_item(queue_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        item = db.execute(
            "SELECT * FROM publish_queue WHERE id=?",
            (queue_id,),
        ).fetchone()
        if not item:
            return {"ok": False, "status": "not_found", "error": "Publication introuvable."}
        if item["status"] == "published":
            return {"ok": True, "status": "published", "remote_url": item["remote_url"]}

        db.execute(
            "UPDATE publish_queue SET status='processing',attempts=attempts+1,last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (queue_id,),
        )
        db.commit()

        title = item["title"] or "Nouveau clip KLYPSO"
        caption = item["caption"] or title
        hashtags = item["hashtags"] or "#KLYPSO #gaming #shorts"
        try:
            metadata = json.loads(item["metadata_json"] or "{}")
        except (TypeError, ValueError):
            metadata = {}

        if item["platform"] in {"youtube", "tiktok"}:
            connection = connection_for(db, item["user_id"], item["platform"])
            if connection and connection.get("access_token"):
                try:
                    media = db.execute(
                        "SELECT stored_path FROM media_files WHERE id=? AND user_id=?",
                        (item["media_id"], item["user_id"]),
                    ).fetchone()
                    if not media:
                        raise FileNotFoundError("Média source introuvable.")
                    token = ensure_fresh_token(db, connection)
                    if item["platform"] == "youtube":
                        media_path = materialize_media_path(media["stored_path"])
                        if not Path(media_path).is_file():
                            raise FileNotFoundError("Média source introuvable.")
                        native_result = youtube_upload(
                            media_path,
                            token,
                            title,
                            f"{caption}\n\n{hashtags}",
                            privacy=str(metadata.get("youtube_privacy") or "private"),
                        )
                    else:
                        creator = tiktok_creator_info(token)
                        options = creator.get("privacy_level_options") or ["SELF_ONLY"]
                        requested_privacy = str(metadata.get("tiktok_privacy") or "")
                        privacy = requested_privacy if requested_privacy in options else options[0]
                        native_result = tiktok_publish(
                            signed_media_url(item["user_id"], item["media_id"]),
                            token,
                            f"{caption} {hashtags}".strip(),
                            is_aigc=bool(metadata.get("is_aigc")),
                            privacy_level=privacy,
                        )
                        native_result["privacy_level"] = privacy
                        native_result["creator_limits"] = creator
                    status = "published" if native_result.get("status") == "published" else "processing"
                    metadata["native_publish"] = native_result
                    db.execute(
                        "UPDATE publish_queue SET status=?,published_at=CASE WHEN ?='published' THEN CURRENT_TIMESTAMP ELSE published_at END,"
                        "remote_url=COALESCE(?,remote_url),last_error=NULL,metadata_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (
                            status,
                            status,
                            native_result.get("url"),
                            json.dumps(metadata, ensure_ascii=False),
                            queue_id,
                        ),
                    )
                    db.commit()
                    return {
                        "ok": True,
                        "status": status,
                        "remote_url": native_result.get("url"),
                        "platform_status": native_result.get("platform_status"),
                        "native": True,
                    }
                except Exception as exc:
                    db.execute(
                        "UPDATE publish_queue SET status='failed',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (str(exc)[:500], queue_id),
                    )
                    db.commit()
                    return {"ok": False, "status": "failed", "error": str(exc)[:500], "native": True}

        webhook = _platform_webhook(item["platform"])
        if not webhook:
            db.execute(
                "UPDATE publish_queue SET status='needs_connection',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                ("Aucun adaptateur de publication configuré pour cette plateforme.", queue_id),
            )
            db.commit()
            return {"ok": False, "status": "needs_connection", "error": "Aucun adaptateur connecté."}

        payload = _post_package(db, item)
        try:
            response = requests.post(
                webhook,
                json=payload,
                headers={"Content-Type": "application/json", "X-KLYPSO-Platform": item["platform"]},
                timeout=45,
            )
            response.raise_for_status()
            remote = None
            metrics = None
            try:
                body = response.json()
                remote = body.get("url") or body.get("remote_url")
                metrics = body.get("metrics")
            except ValueError:
                body = {}
            db.execute(
                "UPDATE publish_queue SET status='published',published_at=CURRENT_TIMESTAMP,remote_url=?,last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (remote, queue_id),
            )
            _record_metrics(db, item, metrics)
            db.commit()
            return {"ok": True, "status": "published", "remote_url": remote, "metrics": metrics or {}, "native": False}
        except Exception as exc:
            db.execute(
                "UPDATE publish_queue SET status='failed',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(exc)[:500], queue_id),
            )
            db.commit()
            return {"ok": False, "status": "failed", "error": str(exc)[:500]}



def sync_native_processing(user_id=None, limit=30):
    """Refresh asynchronous native posts, currently TikTok."""
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        query = "SELECT * FROM publish_queue WHERE status='processing' AND platform='tiktok' "
        params = []
        if user_id is not None:
            query += "AND user_id=? "
            params.append(user_id)
        query += "ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(50, int(limit))))
        rows = db.execute(query, tuple(params)).fetchall()
        updated = []
        for item in rows:
            try:
                metadata = json.loads(item["metadata_json"] or "{}")
            except (TypeError, ValueError):
                metadata = {}
            native = metadata.get("native_publish") or {}
            publish_id = native.get("publish_id")
            if not publish_id:
                continue
            connection = connection_for(db, item["user_id"], "tiktok")
            if not connection:
                continue
            try:
                token = ensure_fresh_token(db, connection)
                state, payload = tiktok_publish_status(publish_id, token)
                native["platform_status"] = state
                metadata["native_publish"] = native
                if state in {"PUBLISH_COMPLETE", "PUBLISHED"}:
                    db.execute(
                        "UPDATE publish_queue SET status='published',published_at=COALESCE(published_at,CURRENT_TIMESTAMP),metadata_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (json.dumps(metadata, ensure_ascii=False), item["id"]),
                    )
                    updated.append({"queue_id": item["id"], "status": "published"})
                elif state in {"FAILED", "ERROR", "CANCELED"}:
                    db.execute(
                        "UPDATE publish_queue SET status='failed',last_error=?,metadata_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (str(payload.get("fail_reason") or state)[:500], json.dumps(metadata, ensure_ascii=False), item["id"]),
                    )
                    updated.append({"queue_id": item["id"], "status": "failed"})
            except Exception as exc:
                current_app.logger.warning("Native post sync failed for queue %s: %s", item["id"], type(exc).__name__)
        db.commit()
    return {"processed": len(updated), "results": updated}


def run_due_posts(user_id=None, limit=12):
    now = _iso(_now())
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        if user_id is None:
            rows = db.execute(
                "SELECT * FROM publish_queue WHERE status='scheduled' AND scheduled_for<=? ORDER BY scheduled_for,id LIMIT ?",
                (now, max(1, min(50, int(limit)))),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM publish_queue WHERE user_id=? AND status='scheduled' AND scheduled_for<=? ORDER BY scheduled_for,id LIMIT ?",
                (user_id, now, max(1, min(50, int(limit)))),
            ).fetchall()
    results = [publish_queue_item(row["id"]) for row in rows]
    sync = sync_native_processing(user_id=user_id, limit=30)
    return {"processed": len(results) + sync["processed"], "results": results + sync["results"]}


def _add_months(value, months):
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _generate_dates(start, frequency, count):
    for index in range(count):
        if frequency == "daily":
            yield start + timedelta(days=index)
        elif frequency == "weekly":
            yield start + timedelta(weeks=index)
        else:
            yield _add_months(start, index)


def _social_copy(job, candidate_id, platform):
    title = "Clip KLYPSO"
    hook = "Nouveau moment fort."
    archetype = "moment"
    if job and job["result_json"]:
        try:
            saved = json.loads(job["result_json"])
            for clip in (saved.get("ai", {}).get("clips") or []):
                if str(clip.get("id")) == str(candidate_id):
                    title = str(clip.get("title") or title)[:90]
                    hook = str(clip.get("hook") or hook)[:180]
                    archetype = str(clip.get("archetype") or archetype)
                    break
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    profile = get_social_profile(platform)
    tags = ["#KLYPSO", f"#{archetype}", *profile["hashtags"]]
    tags = list(dict.fromkeys(tags))
    return {
        "title": title,
        "caption": hook,
        "hashtags": " ".join(tags),
        "render_profile": {
            "platform": platform,
            "ratio": profile["output_format"],
            "recommended_max_seconds": profile["recommended_max_seconds"],
            "preset": profile["preset"],
            "caption_style": profile["caption_style"],
        },
    }


def create_schedule_entry(user_id, media_id, platform, scheduled_for, job_id=None, candidate_id=None, title="", caption="", hashtags="", metadata=None):
    when = _parse_dt(scheduled_for)
    if not when:
        raise ValueError("Date de publication invalide.")
    if when < _now() - timedelta(minutes=2):
        raise ValueError("La date doit être dans le futur.")
    if platform not in PLATFORMS:
        raise ValueError("Plateforme non prise en charge.")
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        media = db.execute(
            "SELECT id FROM media_files WHERE id=? AND user_id=?",
            (media_id, user_id),
        ).fetchone()
        if not media:
            raise ValueError("Média introuvable.")
        job = db.execute(
            "SELECT result_json FROM jobs WHERE id=? AND user_id=?",
            (job_id, user_id),
        ).fetchone() if job_id else None
        package = _social_copy(job, candidate_id, platform)
        cur = db.execute(
            "INSERT INTO publish_queue(user_id,media_id,job_id,candidate_id,platform,scheduled_for,status,title,caption,hashtags,metadata_json) "
            "VALUES(?,?,?,?,?,?, 'scheduled',?,?,?,?)",
            (
                user_id, media_id, job_id, candidate_id, platform, _iso(when),
                title or package["title"], caption or package["caption"], hashtags or package["hashtags"],
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        queue_id = cur.lastrowid
        db.commit()
    return queue_id


def _user_queue(user_id, limit=60):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        rows = db.execute(
            "SELECT * FROM publish_queue WHERE user_id=? ORDER BY scheduled_for DESC,id DESC LIMIT ?",
            (user_id, max(1, min(120, int(limit)))),
        ).fetchall()
    return [dict(row) for row in rows]


@publisher_bp.get("/publisher")
@login_required
def publisher_page():
    user_id = session["user_id"]
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        media = db.execute(
            "SELECT id,original_name,created_at FROM media_files WHERE user_id=? AND mime_type LIKE 'video/%' ORDER BY id DESC LIMIT 30",
            (user_id,),
        ).fetchall()
        stats = {
            "scheduled": db.execute("SELECT COUNT(*) AS n FROM publish_queue WHERE user_id=? AND status='scheduled'", (user_id,)).fetchone()["n"],
            "published": db.execute("SELECT COUNT(*) AS n FROM publish_queue WHERE user_id=? AND status='published'", (user_id,)).fetchone()["n"],
            "failed": db.execute("SELECT COUNT(*) AS n FROM publish_queue WHERE user_id=? AND status='failed'", (user_id,)).fetchone()["n"],
        }
    return render_template(
        "publisher.html",
        queue=_user_queue(user_id),
        media=[dict(item) for item in media],
        platforms=platform_status(),
        stats=stats,
        status_labels=STATUS_LABELS,
    )

@publisher_bp.get("/api/publisher/analytics")
@login_required
def analytics_api():
    user_id = session["user_id"]
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        rows = db.execute(
            "SELECT platform,views,likes,comments,shares,completion_rate,candidate_id,job_id "
            "FROM clip_metrics WHERE user_id=? ORDER BY id DESC LIMIT 500",
            (user_id,),
        ).fetchall()
        published = db.execute(
            "SELECT COUNT(*) AS n FROM publish_queue WHERE user_id=? AND status='published'",
            (user_id,),
        ).fetchone()["n"]
    totals = {"views": 0, "likes": 0, "comments": 0, "shares": 0, "completion_rate": 0.0}
    by_platform = {}
    for row in rows:
        platform = row["platform"] or "unknown"
        bucket = by_platform.setdefault(platform, {"views": 0, "likes": 0, "comments": 0, "shares": 0, "posts": 0, "completion_rates": []})
        for key in ("views", "likes", "comments", "shares"):
            value = max(0, int(row[key] or 0))
            totals[key] += value
            bucket[key] += value
        completion = max(0.0, min(100.0, float(row["completion_rate"] or 0)))
        totals["completion_rate"] += completion
        bucket["completion_rates"].append(completion)
        bucket["posts"] += 1
    count = len(rows)
    if count:
        totals["completion_rate"] = round(totals["completion_rate"] / count, 1)
    for bucket in by_platform.values():
        rates = bucket.pop("completion_rates")
        bucket["completion_rate"] = round(sum(rates) / len(rates), 1) if rates else 0.0
        bucket["engagement_rate"] = round(
            (bucket["likes"] + bucket["comments"] + bucket["shares"]) / max(1, bucket["views"]) * 100,
            2,
        )
    return jsonify({
        "ok": True,
        "published_posts": int(published),
        "tracked_metrics": count,
        "totals": totals,
        "by_platform": by_platform,
    })


@publisher_bp.get("/publisher/connect/youtube")
@login_required
def connect_youtube():
    try:
        return youtube_authorize(url_for("publisher.youtube_callback", _external=True))
    except Exception as exc:
        return redirect(url_for("publisher.publisher_page", connection_error=str(exc)))


@publisher_bp.get("/publisher/connect/youtube/callback")
@login_required
def youtube_callback():
    try:
        token = youtube_oauth_callback()
        channel_id, channel_name = youtube_channel(token["access_token"])
        expires_at = _now() + timedelta(seconds=int(token.get("expires_in", 3600)))
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            upsert_connection(
                db,
                session["user_id"],
                "youtube",
                token.get("access_token", ""),
                token.get("refresh_token", ""),
                expires_at,
                channel_id,
                channel_name,
                token.get("scope", ""),
                {"token_type": token.get("token_type", "Bearer")},
            )
            db.commit()
        return redirect(url_for("publisher.publisher_page"))
    except Exception:
        current_app.logger.exception("YouTube publishing OAuth failed")
        return redirect(url_for("publisher.publisher_page", connection_error="Connexion YouTube impossible."))


@publisher_bp.get("/publisher/connect/tiktok")
@login_required
def connect_tiktok():
    import secrets
    state = secrets.token_urlsafe(32)
    session["tiktok_oauth_state"] = state
    try:
        return redirect(tiktok_authorize_url(url_for("publisher.tiktok_callback", _external=True), state))
    except Exception as exc:
        return redirect(url_for("publisher.publisher_page", connection_error=str(exc)))


@publisher_bp.get("/publisher/connect/tiktok/callback")
@login_required
def tiktok_callback():
    import hmac
    expected = session.pop("tiktok_oauth_state", "")
    state = request.args.get("state", "")
    if not expected or not state or not hmac.compare_digest(expected, state):
        return redirect(url_for("publisher.publisher_page", connection_error="État OAuth TikTok invalide."))
    if request.args.get("error") or not request.args.get("code"):
        return redirect(url_for("publisher.publisher_page", connection_error="Autorisation TikTok refusée."))
    try:
        token = tiktok_exchange(request.args["code"], url_for("publisher.tiktok_callback", _external=True))
        info = tiktok_user_info(token.get("access_token", ""))
        expires_at = _now() + timedelta(seconds=int(token.get("expires_in", 86400)))
        with get_db(current_app.config["DATABASE_PATH"]) as db:
            upsert_connection(
                db,
                session["user_id"],
                "tiktok",
                token.get("access_token", ""),
                token.get("refresh_token", ""),
                expires_at,
                info.get("open_id", ""),
                info.get("display_name", "TikTok"),
                token.get("scope", ""),
                {"avatar_url": info.get("avatar_url", "")},
            )
            db.commit()
        return redirect(url_for("publisher.publisher_page"))
    except Exception:
        current_app.logger.exception("TikTok publishing OAuth failed")
        return redirect(url_for("publisher.publisher_page", connection_error="Connexion TikTok impossible."))


@publisher_bp.post("/api/publisher/disconnect/<platform>")
@login_required
def disconnect_platform(platform):
    if platform not in PLATFORMS:
        return jsonify({"error": "Plateforme invalide."}), 400
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        disconnect_connection(db, session["user_id"], platform)
        db.commit()
    return jsonify({"ok": True, "platform": platform}), 200


@publisher_bp.get("/api/publisher/strategy")
@login_required
def strategy_api():
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        strategy = build_distribution_strategy(db, session["user_id"])
    return jsonify({"ok": True, "strategy": strategy})


@publisher_bp.get("/api/publisher/queue")
@login_required
def queue_api():
    return jsonify({"queue": _user_queue(session["user_id"]), "platforms": platform_status(session["user_id"])})


@publisher_bp.post("/api/publisher/schedule")
@login_required
def schedule_api():
    body = request.get_json(silent=True) or {}
    try:
        media_id = int(body.get("media_id"))
        platforms = body.get("platforms") or [body.get("platform")]
        platforms = [str(p).lower() for p in platforms if p]
        when = body.get("scheduled_for")
        job_id = int(body["job_id"]) if body.get("job_id") else None
        candidate_id = str(body.get("candidate_id") or "") or None
        ids = []
        for platform in platforms:
            ids.append(create_schedule_entry(
                session["user_id"], media_id, platform, when, job_id, candidate_id,
                body.get("title", ""), body.get("caption", ""), body.get("hashtags", ""),
                body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            ))
        return jsonify({"ok": True, "queue_ids": ids}), 201
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@publisher_bp.post("/api/publisher/cadence")
@login_required
def cadence_api():
    body = request.get_json(silent=True) or {}
    media_ids = []
    for value in body.get("media_ids") or []:
        try:
            media_ids.append(int(value))
        except (TypeError, ValueError):
            pass
    platforms = [str(p).lower() for p in body.get("platforms") or [] if str(p).lower() in PLATFORMS]
    frequency = str(body.get("frequency", "daily")).lower()
    if not media_ids or not platforms:
        return jsonify({"error": "Sélectionne au moins un média et un réseau."}), 400
    if frequency not in FREQUENCIES:
        return jsonify({"error": "Fréquence invalide."}), 400
    try:
        count = max(1, min(31, int(body.get("count", 7))))
    except (TypeError, ValueError):
        count = 7
    start = _parse_dt(body.get("start_at"))
    if not start:
        return jsonify({"error": "Date de départ invalide."}), 400
    if start < _now() - timedelta(minutes=2):
        return jsonify({"error": "La date de départ doit être future."}), 400
    created = []
    for index, when in enumerate(_generate_dates(start, frequency, count)):
        media_id = media_ids[index % len(media_ids)]
        for platform in platforms:
            try:
                created.append(create_schedule_entry(
                    session["user_id"], media_id, platform, when,
                    body.get("job_id"), body.get("candidate_id"),
                    metadata={"cadence": frequency, "series_index": index + 1},
                ))
            except ValueError:
                continue
    return jsonify({"ok": True, "created": len(created), "queue_ids": created}), 201


@publisher_bp.post("/api/publisher/publish/<int:queue_id>")
@login_required
def publish_now_api(queue_id):
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        owner = db.execute("SELECT user_id FROM publish_queue WHERE id=?", (queue_id,)).fetchone()
    if not owner or int(owner["user_id"]) != int(session["user_id"]):
        return jsonify({"error": "Publication introuvable."}), 404
    result = publish_queue_item(queue_id)
    return jsonify(result), 200 if result.get("ok") else 409


@publisher_bp.post("/api/publisher/run-due")
def run_due_api():
    secret = os.getenv("KLYPSO_CRON_SECRET", "").strip()
    header = request.headers.get("X-KLYPSO-CRON-KEY", "").strip()
    if secret and header == secret:
        return jsonify(run_due_posts(limit=50))
    if session.get("user_id"):
        return jsonify(run_due_posts(user_id=session["user_id"], limit=12))
    return jsonify({"error": "Non autorisé."}), 401


@publisher_bp.post("/api/publisher/metrics/<int:queue_id>")
@login_required
def metrics_api(queue_id):
    body = request.get_json(silent=True) or {}
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        item = db.execute(
            "SELECT * FROM publish_queue WHERE id=? AND user_id=?",
            (queue_id, session["user_id"]),
        ).fetchone()
        if not item:
            return jsonify({"error": "Publication introuvable."}), 404
        def integer(name):
            try:
                return max(0, int(body.get(name, 0) or 0))
            except (TypeError, ValueError):
                return 0
        try:
            completion = float(body.get("completion_rate", 0) or 0)
        except (TypeError, ValueError):
            completion = 0.0
        completion = max(0.0, min(100.0, completion))
        db.execute(
            "INSERT INTO clip_metrics(user_id,job_id,candidate_id,queue_id,platform,views,likes,comments,shares,completion_rate) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                session["user_id"], item["job_id"], item["candidate_id"], item["id"], item["platform"],
                integer("views"), integer("likes"), integer("comments"), integer("shares"), completion,
            ),
        )
        if item["job_id"]:
            try:
                saved = json.loads(db.execute("SELECT result_json FROM jobs WHERE id=?", (item["job_id"],)).fetchone()["result_json"] or "{}")
                update_creator_memory(db, session["user_id"], saved.get("ai", {}), "9:16")
            except Exception:
                pass
        db.commit()
    return jsonify({"ok": True, "message": "Performance ingérée dans le Creator DNA."}), 200


@publisher_bp.get("/publisher/media/<token>")
def publisher_media(token):
    try:
        payload = _serializer().loads(token, max_age=900)
    except SignatureExpired:
        return jsonify({"error": "Le lien de publication a expiré."}), 410
    except BadSignature:
        return jsonify({"error": "Lien de publication invalide."}), 403
    try:
        user_id = int(payload["user_id"])
        media_id = int(payload["media_id"])
    except (TypeError, ValueError, KeyError):
        return jsonify({"error": "Lien de publication invalide."}), 403
    with get_db(current_app.config["DATABASE_PATH"]) as db:
        row = db.execute(
            "SELECT stored_path,mime_type,original_name FROM media_files WHERE id=? AND user_id=?",
            (media_id, user_id),
        ).fetchone()
    if not row:
        return jsonify({"error": "Média introuvable."}), 404
    return send_stored_file(
        row["stored_path"],
        download_name=Path(row["original_name"]).name,
        mimetype=row["mime_type"],
    )
