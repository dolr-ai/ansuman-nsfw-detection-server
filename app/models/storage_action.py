from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StorageAction:
    action_id: str
    job_id: str
    video_id: str
    publisher_user_id: str
    action_type: str
    threshold: float
    final_score: float
    request_url: str
    request_body: dict[str, object]
    response_status: int | None
    response_body: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None

