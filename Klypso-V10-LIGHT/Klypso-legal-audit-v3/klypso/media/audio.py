from .ffmpeg import run


def normalize_audio(input_path, output_path, target_lufs=-14):
    return run(["-i", input_path, "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11", "-c:v", "copy", "-c:a", "aac", output_path])
