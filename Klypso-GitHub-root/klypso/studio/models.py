from dataclasses import dataclass, field

@dataclass
class TimelineClip:
    media_id: int
    start: float
    duration: float
    track: int = 0
    speed: float = 1.0

@dataclass
class Timeline:
    duration: float = 0.0
    clips: list = field(default_factory=list)
    audio_tracks: list = field(default_factory=list)
    markers: list = field(default_factory=list)
