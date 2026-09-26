from ..media.ffmpeg import run


def render_timeline(input_path, output_path, duration):
    return run(["-i", input_path, "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", output_path])
