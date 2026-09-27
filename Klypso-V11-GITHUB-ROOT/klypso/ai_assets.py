"""Optional generative assets for KLYPSO.

Gemini image generation is used for visual B-roll; ElevenLabs is used for
voiceover. Both integrations are opt-in and server-side-keyed.
"""
import base64
import os
from pathlib import Path

import requests


def _gemini_key():
    values = [os.getenv("GEMINI_API_KEY", "")] + [
        os.getenv(f"GEMINI_API_KEY_{index}", "") for index in range(1, 6)
    ]
    return next((value.strip() for value in values if value and value.strip()), "")


def generate_broll_image(prompt, output_path, aspect_ratio="9:16"):
    key = _gemini_key()
    if not key:
        raise RuntimeError("Aucune clé Gemini configurée pour le B-roll IA.")
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={
            "model": os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            "input": prompt,
            "response_format": {
                "type": "image",
                "mime_type": "image/png",
                "aspect_ratio": aspect_ratio,
                "image_size": "1K",
            },
        },
        timeout=240,
    )
    response.raise_for_status()
    payload = response.json()
    data = ((payload.get("interaction") or {}).get("output_image") or {}).get("data")
    if not data:
        data = (payload.get("output_image") or {}).get("data")
    if not data:
        raise RuntimeError("Gemini n'a retourné aucun asset image.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(data))
    return output


def _eleven_key():
    return (os.getenv("ELEVENLABS_API_KEY", "") or "").strip()


def generate_voiceover(text, output_path, voice_id=None):
    key = _eleven_key()
    voice = (voice_id or os.getenv("ELEVENLABS_VOICE_ID", "")).strip()
    if not key:
        raise RuntimeError("Aucune clé ElevenLabs configurée pour le voiceover IA.")
    if not voice:
        raise RuntimeError("ELEVENLABS_VOICE_ID est requis pour le voiceover IA.")
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={
            "text": " ".join(str(text or "").split())[:5000],
            "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        },
        timeout=180,
    )
    response.raise_for_status()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.content)
    return output


def asset_status():
    return {
        "ai_broll": bool(_gemini_key()),
        "ai_voiceover": bool(_eleven_key() and os.getenv("ELEVENLABS_VOICE_ID", "").strip()),
    }
