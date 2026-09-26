from ..media.ffprobe import probe


def analyze_media(path):
    metadata = probe(path)
    duration = float(metadata.get("format", {}).get("duration") or 0)
    streams = metadata.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_video = any(s.get("codec_type") == "video" for s in streams)
    return {"duration": duration, "has_audio": has_audio, "has_video": has_video, "streams": streams, "format": metadata.get("format", {})}
