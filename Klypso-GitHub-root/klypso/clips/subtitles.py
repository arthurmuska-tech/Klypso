def subtitle_policy(style="classic"):
    return {"style": style, "safe_margin": True, "dynamic_words": style == "dynamic", "external_transcription_required": True}
