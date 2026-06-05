from datetime import datetime

from pydantic import BaseModel


class StorjMoveResponse(BaseModel):
    status_code: int
    body: str


class StorageActionRow(BaseModel):
    action_id: str
    video_id: str
    job_id: str
    publisher_user_id: str
    action_type: str
    threshold: float
    final_score: float
    status: str
    request_url: str
    request_body_json: str
    response_status: int | None
    response_body: str
    created_at: datetime
    completed_at: datetime | None
    updated_at_replacing: datetime

