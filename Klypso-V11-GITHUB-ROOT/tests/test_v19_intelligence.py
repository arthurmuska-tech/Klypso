import json
from pathlib import Path

from klypso import create_app
from klypso.clips.agents import run_agent_suite
from klypso.clips.chat_intelligence import build_chat_signals, enrich_candidates_with_chat_signals
from klypso.clips.intelligence import enrich_ai_result
from klypso.clips.media_intelligence import enrich_candidates_with_media_signals
from klypso.clips.vision_tracking import enrich_candidates_with_face_tracking
from klypso.social_profiles import clamp_candidate_to_profile, get_social_profile
from klypso.clips.renderer import _video_filter, build_audio_filter
from klypso.clips.audio_intelligence import analyze_audio_quality, enrich_candidates_with_audio_quality
from klypso.studio.editor import apply_edit


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "SESSION_COOKIE_SECURE": False,
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "PUBLIC_BASE_URL": "http://localhost",
    })


def test_v19_media_signal_enrichment_changes_candidate_evidence():
    candidates = [{"id": "c1", "start": 10, "end": 40, "duration": 30, "base_score": 70}]
    signals = {
        "scene_changes": [12, 28],
        "audio_peaks": [{"time": 24, "energy": 1.0}],
        "silences": [{"start": 0, "end": 5, "duration": 5}],
        "event_windows": [{"start": 10, "end": 20, "source": "scene_change"}],
    }
    enriched = enrich_candidates_with_media_signals(candidates, signals)
    assert enriched[0]["visual_change"] > 0
    assert enriched[0]["audio_peak"] > 0
    assert enriched[0]["event_density"] > 0
    assert 0 <= enriched[0]["media_signal_score"] <= 1


def test_v19_chat_spike_is_real_signal():
    messages = [
        {"timestamp": 10, "author": "a", "text": "WOW"},
        {"timestamp": 10.5, "author": "b", "text": "NO WAY"},
        {"timestamp": 11, "author": "c", "text": "CLUTCH"},
        {"timestamp": 11.5, "author": "d", "text": "OMG"},
        {"timestamp": 12, "author": "e", "text": "WTF"},
        {"timestamp": 12.5, "author": "f", "text": "LET'S GO"},
    ]
    signals = build_chat_signals(messages)
    assert signals["message_count"] == 6
    enriched = enrich_candidates_with_chat_signals(
        [{"id": "c1", "start": 8, "end": 22, "duration": 14}],
        signals,
    )
    assert enriched[0]["chat_messages"] >= 1
    assert enriched[0]["chat_signal_score"] > 0


def test_v19_agents_report_connected_chat_and_media():
    report = run_agent_suite(
        120,
        analysis={"has_video": True, "has_audio": True, "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "60/1"}]},
        candidates=[{"id": "c1", "duration": 30, "speech_density": 1.0}],
        media_signals={"scene_change_count": 12, "audio_peak_count": 8},
        chat_signals={"message_count": 200, "spikes": [{"start": 20, "end": 25}]},
    )
    chat = next(item for item in report["agents"] if item["name"] == "chat_context")
    assert chat["signals"]["chat_signal"] == "connected"
    assert report["coverage"]["scene_changes"] == 12
    assert report["coverage"]["audio_peaks"] == 8
    assert report["coverage"]["chat_messages"] == 200


def test_v19_renderer_accepts_focal_reframe():
    filters, _ = _video_filter(
        (1080, 1920),
        social_preset="gaming",
        reframe_plan={"focus_x": 0.22, "focus_y": 0.58, "mode": "smart_gameplay"},
    )
    crop = next(item for item in filters if item.startswith("crop="))
    assert "0.2200" in crop
    assert "0.5800" in crop


def test_v19_enriched_clip_persists_reframe_and_signal_scores():
    candidates = [{"id": "c1", "start": 0, "end": 30, "duration": 30, "base_score": 80, "media_signal_score": 0.9, "chat_signal_score": 55}]
    result = {
        "clips": [{
            "id": "c1",
            "start": 3,
            "end": 26,
            "title": "Clutch",
            "hook": "WOW",
            "reason": "Payoff",
            "archetype": "clutch",
            "hook_score": 92,
            "payoff_score": 94,
            "emotion_score": 88,
            "novelty_score": 80,
            "context_score": 85,
            "shareability_score": 90,
            "creator_fit_score": 86,
            "replay_score": 89,
            "focus_x": 0.18,
            "focus_y": 0.61,
            "reframe_mode": "smart_gameplay",
        }]
    }
    enriched = enrich_ai_result(result, candidates, {})
    clip = enriched["clips"][0]
    assert clip["focus_x"] == 0.18
    assert clip["focus_y"] == 0.61
    assert clip["reframe_mode"] == "smart_gameplay"
    assert "media_signals" in clip
    assert "visual_change" in clip["media_signals"]


def test_v19_health_version(tmp_path):
    app = make_app(tmp_path)
    response = app.test_client().get("/healthz")
    assert response.get_json()["version"] == "22.0.0"


def test_v19_face_tracking_focus_is_applied_when_present():
    candidates = [{"id": "c1", "start": 10, "end": 30, "duration": 20}]
    tracking = {
        "engine": "opencv-face-v1",
        "available": True,
        "tracks": [{"time": 20, "focus_x": 0.2, "focus_y": 0.7, "area": 0.02}],
    }
    enriched = enrich_candidates_with_face_tracking(candidates, tracking)
    assert enriched[0]["focus_x"] == 0.2
    assert enriched[0]["focus_y"] == 0.7
    assert enriched[0]["reframe_mode"] == "smart_face"


def test_v19_social_profiles_are_clamped():
    candidate = {"id": "c1", "start": 0, "end": 180, "duration": 180}
    profile = get_social_profile("youtube")
    clipped = clamp_candidate_to_profile(candidate, profile)
    assert clipped["duration"] <= profile["recommended_max_seconds"]
    assert profile["output_format"] == "9:16"


def test_v19_local_fallback_is_keyless(monkeypatch):
    from klypso.ai_api import _local_signal_result
    result = _local_signal_result([
        {
            "id": "signal-1",
            "start": 5,
            "end": 25,
            "duration": 20,
            "base_score": 80,
            "media_signal_score": 0.9,
            "chat_signal_score": 70,
            "speech_density": 2.0,
            "source": "chat_spike",
            "context": "le chat explose",
            "focus_x": 0.3,
            "focus_y": 0.6,
            "reframe_mode": "smart_face",
        }
    ])
    assert result["engine"] == "KLYPSO LOCAL VIRAL ENGINE v1"
    assert result["clips"][0]["id"] == "signal-1"


def test_v19_gameplay_context_and_candidate_signal():
    from klypso.clips.gameplay_intelligence import classify_game_context, enrich_gameplay_candidates
    context = classify_game_context("Valorant", "gros clutch headshot round")
    assert context["genre"] == "fps"
    enriched = enrich_gameplay_candidates(
        [{"id":"c1","start":10,"end":30,"source":"chat_spike","context":"clutch headshot"}],
        context,
    )
    assert enriched[0]["gameplay_signal"] > 0
    assert enriched[0]["scene_type"] == "gameplay_event"


def test_v19_renderer_motion_graphics_progress_bar():
    from klypso.clips.renderer import _video_filter
    filters, _ = _video_filter((1080, 1920), progress_duration=30)
    assert any(item.startswith("drawbox=") for item in filters)


def test_v20_studio_project_lifecycle(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        from klypso.database import get_db
        with get_db(app.config["DATABASE_PATH"]) as db:
            cur = db.execute(
                "INSERT INTO users(email,password_hash,display_name) VALUES(?,?,?)",
                ("studio-v20@example.com", "test-hash", "Studio V20"),
            )
            user_id = cur.lastrowid
            db.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_email"] = "studio-v20@example.com"
        sess["csrf_token"] = "csrf-v20"

    timeline = {
        "clips": [{"start": 0, "duration": 12, "name": "Hook"}],
        "audio_tracks": [{"name": "Main"}],
        "markers": [{"time": 5, "label": "Payoff"}],
        "settings": {"ratio": "9:16"},
    }
    created = client.post(
        "/api/studio/projects",
        json={"name": "V20 Studio", "timeline": timeline},
        headers={"X-CSRF-Token": "csrf-v20"},
    )
    assert created.status_code == 201
    project_id = created.get_json()["project_id"]

    loaded = client.get(f"/api/studio/projects/{project_id}")
    assert loaded.status_code == 200
    assert loaded.get_json()["timeline"]["settings"]["ratio"] == "9:16"

    timeline["settings"]["ratio"] = "16:9"
    saved = client.post(
        f"/api/studio/projects/{project_id}/save",
        json={"name": "V20 Studio Updated", "timeline": timeline},
        headers={"X-CSRF-Token": "csrf-v20"},
    )
    assert saved.status_code == 200
    assert saved.get_json()["name"] == "V20 Studio Updated"

    edited = client.post(
        f"/api/studio/projects/{project_id}/edit",
        json={"operation": {"type": "split", "clip_index": 0, "at": 5}},
        headers={"X-CSRF-Token": "csrf-v20"},
    )
    assert edited.status_code == 200
    assert len(edited.get_json()["timeline"]["clips"]) == 2


def test_v20_studio_rejects_foreign_project(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        from klypso.database import get_db
        with get_db(app.config["DATABASE_PATH"]) as db:
            cur = db.execute("INSERT INTO users(email,password_hash,display_name) VALUES(?,?,?)", ("owner-v20@example.com", "test-hash", "Owner"))
            owner_id = cur.lastrowid
            cur = db.execute("INSERT INTO users(email,password_hash,display_name) VALUES(?,?,?)", ("other-v20@example.com", "test-hash", "Other"))
            other_id = cur.lastrowid
            cur = db.execute(
                "INSERT INTO projects(user_id,name,timeline_json) VALUES(?,?,?)",
                (other_id, "Private", json.dumps({"clips":[],"audio_tracks":[],"markers":[]}))
            )
            project_id = cur.lastrowid
            db.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = owner_id
        sess["user_email"] = "owner-v20@example.com"
        sess["csrf_token"] = "csrf-v20"
    assert client.get(f"/api/studio/projects/{project_id}").status_code == 404


def test_v20_audio_quality_detects_fillers_and_silence():
    profile = analyze_audio_quality(
        40,
        transcript_segments=[
            {"start": 5, "end": 12, "text": "Euh je pense que c'est incroyable"},
            {"start": 16, "end": 23, "text": "C'est vraiment le moment"},
        ],
        silences=[{"start": 0, "end": 4}, {"start": 24, "end": 28}],
    )
    assert profile["filler_count"] >= 1
    assert profile["silence_ratio"] > 0
    assert 0 <= profile["score"] <= 100


def test_v20_audio_quality_enriches_candidates():
    enriched = enrich_candidates_with_audio_quality(
        [{"id": "c1", "start": 0, "end": 30, "duration": 30, "base_score": 80, "audio_peak": 0.8}],
        {"score": 82, "silence_ratio": 0.1, "filler_rate": 0.01, "filler_count": 2},
    )
    assert enriched[0]["audio_quality_score"] > 0
    assert enriched[0]["filler_count"] == 2


def test_v20_renderer_broadcast_audio_mode():
    audio_filter = build_audio_filter(True, "broadcast")
    assert "highpass=f=70" in audio_filter
    assert "acompressor" in audio_filter
    assert "loudnorm" in audio_filter


def test_v20_studio_edit_operations_are_non_destructive():
    timeline = {
        "clips": [
            {"start": 0, "duration": 12, "name": "Hook"},
            {"start": 12, "duration": 10, "name": "Payoff"},
        ],
        "audio_tracks": [],
        "markers": [],
        "settings": {"ratio": "9:16"},
    }
    trimmed = apply_edit(timeline, {"type": "trim", "clip_index": 0, "in_point": 2, "out_point": 8})
    assert trimmed["clips"][0]["start"] == 2
    assert trimmed["clips"][0]["duration"] == 6

    moved = apply_edit(trimmed, {"type": "move", "clip_index": 0, "new_start": 4})
    assert moved["clips"][0]["start"] == 4

    duplicated = apply_edit(moved, {"type": "duplicate", "clip_index": 0})
    assert len(duplicated["clips"]) == 3

    marked = apply_edit(duplicated, {"type": "add_marker", "time": 7.5, "label": "Payoff"})
    assert marked["markers"][0]["label"] == "Payoff"

    configured = apply_edit(marked, {"type": "set_setting", "key": "audio_cleanup", "value": "broadcast"})
    assert configured["settings"]["audio_cleanup"] == "broadcast"


def test_v20_opportunity_score_is_normalized():
    from klypso.clips.intelligence import enrich_ai_result
    candidate = {
        "id": "c1",
        "start": 0,
        "end": 20,
        "duration": 20,
        "base_score": 100,
        "media_signal_score": 1.0,
        "chat_signal_score": 100,
        "audio_quality_score": 100,
        "gameplay_signal": 1.0,
        "context": "perfect moment",
        "speech_density": 3.0,
    }
    raw = {
        "clips": [{
            "id": "c1", "start": 0, "end": 20,
            "title": "Peak", "hook": "Hook",
            "hook_score": 100, "payoff_score": 100,
            "emotion_score": 100, "novelty_score": 100,
            "context_score": 100, "shareability_score": 100,
            "creator_fit_score": 100, "replay_score": 100,
        }]
    }
    result = enrich_ai_result(raw, [candidate], {}, [])
    assert result["clips"][0]["opportunity_score"] <= 100
