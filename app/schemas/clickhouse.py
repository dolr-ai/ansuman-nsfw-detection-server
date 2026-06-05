from datetime import datetime

from pydantic import BaseModel


class VideoNsfwDetectionRow(BaseModel):
    video_id: str
    job_id: str
    publisher_user_id: str
    post_id: str | None
    canister_id: str | None
    source_video_uri: str
    source_object_version: str
    upload_event_id: str | None
    status: str
    policy_version: str
    prompt_version: str
    aggregation_version: str
    model_provider: str
    model_name: str
    model_version: str | None
    duration_seconds: float
    frames_extracted: int
    frames_processed: int
    frame_batch_size: int
    final_is_nsfw: bool
    final_score: float
    final_top_category: str
    max_overall_severity: int
    nsfw_frame_count: int
    total_frame_count: int
    max_suggestive_severity: int
    max_nudity_severity: int
    max_porn_severity: int
    max_gore_severity: int
    max_violence_severity: int
    max_self_harm_severity: int
    max_hate_or_extremism_severity: int
    max_drugs_severity: int
    max_unknown_severity: int
    max_sexual_minor_content_severity: int
    move_required: bool
    move_threshold: float
    storj_move_status: str
    legacy_nsfw_ec: str
    legacy_nsfw_gore: str
    frame_results_json: str
    final_response_json: str
    created_at: datetime
    updated_at: datetime
    updated_at_replacing: datetime

