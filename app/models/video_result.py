from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VideoModerationResult:
    job_id: str
    video_id: str
    policy_version: str
    prompt_version: str
    aggregation_version: str
    final_is_nsfw: bool
    final_score: float
    final_top_category: str
    max_overall_severity: int
    nsfw_frame_count: int
    total_frame_count: int
    move_required: bool
    move_threshold: float
    max_category_severities: dict[str, int]
    legacy_nsfw_ec: str
    legacy_nsfw_gore: str
    final_response: dict[str, object]
    created_at: datetime
    updated_at: datetime

