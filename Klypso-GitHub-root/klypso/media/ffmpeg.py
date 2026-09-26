import shutil
import subprocess


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def run(args):
    if not ffmpeg_available():
        raise RuntimeError("FFmpeg est introuvable dans le PATH.")
    result = subprocess.run(["ffmpeg", "-hide_banner", "-y", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-4000:] or "FFmpeg a échoué.")
    return result


def render_clip(input_path, output_path, start, duration):
    return run(["-ss", str(start), "-i", input_path, "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", output_path])
