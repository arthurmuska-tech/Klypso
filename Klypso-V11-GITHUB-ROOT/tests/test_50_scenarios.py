# KLYPSO V15.8 regression matrix
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from klypso import create_app
from klypso import auth as auth_module
from klypso.auth import _create_email_user, _login, _oauth_user
from klypso.database import get_db
from klypso.plans import get_plan, trial_active, trial_ends_at


@pytest.fixture()
def app(tmp_path, monkeypatch):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "EMAIL_OTP_DEV_LOG_CODE": False,
        "EMAIL_OTP_COOLDOWN_SECONDS": 0,
        "EMAIL_OTP_MAX_PER_HOUR": 100,
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "APPLE_CLIENT_ID": "",
        "APPLE_TEAM_ID": "",
        "APPLE_KEY_ID": "",
        "APPLE_PRIVATE_KEY": "",
    })
    app.config["TESTING"] = True
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


PUBLIC_SCENARIOS = [
    ("homepage", "/", 200),
    ("pricing", "/pricing", 200),
    ("login", "/login", 200),
    ("register", "/register", 200),
    ("health", "/healthz", 200),
    ("dashboard_requires_auth", "/dashboard", 302),
    ("clips_requires_auth", "/clips", 302),
    ("studio_requires_auth", "/studio", 302),
    ("account_requires_auth", "/account", 302),
    ("brand_requires_auth", "/brand-kit", 302),
]


@pytest.mark.parametrize("name,path,expected", PUBLIC_SCENARIOS, ids=[x[0] for x in PUBLIC_SCENARIOS])
def test_surface_scenarios(client, name, path, expected):
    response = client.get(path)
    assert response.status_code == expected
    if expected == 302:
        assert "/login" in response.headers["Location"]
    if name == "homepage":
        assert b"KLYPSO" in response.data
    if name == "health":
        assert response.get_json()["status"] == "ok"


AUTH_SCENARIOS = [
    "invalid_email",
    "missing_cgu",
    "missing_privacy",
    "missing_csrf",
    "wrong_csrf",
    "valid_register_request",
    "pending_register_state",
    "wrong_otp",
    "correct_otp",
    "verified_user",
]


@pytest.mark.parametrize("scenario", AUTH_SCENARIOS, ids=AUTH_SCENARIOS)
def test_auth_scenarios(client, app, scenario, monkeypatch):
    email = "creator@example.com"

    with client.session_transaction() as sess:
        sess["csrf_token"] = "csrf-ok"

    if scenario == "invalid_email":
        r = client.post("/register", data={"email": "not-an-email", "cgu": "on", "privacy": "on", "csrf_token": "csrf-ok"})
        assert r.status_code == 400
    elif scenario == "missing_cgu":
        r = client.post("/register", data={"email": email, "privacy": "on", "csrf_token": "csrf-ok"})
        assert r.status_code == 400
    elif scenario == "missing_privacy":
        r = client.post("/register", data={"email": email, "cgu": "on", "csrf_token": "csrf-ok"})
        assert r.status_code == 400
    elif scenario == "missing_csrf":
        r = client.post("/register", data={"email": email, "cgu": "on", "privacy": "on"})
        assert r.status_code == 400
    elif scenario == "wrong_csrf":
        r = client.post("/register", data={"email": email, "cgu": "on", "privacy": "on", "csrf_token": "wrong"})
        assert r.status_code == 400
    else:
        captured = {}
        monkeypatch.setattr(auth_module, "_send_code", lambda address, code: captured.update(email=address, code=code))
        r = client.post("/register", data={"email": email, "cgu": "on", "privacy": "on", "csrf_token": "csrf-ok"})
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/verify-email")
        if scenario == "valid_register_request":
            assert captured["email"] == email and len(captured["code"]) == 6
        elif scenario == "pending_register_state":
            with client.session_transaction() as sess:
                assert sess["pending_email"] == email
                assert sess["pending_purpose"] == "register"
        elif scenario == "wrong_otp":
            r = client.post("/verify-email", data={"code": "000000", "csrf_token": "csrf-ok"})
            assert r.status_code == 400
        elif scenario in {"correct_otp", "verified_user"}:
            r = client.post("/verify-email", data={"code": captured["code"], "csrf_token": "csrf-ok"})
            assert r.status_code == 302
            assert r.headers["Location"].endswith("/dashboard")
            with get_db(app.config["DATABASE_PATH"]) as db:
                user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            assert user is not None
            assert user["email_verified_at"]
            assert user["auth_provider"] == "email"
            if scenario == "verified_user":
                assert user["display_name"] == "creator"


OAUTH_SCENARIOS = [
    "google_create",
    "google_identity",
    "google_profile_name",
    "google_avatar",
    "google_idempotent",
    "same_email_cross_provider",
    "apple_identity",
    "account_displays_profile",
    "login_session_metadata",
    "google_callback",
]


@pytest.mark.parametrize("scenario", OAUTH_SCENARIOS, ids=OAUTH_SCENARIOS)
def test_oauth_and_account_scenarios(client, app, scenario, monkeypatch):
    profile = {"sub": "google-sub-001", "email": "google@example.com", "name": "Google Creator", "picture": "https://example.com/avatar.png"}

    if scenario == "google_create":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        assert user["email"] == profile["email"]
        assert user["auth_provider"] == "google"
    elif scenario == "google_identity":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
            with get_db(app.config["DATABASE_PATH"]) as db:
                row = db.execute("SELECT * FROM oauth_identities WHERE user_id=? AND provider='google'", (user["id"],)).fetchone()
        assert row is not None
    elif scenario == "google_profile_name":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        assert user["display_name"] == "Google Creator"
    elif scenario == "google_avatar":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        assert user["avatar_url"] == profile["picture"]
    elif scenario == "google_idempotent":
        with app.app_context():
            first = _oauth_user("google", profile["sub"], profile["email"], profile)
            second = _oauth_user("google", profile["sub"], profile["email"], profile)
        assert first["id"] == second["id"]
    elif scenario == "same_email_cross_provider":
        with app.app_context():
            first = _oauth_user("google", profile["sub"], profile["email"], profile)
            second = _oauth_user("apple", "apple-sub-001", profile["email"], {"name": "Apple Creator"})
            with get_db(app.config["DATABASE_PATH"]) as db:
                count = db.execute("SELECT COUNT(*) AS n FROM oauth_identities WHERE user_id=?", (first["id"],)).fetchone()["n"]
        assert second["id"] == first["id"]
        assert count == 2
    elif scenario == "apple_identity":
        with app.app_context():
            user = _oauth_user("apple", "apple-sub-123", "apple@example.com", {"name": "Apple Creator"})
            row = get_db(app.config["DATABASE_PATH"]).__enter__()
            row.close()
        assert user["auth_provider"] == "apple"
    elif scenario == "account_displays_profile":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
            sess["user_email"] = user["email"]
            sess["csrf_token"] = "csrf-ok"
        r = client.get("/account")
        assert r.status_code == 200
        assert b"Google Creator" in r.data
    elif scenario == "login_session_metadata":
        with app.app_context():
            user = _oauth_user("google", profile["sub"], profile["email"], profile)
        with app.test_request_context("/"):
            _login(user)
            from flask import session
            assert session["auth_provider"] == "google"
            assert session["user_name"] == "Google Creator"
    elif scenario == "google_callback":
        class FakeGoogleClient:
            def authorize_access_token(self):
                return {"userinfo": profile}

            def userinfo(self):
                return profile

        monkeypatch.setattr(auth_module.oauth, "create_client", lambda name: FakeGoogleClient())
        r = client.get("/oauth/google/callback")
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/dashboard")
        with client.session_transaction() as sess:
            assert sess["user_email"] == profile["email"]


DATA_SECURITY_SCENARIOS = [
    "authenticated_dashboard",
    "logout_requires_csrf",
    "logout_valid_csrf",
    "security_content_type",
    "security_frame",
    "security_referrer",
    "security_permissions",
    "security_csp",
    "security_hsts",
    "delete_cascade",
]


@pytest.mark.parametrize("scenario", DATA_SECURITY_SCENARIOS, ids=DATA_SECURITY_SCENARIOS)
def test_data_security_scenarios(client, app, scenario):
    if scenario == "security_hsts":
        prod = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_PATH": str(Path(app.config["DATABASE_PATH"]).with_name("prod.sqlite3")),
            "STORAGE_PATH": str(Path(app.config["STORAGE_PATH"]).with_name("prod-storage")),
            "FLASK_ENV": "production",
            "SESSION_COOKIE_SECURE": True,
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "APPLE_CLIENT_ID": "",
            "APPLE_TEAM_ID": "",
            "APPLE_KEY_ID": "",
            "APPLE_PRIVATE_KEY": "",
        })
        r = prod.test_client().get("/healthz")
        assert r.headers["Strict-Transport-Security"].startswith("max-age=")
        return

    with app.app_context():
        user = _create_email_user("security@example.com")
        user_id = user["id"]
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute("INSERT INTO projects(user_id,name) VALUES(?,?)", (user_id, "Project test"))
            db.execute("INSERT INTO jobs(user_id,job_type) VALUES(?,?)", (user_id, "clip"))
            db.execute("INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)", (user_id, "test.mp4", "storage/test.mp4", "video/mp4", 123))
            db.execute("INSERT INTO clip_feedback(user_id,job_id,candidate_id,decision) VALUES(?,?,?,?)", (user_id, 1, "c1", "keep"))
            db.execute("INSERT INTO credit_transactions(user_id,amount,balance_after,transaction_type) VALUES(?,?,?,?)", (user_id, 3, 3, "test"))
            db.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_email"] = "security@example.com"
        sess["csrf_token"] = "csrf-ok"

    if scenario == "authenticated_dashboard":
        r = client.get("/dashboard")
        assert r.status_code == 200
    elif scenario == "logout_requires_csrf":
        r = client.post("/logout")
        assert r.status_code == 400
    elif scenario == "logout_valid_csrf":
        r = client.post("/logout", data={"csrf_token": "csrf-ok"})
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/")
    elif scenario == "security_content_type":
        assert client.get("/").headers["X-Content-Type-Options"] == "nosniff"
    elif scenario == "security_frame":
        assert client.get("/").headers["X-Frame-Options"] == "DENY"
    elif scenario == "security_referrer":
        assert client.get("/").headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    elif scenario == "security_permissions":
        assert "camera=()" in client.get("/").headers["Permissions-Policy"]
    elif scenario == "security_csp":
        assert "form-action 'self'" in client.get("/").headers["Content-Security-Policy"]
    elif scenario == "delete_cascade":
        storage_user = Path(app.config["STORAGE_PATH"]) / "users" / str(user_id)
        storage_user.mkdir(parents=True, exist_ok=True)
        (storage_user / "test.mp4").write_bytes(b"test")
        r = client.post("/delete-account", data={"csrf_token": "csrf-ok"})
        assert r.status_code == 302
        with get_db(app.config["DATABASE_PATH"]) as db:
            assert db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None
            for table in ["oauth_identities", "user_consents", "projects", "jobs", "media_files", "clip_feedback", "credit_transactions"]:
                assert db.execute(f"SELECT 1 FROM {table} WHERE user_id=?", (user_id,)).fetchone() is None
        assert not storage_user.exists()


PLAN_SCENARIOS = [
    "free_limits",
    "pro_limits",
    "ultra_limits",
    "trial_missing",
    "trial_active",
    "trial_expiry",
    "promo_invalid_range",
    "health_version",
    "no_github_login",
    "theme_gallery",
]


@pytest.mark.parametrize("scenario", PLAN_SCENARIOS, ids=PLAN_SCENARIOS)
def test_plan_and_product_scenarios(client, app, scenario):
    if scenario == "free_limits":
        plan = get_plan("free")
        assert (plan.clips_per_month, plan.daily_credits, plan.max_projects, plan.max_upload_mb) == (15, 3, 2, 512)
    elif scenario == "pro_limits":
        plan = get_plan("pro")
        assert (plan.clips_per_month, plan.daily_credits, plan.max_projects, plan.max_upload_mb) == (100, 12, 20, 2048)
        assert plan.advanced_ai and plan.batch
    elif scenario == "ultra_limits":
        plan = get_plan("ultra")
        assert (plan.clips_per_month, plan.daily_credits, plan.max_projects, plan.max_upload_mb) == (500, 24, 100, 4096)
        assert plan.advanced_ai and plan.studio and plan.batch
    elif scenario == "trial_missing":
        assert not trial_active(None)
        assert trial_ends_at(None) is None
    elif scenario == "trial_active":
        started = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert trial_active(started)
    elif scenario == "trial_expiry":
        started = (datetime.now(timezone.utc) - timedelta(days=10, seconds=1)).isoformat()
        assert not trial_active(started)
        assert trial_ends_at(started) is not None
    elif scenario == "promo_invalid_range":
        from klypso.plans import promo_ends_at
        with pytest.raises(ValueError):
            promo_ends_at(datetime.now(timezone.utc).isoformat(), 0)
    elif scenario == "health_version":
        body = client.get("/healthz").get_json()
        assert body["version"] == "17.0.0"
    elif scenario == "no_github_login":
        text = Path(app.root_path).parent.joinpath("templates", "login.html").read_text(encoding="utf-8").lower()
        assert "github" not in text
    elif scenario == "theme_gallery":
        text = Path(app.root_path).parent.joinpath("templates", "account.html").read_text(encoding="utf-8")
        for palette in ["paper", "linen", "clay", "ocean", "forest", "plum", "graphite", "midnight"]:
            assert f'data-palette="{palette}"' in text


V16_SCENARIOS = [
    "profile_update_requires_csrf",
    "profile_update_success",
    "resend_without_pending",
    "verify_page_has_resend",
    "pricing_has_checkout",
    "command_center_exists",
    "clip_library_search_exists",
    "theme_gallery_has_12",
    "oauth_rejects_unverified",
    "oauth_profile_refresh",
]

@pytest.mark.parametrize("scenario", V16_SCENARIOS, ids=V16_SCENARIOS)
def test_v16_surface_scenarios(client, app, scenario):
    if scenario == "profile_update_requires_csrf":
        with app.app_context():
            user = _create_email_user("profile@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.post("/account/profile", data={"display_name": "New Name"})
        assert r.status_code == 400
    elif scenario == "profile_update_success":
        with app.app_context():
            user = _create_email_user("profile2@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.post("/account/profile", data={"display_name": "New Name", "csrf_token": "csrf-ok"})
        assert r.status_code == 302
        with app.app_context():
            with get_db(app.config["DATABASE_PATH"]) as db:
                row = db.execute("SELECT display_name FROM users WHERE id=?", (user["id"],)).fetchone()
        assert row["display_name"] == "New Name"
    elif scenario == "resend_without_pending":
        with client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-ok"
        r = client.post("/resend-code", data={"csrf_token": "csrf-ok"})
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    elif scenario == "verify_page_has_resend":
        r = client.get("/verify-email")
        assert r.status_code == 302
        with client.session_transaction() as sess:
            sess["pending_email"] = "x@example.com"; sess["pending_purpose"] = "login"; sess["csrf_token"] = "csrf-ok"
        r = client.get("/verify-email")
        assert r.status_code == 200 and "Renvoyer un code" in r.get_data(as_text=True)
    elif scenario == "pricing_has_checkout":
        r = client.get("/pricing")
        assert r.status_code == 200 and "Créer mon compte" in r.get_data(as_text=True)
        with app.app_context():
            user = _create_email_user("pricing@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.get("/pricing")
        assert b"Choisir Pro" in r.data and b"Choisir Ultra" in r.data
    elif scenario == "command_center_exists":
        with app.app_context():
            user = _create_email_user("cmd@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.get("/dashboard")
        assert r.status_code == 200 and "COMMAND CENTER" in r.get_data(as_text=True)
    elif scenario == "clip_library_search_exists":
        with app.app_context():
            user = _create_email_user("clips@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.get("/clips")
        assert r.status_code == 200 and "data-clips-search-toggle" in r.get_data(as_text=True)
    elif scenario == "theme_gallery_has_12":
        textv = Path(app.root_path).parent.joinpath("templates", "account.html").read_text(encoding="utf-8")
        for palette in ["paper","linen","clay","ocean","forest","plum","graphite","midnight","sage","sand","lavender","slate"]:
            assert f'data-palette="{palette}"' in textv
    elif scenario == "oauth_rejects_unverified":
        from klypso.auth import _oauth_user
        with app.app_context(), pytest.raises(ValueError):
            _oauth_user("google", "sub-unverified", "unverified@example.com", {"email_verified": False})
    elif scenario == "oauth_profile_refresh":
        from klypso.auth import _oauth_user
        with app.app_context():
            user = _oauth_user("google", "sub-refresh", "refresh@example.com", {"name": "Old Name", "picture": "https://example.com/old.png"})
            updated = _oauth_user("google", "sub-refresh", "refresh@example.com", {"name": "New Name", "picture": "https://example.com/new.png"})
        assert updated["id"] == user["id"]
        assert updated["display_name"] == "New Name"
        assert updated["avatar_url"] == "https://example.com/new.png"



# V17/Viral Engine coverage: creator memory, feedback, performance and render paths.
V17_SCENARIOS = [
    "creator_memory_empty",
    "intelligent_candidates_use_transcript",
    "intelligent_candidates_keep_nonverbal_coverage",
    "creator_memory_reads_winners",
    "creator_memory_reads_feedback",
    "profile_persists",
    "enrich_ignores_unknown_model_ids",
    "enrich_limits_clip_count",
    "enrich_prevents_near_duplicates",
    "enrich_keeps_score_breakdown",
    "project_jobs_support_four_modes",
    "ai_status_exposes_engine",
    "ai_plan_gate_for_free",
    "ai_render_requires_analysis",
    "ai_montage_requires_analysis",
    "upload_page_exposes_four_modes",
    "clips_page_exposes_viral_engine",
    "standard_engine_stays_available",
    "renderer_writes_timestamped_srt",
    "renderer_supports_social_ratios",
]

@pytest.mark.parametrize("scenario", V17_SCENARIOS, ids=V17_SCENARIOS)
def test_v17_ai_engine_scenarios(client, app, scenario):
    from klypso.clips.intelligence import (
        build_creator_memory,
        enrich_ai_result,
        generate_intelligent_candidates,
        update_creator_memory,
    )
    from klypso.clips.pipeline import analyze_video, create_analysis_job
    from klypso.clips.renderer import RATIOS, write_srt

    if scenario == "creator_memory_empty":
        with app.app_context():
            user = _create_email_user("empty-ai@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                memory = build_creator_memory(db, user["id"])
        assert memory["projects_analyzed"] == 0
        assert memory["preferred_archetypes"]

    elif scenario == "intelligent_candidates_use_transcript":
        segments = [
            {"start": 12, "end": 14, "text": "Attends quoi ?! C'est impossible."},
            {"start": 14.4, "end": 18, "text": "Regarde ça, regarde ça !"},
        ]
        candidates = generate_intelligent_candidates(90, segments)
        assert candidates
        assert any(c["source"] == "speech_cluster" for c in candidates)
        assert any("impossible" in c["context"].lower() for c in candidates)

    elif scenario == "intelligent_candidates_keep_nonverbal_coverage":
        candidates = generate_intelligent_candidates(180, [])
        assert candidates
        assert any(c["source"] == "coverage_grid" for c in candidates)

    elif scenario == "creator_memory_reads_winners":
        with app.app_context():
            user = _create_email_user("winners@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                db.execute(
                    "INSERT INTO jobs(user_id,job_type,status,payload_json,result_json) VALUES(?,?,?,?,?)",
                    (user["id"], "ai_clip_analysis", "completed", '{"output_format":"9:16"}',
                     '{"ai":{"clips":[{"start":1,"end":26,"title":"Gros clutch","hook":"IL A RETOURNÉ LA GAME","archetype":"clutch","opportunity_score":92}]}}')
                )
                db.commit()
                memory = build_creator_memory(db, user["id"])
        assert memory["projects_analyzed"] == 1
        assert memory["winning_examples"]

    elif scenario == "creator_memory_reads_feedback":
        with app.app_context():
            user = _create_email_user("feedback-memory@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                db.execute(
                    "INSERT INTO clip_feedback(user_id,candidate_id,decision) VALUES(?,?,?)",
                    (user["id"], "c1", "keep"),
                )
                db.execute(
                    "INSERT INTO clip_feedback(user_id,candidate_id,decision) VALUES(?,?,?)",
                    (user["id"], "c2", "reject"),
                )
                db.commit()
                memory = build_creator_memory(db, user["id"])
        assert memory["feedback_kept"] == 1
        assert memory["feedback_rejected"] == 1

    elif scenario == "profile_persists":
        with app.app_context():
            user = _create_email_user("profile-ai@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                update_creator_memory(
                    db,
                    user["id"],
                    {"clips":[{"title":"Moment fou","hook":"C'est lunaire","archetype":"surprise","duration":24,"opportunity_score":89}]},
                    "9:16",
                )
                db.commit()
                row = db.execute("SELECT profile_json FROM creator_ai_profiles WHERE user_id=?", (user["id"],)).fetchone()
        assert row is not None
        assert "Moment fou" in row["profile_json"]

    elif scenario == "enrich_ignores_unknown_model_ids":
        candidates = generate_intelligent_candidates(60, [{"start":10,"end":18,"text":"moment fort"}])
        result = enrich_ai_result({"clips":[{"id":"does-not-exist","start":10,"end":18,"title":"bad"}]}, candidates, {})
        assert result["clips"] == []

    elif scenario == "enrich_limits_clip_count":
        candidates = generate_intelligent_candidates(300, [])
        raws = []
        for candidate in candidates[:8]:
            raws.append({
                "id": candidate["id"], "start": candidate["start"], "end": candidate["end"],
                "title": candidate["id"], "hook": "hook", "reason": "reason", "archetype": "surprise",
                "hook_score": 90, "payoff_score": 90, "emotion_score": 90, "novelty_score": 80,
                "context_score": 90, "shareability_score": 85, "creator_fit_score": 80, "replay_score": 80,
            })
        result = enrich_ai_result({"clips": raws}, candidates, {})
        assert len(result["clips"]) <= 5

    elif scenario == "enrich_prevents_near_duplicates":
        candidates = [
            {"id":"a","start":10,"end":30,"duration":20,"base_score":95,"speech_density":4,"context":"A"},
            {"id":"b","start":12,"end":32,"duration":20,"base_score":94,"speech_density":4,"context":"B"},
            {"id":"c","start":60,"end":84,"duration":24,"base_score":92,"speech_density":3,"context":"C"},
        ]
        raws = [
            {"id":"a","start":10,"end":30,"title":"A","hook":"A","reason":"A","archetype":"reaction","hook_score":90,"payoff_score":90,"emotion_score":90,"novelty_score":80,"context_score":90,"shareability_score":90,"creator_fit_score":90,"replay_score":90},
            {"id":"b","start":12,"end":32,"title":"B","hook":"B","reason":"B","archetype":"punchline","hook_score":89,"payoff_score":89,"emotion_score":89,"novelty_score":80,"context_score":89,"shareability_score":89,"creator_fit_score":89,"replay_score":89},
            {"id":"c","start":60,"end":84,"title":"C","hook":"C","reason":"C","archetype":"surprise","hook_score":88,"payoff_score":88,"emotion_score":88,"novelty_score":80,"context_score":88,"shareability_score":88,"creator_fit_score":88,"replay_score":88},
        ]
        result = enrich_ai_result({"clips":raws}, candidates, {})
        assert len(result["clips"]) == 2
        assert all(abs(a["start"] - b["start"]) >= 9 for i, a in enumerate(result["clips"]) for b in result["clips"][i+1:])

    elif scenario == "enrich_keeps_score_breakdown":
        candidates = generate_intelligent_candidates(80, [{"start":20,"end":40,"text":"très gros moment"}])
        candidate = candidates[0]
        raw = {"id":candidate["id"],"start":candidate["start"],"end":candidate["end"],"title":"Test","hook":"Hook","reason":"Reason","archetype":"clutch","hook_score":99,"payoff_score":88,"emotion_score":77,"novelty_score":66,"context_score":55,"shareability_score":88,"creator_fit_score":80,"replay_score":91}
        result = enrich_ai_result({"clips":[raw]}, candidates, {})
        assert set(result["clips"][0]["scores"]) >= {"hook_score","payoff_score","emotion_score","creator_fit_score","base_score"}

    elif scenario == "project_jobs_support_four_modes":
        with app.app_context():
            user = _create_email_user("modes@example.com")
            for mode in ["ai_clips","clip_only","ai_montage","montage_only"]:
                job_id = create_analysis_job(user["id"], 1, "/tmp/video.mp4", app.config["DATABASE_PATH"], {"mode":mode,"output_format":"9:16"})
                with get_db(app.config["DATABASE_PATH"]) as db:
                    row = db.execute("SELECT job_type,payload_json FROM jobs WHERE id=?", (job_id,)).fetchone()
                assert row["job_type"]
                assert mode in row["payload_json"]

    elif scenario == "ai_status_exposes_engine":
        with app.app_context():
            user = _create_email_user("status-ai@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.get("/api/ai/status")
        assert r.status_code == 200
        assert r.get_json()["engine"] == "KLYPSO VIRAL ENGINE v1"

    elif scenario == "ai_plan_gate_for_free":
        with app.app_context():
            user = _create_email_user("free-ai@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                cur = db.execute("INSERT INTO jobs(user_id,job_type,status,payload_json) VALUES(?,?,?,?)", (user["id"],"ai_clip_analysis","queued",'{"path":"/tmp/nope.mp4","mode":"ai_clips"}'))
                db.commit()
                job_id = cur.lastrowid
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.post(f"/api/ai/analyze/{job_id}", headers={"X-CSRF-Token":"csrf-ok"})
        assert r.status_code == 403

    elif scenario == "ai_render_requires_analysis":
        with app.app_context():
            user = _create_email_user("render-ai@example.com")
            job_id = create_analysis_job(user["id"], 1, "/tmp/nope.mp4", app.config["DATABASE_PATH"], {"mode":"ai_clips"})
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.post(f"/api/ai/render-clips/{job_id}", headers={"X-CSRF-Token":"csrf-ok"})
        assert r.status_code in {403, 409}

    elif scenario == "ai_montage_requires_analysis":
        with app.app_context():
            user = _create_email_user("montage-ai@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                db.execute("UPDATE users SET plan='pro', subscription_status='active' WHERE id=?", (user["id"],))
                db.commit()
            job_id = create_analysis_job(user["id"], 1, "/tmp/nope.mp4", app.config["DATABASE_PATH"], {"mode":"ai_montage"})
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.post(f"/api/ai/render-montage/{job_id}", headers={"X-CSRF-Token":"csrf-ok"})
        assert r.status_code in {409, 500, 503}

    elif scenario == "upload_page_exposes_four_modes":
        with app.app_context():
            user = _create_email_user("upload-modes@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.get("/clips/create")
        assert r.status_code == 200
        for mode in ["ai_clips","clip_only","ai_montage","montage_only"]:
            assert f'data-creation-mode="{mode}"' in r.get_data(as_text=True)

    elif scenario == "clips_page_exposes_viral_engine":
        with app.app_context():
            user = _create_email_user("clips-engine@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.get("/clips")
        assert r.status_code == 200
        assert "KLYPSO VIRAL ENGINE" in r.get_data(as_text=True)

    elif scenario == "standard_engine_stays_available":
        path = Path(app.root_path).parent / "tests" / "fixtures_nonexistent.mp4"
        with pytest.raises(Exception):
            analyze_video(str(path))

    elif scenario == "renderer_writes_timestamped_srt":
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            assert write_srt([{"start":1.0,"end":3.2,"text":"Bonjour le chat"}], 0.0, 4.0, tmp_path)
            body = Path(tmp_path).read_text(encoding="utf-8")
            assert "00:00:01,000 --> 00:00:03,200" in body
            assert "Bonjour le chat" in body
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    elif scenario == "renderer_supports_social_ratios":
        assert RATIOS["9:16"] == (1080, 1920)
        assert RATIOS["1:1"] == (1080, 1080)
        assert RATIOS["4:5"] == (1080, 1350)
        assert RATIOS["16:9"] == (1920, 1080)


V17_EXTRA_SCENARIOS = [
    "preferences_saved_in_project",
    "standard_render_missing_source_is_safe",
    "feedback_bias_changes_score",
    "speech_boundary_optimizer_trims_air",
]

@pytest.mark.parametrize("scenario", V17_EXTRA_SCENARIOS, ids=V17_EXTRA_SCENARIOS)
def test_v17_extra_scenarios(client, app, scenario):
    from klypso.clips.intelligence import enrich_ai_result, tighten_clip_boundaries
    from klypso.clips.pipeline import create_analysis_job

    if scenario == "preferences_saved_in_project":
        with app.app_context():
            user = _create_email_user("prefs@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                db.execute(
                    "INSERT INTO projects(user_id,name,timeline_json) VALUES(?,?,?)",
                    (user["id"], "AI prefs", '{"mode":"ai_clips","preferences":{"ai_style":"punchy","scene_priority":"reaction","pace":"fast"}}'),
                )
                db.commit()
                row = db.execute("SELECT timeline_json FROM projects WHERE user_id=?", (user["id"],)).fetchone()
        assert "punchy" in row["timeline_json"]
        assert "reaction" in row["timeline_json"]

    elif scenario == "standard_render_missing_source_is_safe":
        with app.app_context():
            user = _create_email_user("standard-safe@example.com")
            job_id = create_analysis_job(user["id"], 1, "/tmp/not-there.mp4", app.config["DATABASE_PATH"], {"mode": "clip_only"})
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        r = client.post(f"/api/clips/render-standard/{job_id}", json={"start":0,"end":30}, headers={"X-CSRF-Token":"csrf-ok"})
        assert r.status_code == 404

    elif scenario == "feedback_bias_changes_score":
        candidates = [{"id":"a","start":10,"end":35,"duration":25,"base_score":80,"speech_density":3,"context":"moment"}]
        raw = {"clips":[{"id":"a","start":10,"end":35,"title":"Réaction","hook":"Wow","reason":"R","archetype":"reaction","hook_score":80,"payoff_score":80,"emotion_score":80,"novelty_score":70,"context_score":80,"shareability_score":80,"creator_fit_score":70,"replay_score":75}]}
        base = enrich_ai_result(raw, candidates, {"kept_archetypes":{},"rejected_archetypes":{}})
        boosted = enrich_ai_result(raw, candidates, {"kept_archetypes":{"reaction":2},"rejected_archetypes":{}})
        penalized = enrich_ai_result(raw, candidates, {"kept_archetypes":{},"rejected_archetypes":{"reaction":2}})
        assert boosted["clips"][0]["score"] > base["clips"][0]["score"]
        assert penalized["clips"][0]["score"] < base["clips"][0]["score"]

    elif scenario == "speech_boundary_optimizer_trims_air":
        clip = {"start":10,"end":45,"duration":35}
        segments = [{"start":18,"end":23,"text":"Voici le moment"},{"start":24,"end":29,"text":"regarde ça"}]
        trimmed = tighten_clip_boundaries(clip, segments)
        assert trimmed["start"] == 16.2
        assert trimmed["end"] == 32.0
        assert trimmed["duration"] < 35


V17_SEMANTIC_SCENARIOS = [
    "semantic_duplicate_gate",
]

@pytest.mark.parametrize("scenario", V17_SEMANTIC_SCENARIOS, ids=V17_SEMANTIC_SCENARIOS)
def test_v17_semantic_scenarios(client, app, scenario):
    from klypso.clips.intelligence import enrich_ai_result
    if scenario == "semantic_duplicate_gate":
        candidates = [
            {"id":"a","start":10,"end":30,"duration":20,"base_score":90,"speech_density":3,"context":"regarde ce clutch incroyable maintenant"},
            {"id":"b","start":80,"end":105,"duration":25,"base_score":89,"speech_density":3,"context":"regarde ce clutch incroyable maintenant encore"},
            {"id":"c","start":140,"end":165,"duration":25,"base_score":88,"speech_density":3,"context":"réaction totalement différente sur un nouveau sujet"},
        ]
        def raw(candidate, archetype):
            return {"id":candidate["id"],"start":candidate["start"],"end":candidate["end"],"title":candidate["id"],"hook":"hook","reason":"reason","archetype":archetype,
                    "hook_score":90,"payoff_score":90,"emotion_score":85,"novelty_score":80,"context_score":90,"shareability_score":85,"creator_fit_score":85,"replay_score":80}
        result = enrich_ai_result({"clips":[raw(candidates[0],"clutch"),raw(candidates[1],"clutch"),raw(candidates[2],"reaction")]}, candidates, {})
        assert len(result["clips"]) == 2
        assert {clip["id"] for clip in result["clips"]} == {"a","c"}

V17_MONTAGE_SCENARIOS = [
    "montage_respects_ai_order",
]

@pytest.mark.parametrize("scenario", V17_MONTAGE_SCENARIOS, ids=V17_MONTAGE_SCENARIOS)
def test_v17_montage_scenarios(client, app, scenario):
    from klypso.clips.intelligence import enrich_ai_result

    if scenario == "montage_respects_ai_order":
        candidates = [
            {"id":"a","start":10,"end":30,"duration":20,"base_score":95,"speech_density":4,"context":"setup"},
            {"id":"b","start":60,"end":82,"duration":22,"base_score":94,"speech_density":4,"context":"payoff"},
            {"id":"c","start":110,"end":132,"duration":22,"base_score":93,"speech_density":4,"context":"reaction"},
        ]
        def raw(candidate, archetype):
            return {"id":candidate["id"],"start":candidate["start"],"end":candidate["end"],"title":candidate["id"],"hook":"hook","reason":"reason","archetype":archetype,
                    "hook_score":95,"payoff_score":95,"emotion_score":90,"novelty_score":85,"context_score":92,"shareability_score":90,"creator_fit_score":90,"replay_score":88}
        result = enrich_ai_result(
            {"clips":[raw(candidates[0],"story"),raw(candidates[1],"clutch"),raw(candidates[2],"reaction")],
             "montage":{"clip_ids":["b","a","c"],"opening_clip_id":"b","closing_clip_id":"c"}},
            candidates,
            {},
        )
        assert result["montage"]["clip_ids"] == ["b","a","c"]

V17_PERFORMANCE_SCENARIOS = [
    "performance_memory_reads_real_results",
    "performance_endpoint_accepts_valid_clip",
    "performance_endpoint_rejects_unknown_clip",
]

@pytest.mark.parametrize("scenario", V17_PERFORMANCE_SCENARIOS, ids=V17_PERFORMANCE_SCENARIOS)
def test_v17_performance_scenarios(client, app, scenario):
    from klypso.clips.intelligence import build_creator_memory
    from klypso.clips.pipeline import create_analysis_job

    if scenario == "performance_memory_reads_real_results":
        with app.app_context():
            user = _create_email_user("metrics-memory@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                job = db.execute(
                    "INSERT INTO jobs(user_id,job_type,status,payload_json,result_json) VALUES(?,?,?,?,?)",
                    (user["id"], "ai_clip_analysis", "completed", '{"output_format":"9:16"}',
                     '{"ai":{"clips":[{"id":"c1","start":1,"end":30,"title":"Gros clutch","hook":"NO WAY","archetype":"clutch","opportunity_score":88}]}}'),
                )
                job_id = job.lastrowid
                db.execute(
                    "INSERT INTO clip_metrics(user_id,job_id,candidate_id,platform,views,likes,comments,shares,completion_rate) VALUES(?,?,?,?,?,?,?,?,?)",
                    (user["id"], job_id, "c1", "youtube", 100000, 9000, 600, 1100, 78.0),
                )
                db.commit()
                memory = build_creator_memory(db, user["id"])
        assert memory["performance_count"] == 1
        assert "clutch" in memory["performance_by_archetype"]
        assert memory["performance_winners"][0]["views"] == 100000

    elif scenario == "performance_endpoint_accepts_valid_clip":
        with app.app_context():
            user = _create_email_user("metrics-endpoint@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                job = db.execute(
                    "INSERT INTO jobs(user_id,job_type,status,payload_json,result_json) VALUES(?,?,?,?,?)",
                    (user["id"], "ai_clip_analysis", "completed", '{"mode":"ai_clips"}',
                     '{"ai":{"clips":[{"id":"c1","start":2,"end":25,"title":"Moment","hook":"Wow","archetype":"reaction"}]}}'),
                )
                job_id = job.lastrowid
                db.commit()
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        response = client.post(
            "/clips/performance",
            json={"job_id":job_id,"candidate_id":"c1","platform":"tiktok","views":12000,"likes":1400,"comments":80,"shares":120,"completion_rate":71.5},
            headers={"X-CSRF-Token":"csrf-ok"},
        )
        assert response.status_code == 200
        with app.app_context():
            with get_db(app.config["DATABASE_PATH"]) as db:
                row = db.execute("SELECT views,platform,completion_rate FROM clip_metrics WHERE job_id=?", (job_id,)).fetchone()
        assert row["views"] == 12000
        assert row["platform"] == "tiktok"
        assert row["completion_rate"] == 71.5

    elif scenario == "performance_endpoint_rejects_unknown_clip":
        with app.app_context():
            user = _create_email_user("metrics-invalid@example.com")
            with get_db(app.config["DATABASE_PATH"]) as db:
                job = db.execute(
                    "INSERT INTO jobs(user_id,job_type,status,payload_json,result_json) VALUES(?,?,?,?,?)",
                    (user["id"], "ai_clip_analysis", "completed", '{"mode":"ai_clips"}',
                     '{"ai":{"clips":[{"id":"c1","start":2,"end":25,"title":"Moment","hook":"Wow","archetype":"reaction"}]}}'),
                )
                job_id = job.lastrowid
                db.commit()
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]; sess["user_email"] = user["email"]; sess["csrf_token"] = "csrf-ok"
        response = client.post(
            "/clips/performance",
            json={"job_id":job_id,"candidate_id":"nope","views":100},
            headers={"X-CSRF-Token":"csrf-ok"},
        )
        assert response.status_code == 400
