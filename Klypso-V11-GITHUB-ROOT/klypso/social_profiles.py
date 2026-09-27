"""KLYPSO social output profiles.

These are product presets and safety-oriented defaults, not a claim that every
platform currently enforces exactly these limits.
"""

SOCIAL_PROFILES = {
    "youtube": {
        "name": "YouTube Shorts",
        "output_format": "9:16",
        "recommended_max_seconds": 60,
        "preset": "gaming",
        "caption_style": "dynamic",
        "hashtags": ["#shorts", "#gaming"],
    },
    "tiktok": {
        "name": "TikTok",
        "output_format": "9:16",
        "recommended_max_seconds": 90,
        "preset": "dynamic",
        "caption_style": "dynamic",
        "hashtags": ["#tiktok", "#gaming"],
    },
    "instagram": {
        "name": "Instagram Reels",
        "output_format": "9:16",
        "recommended_max_seconds": 90,
        "preset": "dynamic",
        "caption_style": "classic",
        "hashtags": ["#reels", "#gaming"],
    },
    "x": {
        "name": "X",
        "output_format": "16:9",
        "recommended_max_seconds": 140,
        "preset": "clean",
        "caption_style": "classic",
        "hashtags": ["#gaming"],
    },
}


def get_social_profile(platform):
    return dict(SOCIAL_PROFILES.get(platform, SOCIAL_PROFILES["youtube"]))


def clamp_candidate_to_profile(candidate, profile):
    item = dict(candidate or {})
    start = max(0.0, float(item.get("start", 0) or 0))
    end = max(start + 1.0, float(item.get("end", start + 1) or (start + 1)))
    max_seconds = float(profile.get("recommended_max_seconds", 60))
    if end - start > max_seconds:
        end = start + max_seconds
    item["start"] = round(start, 3)
    item["end"] = round(end, 3)
    item["duration"] = round(max(1.0, end - start), 3)
    return item
