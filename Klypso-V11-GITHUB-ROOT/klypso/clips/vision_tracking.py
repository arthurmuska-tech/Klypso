"""Optional local vision tracking for KLYPSO.

This module detects the largest visible face in sampled frames. It is a tracking
signal, not semantic scene understanding, and gracefully disables itself when
OpenCV or a usable cascade is unavailable.
"""
from pathlib import Path


def analyze_face_tracking(path, sample_every=0.75, max_samples=900):
    try:
        import cv2
    except ImportError:
        return {"engine": "opencv-face-v1", "available": False, "tracks": []}

    source = Path(path)
    if not source.is_file():
        return {"engine": "opencv-face-v1", "available": False, "tracks": []}

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return {"engine": "opencv-face-v1", "available": False, "tracks": []}

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
    step = max(1, int(round(fps * max(0.2, float(sample_every)))))
    cascade_path = getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml"
    classifier = cv2.CascadeClassifier(cascade_path)
    if classifier.empty():
        capture.release()
        return {"engine": "opencv-face-v1", "available": False, "tracks": []}

    tracks = []
    frame_index = 0
    samples = 0
    while samples < max_samples:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % step != 0:
            frame_index += 1
            continue

        samples += 1
        frame_index += 1
        small = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = classifier.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(36, 36),
        )
        if len(faces):
            x, y, w, h = max(faces, key=lambda box: int(box[2]) * int(box[3]))
            center_x = (x + w / 2.0) / 640.0
            center_y = (y + h / 2.0) / 360.0
            area = (w * h) / (640.0 * 360.0)
            tracks.append({
                "time": round(frame_index / max(fps, 1.0), 3),
                "focus_x": round(float(center_x), 4),
                "focus_y": round(float(center_y), 4),
                "area": round(float(area), 5),
            })

    capture.release()
    return {
        "engine": "opencv-face-v1",
        "available": True,
        "sample_count": samples,
        "track_count": len(tracks),
        "duration": round(duration, 3),
        "tracks": tracks[:max_samples],
    }


def _nearest_track(tracks, start, end):
    if not tracks:
        return None
    midpoint = (float(start) + float(end)) / 2.0
    return min(tracks, key=lambda item: abs(float(item.get("time", 0)) - midpoint))


def enrich_candidates_with_face_tracking(candidates, tracking):
    tracks = (tracking or {}).get("tracks") or []
    enriched = []
    for candidate in candidates or []:
        item = dict(candidate)
        match = _nearest_track(tracks, item.get("start", 0), item.get("end", 0))
        if match:
            item["face_focus_x"] = match["focus_x"]
            item["face_focus_y"] = match["focus_y"]
            item["face_area"] = match["area"]
            # Keep a face focus only when the detected subject is substantial enough.
            if float(match["area"]) >= 0.003:
                item["focus_x"] = match["focus_x"]
                item["focus_y"] = match["focus_y"]
                item["reframe_mode"] = "smart_face"
        enriched.append(item)
    return enriched
