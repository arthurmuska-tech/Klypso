"""Server-side OAuth connections and native publishing adapters.

Native integrations are optional and credential-gated. KLYPSO stores social
access/refresh tokens encrypted at rest using a key derived from the server
SECRET_KEY; end-user platform consent remains mandatory.
"""
import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import current_app
from authlib.integrations.flask_client import OAuth
from cryptography.fernet import Fernet, InvalidToken


oauth = OAuth()


def _secret():
    raw = str(current_app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY") or "klypso-development-secret").encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())


def _fernet():
    return Fernet(_secret())


def _enc(value):
    return _fernet().encrypt(str(value).encode("utf-8")).decode("utf-8") if value else ""


def _dec(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(str(value).encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def connection_for(db, user_id, platform):
    row = db.execute(
        "SELECT * FROM social_connections WHERE user_id=? AND platform=?",
        (user_id, platform),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["access_token"] = _dec(data.get("access_token_enc"))
    data["refresh_token"] = _dec(data.get("refresh_token_enc"))
    try:
        data["metadata"] = json.loads(data.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        data["metadata"] = {}
    return data


def upsert_connection(db, user_id, platform, access_token, refresh_token="", expires_at=None, account_id="", account_name="", scopes="", metadata=None):
    metadata = metadata if isinstance(metadata, dict) else {}
    db.execute(
        "INSERT INTO social_connections(user_id,platform,access_token_enc,refresh_token_enc,expires_at,account_id,account_name,scopes,metadata_json) "
        "VALUES(?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(user_id,platform) DO UPDATE SET "
        "access_token_enc=excluded.access_token_enc,refresh_token_enc=excluded.refresh_token_enc,"
        "expires_at=excluded.expires_at,account_id=excluded.account_id,account_name=excluded.account_name,"
        "scopes=excluded.scopes,metadata_json=excluded.metadata_json,updated_at=CURRENT_TIMESTAMP",
        (
            user_id, platform, _enc(access_token), _enc(refresh_token), _iso(expires_at) if expires_at else None,
            str(account_id or "")[:300], str(account_name or "")[:120], str(scopes or "")[:1000],
            json.dumps(metadata, ensure_ascii=False),
        ),
    )


def disconnect_connection(db, user_id, platform):
    db.execute("DELETE FROM social_connections WHERE user_id=? AND platform=?", (user_id, platform))


def connection_status(db, user_id):
    out = {}
    for platform in ("youtube", "tiktok", "instagram", "x"):
        row = connection_for(db, user_id, platform)
        out[platform] = {
            "connected": bool(row and row.get("access_token")),
            "adapter": "oauth" if row and row.get("access_token") else None,
            "account_name": row.get("account_name") if row else None,
        }
    return out


def _youtube_client(client_id, client_secret):
    client = oauth.create_client("klypso_youtube")
    if client is None:
        oauth.register(
            name="klypso_youtube",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile https://www.googleapis.com/auth/youtube.upload"},
        )
        client = oauth.create_client("klypso_youtube")
    return client


def youtube_authorize(redirect_uri):
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET sont requis pour YouTube.")
    return _youtube_client(client_id, client_secret).authorize_redirect(redirect_uri)


def youtube_callback():
    return _youtube_client(
        os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
    ).authorize_access_token()


def tiktok_authorize_url(redirect_uri, state):
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
    if not client_key:
        raise RuntimeError("TIKTOK_CLIENT_KEY est requis pour TikTok.")
    scopes = os.getenv("TIKTOK_SCOPES", "user.info.basic,video.publish").strip()
    return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
        "client_key": client_key,
        "response_type": "code",
        "scope": scopes,
        "redirect_uri": redirect_uri,
        "state": state,
    })


def tiktok_exchange(code, redirect_uri):
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
    response = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def tiktok_refresh(refresh_token):
    response = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
        data={
            "client_key": os.getenv("TIKTOK_CLIENT_KEY", "").strip(),
            "client_secret": os.getenv("TIKTOK_CLIENT_SECRET", "").strip(),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def tiktok_user_info(access_token):
    response = requests.get(
        "https://open.tiktokapis.com/v2/user/info/",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "open_id,display_name,avatar_url"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("user", {}) or {}


def ensure_fresh_token(db, connection):
    if not connection:
        raise RuntimeError("Connexion sociale introuvable.")
    token = connection.get("access_token") or ""
    expires_raw = connection.get("expires_at")
    try:
        expires = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00")) if expires_raw else None
    except ValueError:
        expires = None
    if token and (expires is None or expires > _now() + timedelta(minutes=3)):
        return token
    refresh = connection.get("refresh_token") or ""
    if not refresh:
        return token
    if connection.get("platform") == "tiktok":
        data = tiktok_refresh(refresh)
        token = data.get("access_token") or token
        new_refresh = data.get("refresh_token") or refresh
        expires_at = _now() + timedelta(seconds=int(data.get("expires_in", 86400)))
        upsert_connection(
            db,
            connection["user_id"],
            "tiktok",
            token,
            new_refresh,
            expires_at,
            connection.get("account_id"),
            connection.get("account_name"),
            data.get("scope", connection.get("scopes", "")),
            connection.get("metadata", {}),
        )
        return token
    raise RuntimeError("Le renouvellement automatique de cette connexion n'est pas encore implémenté.")


def youtube_channel(access_token):
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"part": "snippet", "mine": "true"},
        timeout=30,
    )
    response.raise_for_status()
    item = (response.json().get("items") or [{}])[0]
    return item.get("id", ""), (item.get("snippet") or {}).get("title", "YouTube")


def youtube_upload(video_path, access_token, title, description, privacy="private"):
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError("Vidéo de publication introuvable.")
    initiate = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Upload-Content-Length": str(path.stat().st_size),
            "X-Upload-Content-Type": "video/mp4",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "snippet": {
                "title": str(title or "Clip KLYPSO")[:100],
                "description": str(description or "")[:5000],
                "categoryId": "20",
            },
            "status": {
                "privacyStatus": privacy if privacy in {"private", "public", "unlisted"} else "private",
                "selfDeclaredMadeForKids": False,
            },
        },
        timeout=60,
    )
    initiate.raise_for_status()
    location = initiate.headers.get("Location")
    if not location:
        raise RuntimeError("YouTube n'a pas fourni d'URL d'upload.")
    with path.open("rb") as stream:
        upload = requests.put(
            location,
            headers={"Content-Length": str(path.stat().st_size), "Content-Type": "video/mp4"},
            data=stream,
            timeout=600,
        )
    upload.raise_for_status()
    body = upload.json()
    video_id = body.get("id")
    if not video_id:
        raise RuntimeError("YouTube n'a pas renvoyé d'identifiant vidéo.")
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "status": "published",
    }


def tiktok_publish_status(publish_id, access_token):
    response = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"},
        json={"publish_id": publish_id},
        timeout=45,
    )
    response.raise_for_status()
    data = response.json().get("data") or {}
    state = str(data.get("status") or "PROCESSING").upper()
    return state, data


def tiktok_publish(media_url, access_token, title, is_aigc=False):
    init = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"},
        json={
            "post_info": {
                "title": str(title or "Clip KLYPSO")[:2200],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "is_aigc": bool(is_aigc),
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": media_url,
            },
        },
        timeout=60,
    )
    init.raise_for_status()
    body = init.json()
    error = body.get("error") or {}
    publish_id = (body.get("data") or {}).get("publish_id")
    if error.get("code") not in (None, "ok"):
        raise RuntimeError(error.get("message") or "TikTok a refusé le démarrage de la publication.")
    if not publish_id:
        raise RuntimeError("TikTok n'a pas renvoyé de publish_id.")
    status = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"},
        json={"publish_id": publish_id},
        timeout=45,
    )
    current = {}
    if status.ok:
        current = status.json().get("data") or {}
    state = str(current.get("status") or "PROCESSING").upper()
    return {
        "publish_id": publish_id,
        "status": "published" if state in {"PUBLISH_COMPLETE", "PUBLISHED"} else "processing",
        "platform_status": state,
    }
