import json
from pathlib import Path

from klypso import create_app
from klypso.clips.agents import run_agent_suite
from klypso.clips.chat_intelligence import build_chat_signals, enrich_candidates_with_chat_signals
from klypso.clips.intelligence import enrich_ai_result
from klypso.clips.media_intelligence import enrich_candidates_with_media_signals
from klypso.clips.vision_tracking import enrich_candidates_with_face_tracking
from klypso.social_profiles import clamp_candidate_to_profile, get_social_profile
from klypso.clips.renderer import _video_filter


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
    assert response.get_json()["version"] == "19.0.0"


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
