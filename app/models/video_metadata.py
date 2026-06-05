from dataclasses import dataclass


@dataclass(frozen=True)
class VideoMetadata:
    job_id: str
    video_id: str
    duration_seconds: float
    width: int | None
    height: int | None
    fps: float | None
    codec_name: str | None
    has_video_stream: bool
    frames_extracted: int

