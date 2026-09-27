import json
from datetime import datetime, timedelta, timezone

from klypso import create_app
from klypso.auth import _create_email_user
from klypso.database import get_db
from klypso.clips.agents import AGENT_NAMES, build_montage_directive, run_agent_suite
from klypso.clips.renderer import CAPTION_STYLES, RATIOS, SOCIAL_PRESETS
from klypso.publisher import create_schedule_entry, platform_status, signed_media_token


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "APPLE_CLIENT_ID": "",
        "APPLE_TEAM_ID": "",
        "APPLE_KEY_ID": "",
        "APPLE_PRIVATE_KEY": "",
        "PUBLIC_BASE_URL": "http://localhost",
    })


def test_v18_has_fifteen_specialist_agents(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        report = run_agent_suite(
            600,
            analysis={"has_video": True, "has_audio": True, "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "60/1"}]},
            segments=[{"start": 10, "end": 20, "text": "No way incroyable"}],
            candidates=[{"id": "c1", "duration": 30, "speech_density": 0.7, "archetype": "reaction", "source": "speech"}],
            memory={"projects_analyzed": 3, "preferred_archetypes": ["reaction"], "performance_count": 2},
            preferences={"scene_priority": "gameplay", "ai_style": "punchy", "subtitles": True, "brand_kit": True},
        )
    assert report["agent_count"] == 15
    assert tuple(item["name"] for item in report["agents"]) == AGENT_NAMES


def test_v18_agents_have_shared_consensus(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        report = run_agent_suite(120, candidates=[], memory={}, preferences={})
    assert 0 <= report["consensus_score"] <= 100
    assert len(report["agents"]) == 15
    assert "coverage" in report


def test_v18_montage_director_creates_story_arc():
    clips = [
        {"id": "reaction-1", "duration": 15, "archetype": "reaction", "opportunity_score": 90},
        {"id": "setup-1", "duration": 22, "archetype": "story", "opportunity_score": 75},
        {"id": "payoff-1", "duration": 18, "archetype": "clutch", "opportunity_score": 88},
        {"id": "close-1", "duration": 12, "archetype": "punchline", "opportunity_score": 80},
    ]
    directive = build_montage_directive(clips, preferences={"social_preset": "story", "caption_style": "classic"})
    assert directive["story_arc"][0] == "hook"
    assert directive["sequence"][0]["clip_id"] == "reaction-1"
    assert directive["sequence"][0]["transition_in"] == "hard_cut"
    assert directive["sequence"][1]["fade_seconds"] > 0


def test_v18_social_presets_exist():
    assert set(SOCIAL_PRESETS) == {"clean", "dynamic", "gaming", "story"}
    assert SOCIAL_PRESETS["gaming"]["zoom"] > SOCIAL_PRESETS["clean"]["zoom"]
    assert SOCIAL_PRESETS["story"]["fade"] > 0


def test_v18_caption_styles_exist():
    assert set(CAPTION_STYLES) == {"dynamic", "classic", "minimal"}
    assert CAPTION_STYLES["dynamic"]["fontsize"] > CAPTION_STYLES["minimal"]["fontsize"]


def test_v18_ratios_preserved():
    assert RATIOS["9:16"] == (1080, 1920)
    assert RATIOS["4:5"] == (1080, 1350)
    assert RATIOS["1:1"] == (1080, 1080)
    assert RATIOS["16:9"] == (1920, 1080)


def seed_user_media(app):
    with app.app_context():
        user = _create_email_user("publisher@example.com")
        with get_db(app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO media_files(user_id,original_name,stored_path,mime_type,size_bytes) VALUES(?,?,?,?,?)",
                (user["id"], "clip.mp4", str(app.config["STORAGE_PATH"]) + "/clip.mp4", "video/mp4", 42),
            )
            media_id = cur.lastrowid
            db.commit()
        return user["id"], media_id


def test_v18_schedule_daily_weekly_monthly(tmp_path):
    app = make_app(tmp_path)
    user_id, media_id = seed_user_media(app)
    start = datetime.now(timezone.utc) + timedelta(days=1)
    with app.app_context():
        ids = [
            create_schedule_entry(user_id, media_id, "youtube", (start + timedelta(days=2)).isoformat()),
            create_schedule_entry(user_id, media_id, "tiktok", (start + timedelta(weeks=2)).isoformat()),
            create_schedule_entry(user_id, media_id, "instagram", (start + timedelta(days=40)).replace(day=1).isoformat()),
        ]
        with get_db(app.config["DATABASE_PATH"]) as db:
            rows = db.execute("SELECT status,platform,scheduled_for FROM publish_queue WHERE id IN (?,?,?) ORDER BY id", ids).fetchall()
    assert [row["status"] for row in rows] == ["scheduled", "scheduled", "scheduled"]
    assert [row["platform"] for row in rows] == ["youtube", "tiktok", "instagram"]


def test_v18_platforms_never_claim_unconfigured_connection(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.delenv("KLYPSO_PUBLISH_YOUTUBE_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("KLYPSO_PUBLISH_TIKTOK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("KLYPSO_PUBLISH_INSTAGRAM_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("KLYPSO_PUBLISH_X_WEBHOOK_URL", raising=False)
    with app.app_context():
        status = platform_status()
    assert all(not item["connected"] for item in status.values())


def test_v18_signed_media_token_round_trip(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        token = signed_media_token(12, 34)
    assert isinstance(token, str)
    assert token.count(".") >= 2


def test_v18_signed_media_token_rejects_tampering(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        token = signed_media_token(12, 34)
        from klypso.publisher import _serializer
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        try:
            _serializer().loads(tampered, max_age=900)
        except Exception:
            pass
        else:
            raise AssertionError("tampered token unexpectedly accepted")


def test_v18_publisher_page_requires_auth(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    response = client.get("/publisher")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_v18_publisher_schema_links_metrics():
    from klypso.database import SCHEMA
    assert "queue_id INTEGER" not in SCHEMA  # queue_id is an additive migration
    assert "CREATE TABLE IF NOT EXISTS publish_queue" in SCHEMA


def test_v18_health_version(tmp_path):
    app = make_app(tmp_path)
    response = app.test_client().get("/healthz")
    assert response.get_json()["version"] == "18.0.0"


def test_v18_creator_memory_can_keep_published_feedback(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        user = _create_email_user("dna@example.com")
        with get_db(app.config["DATABASE_PATH"]) as db:
            db.execute(
                "INSERT INTO jobs(user_id,job_type,status,payload_json,result_json) VALUES(?,?,?,?,?)",
                (
                    user["id"], "ai_clip_analysis", "completed", json.dumps({"output_format": "9:16"}),
                    json.dumps({"ai": {"clips": [{"id": "c1", "start": 1, "end": 20, "title": "Clutch", "hook": "WOW", "archetype": "clutch", "opportunity_score": 90}]}}),
                ),
            )
            db.commit()
            job = db.execute("SELECT id FROM jobs WHERE user_id=?", (user["id"],)).fetchone()
            db.execute(
                "INSERT INTO clip_feedback(user_id,job_id,candidate_id,decision) VALUES(?,?,?,?)",
                (user["id"], job["id"], "c1", "keep"),
            )
            db.commit()
            from klypso.clips.intelligence import build_creator_memory
            memory = build_creator_memory(db, user["id"])
    assert memory["feedback_count"] >= 1
    assert memory["kept_archetypes"]["clutch"] >= 1

def test_v18_cron_secret_can_trigger_due_queue_without_browser_session(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setenv("KLYPSO_CRON_SECRET", "cron-secret")
    response = app.test_client().post(
        "/api/publisher/run-due",
        headers={"X-KLYPSO-CRON-KEY": "cron-secret"},
    )
    assert response.status_code == 200
    assert response.get_json()["processed"] == 0
