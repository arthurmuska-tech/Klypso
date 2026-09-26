SUPPORTED_FORMATS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def framing_plan(aspect_ratio="9:16"):
    if aspect_ratio not in SUPPORTED_FORMATS:
        raise ValueError("Format de cadrage non supporté.")
    return {"aspect_ratio": aspect_ratio, "resolution": SUPPORTED_FORMATS[aspect_ratio], "tracking": "progressive", "targets": ["face", "webcam", "area_of_interest"]}
