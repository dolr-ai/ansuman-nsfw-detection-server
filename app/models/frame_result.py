from dataclasses import dataclass


@dataclass(frozen=True)
class FrameModerationResult:
    frame_index: int
    frame_timestamp_seconds: float
    top_category: str
    is_nsfw: bool
    overall_severity: int
    categories: dict[str, int]
    reason: str
    raw_response: dict[str, object]

