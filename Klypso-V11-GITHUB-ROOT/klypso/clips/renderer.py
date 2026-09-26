from ..media.ffmpeg import render_clip


def render_candidate(input_path, output_path, candidate):
    return render_clip(input_path, output_path, candidate["start"], candidate["duration"])
