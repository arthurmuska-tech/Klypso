import json
import shutil
import subprocess


def ffprobe_available():
    return shutil.which("ffprobe") is not None


def probe(path):
    if not ffprobe_available():
        raise RuntimeError("FFprobe est introuvable dans le PATH.")
    command = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFprobe a échoué.")
    return json.loads(result.stdout or "{}")
