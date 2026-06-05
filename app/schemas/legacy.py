from pydantic import BaseModel


class LegacyNsfwAggRow(BaseModel):
    video_id: str
    gcs_video_id: str | None
    nsfw_ec: str | None
    nsfw_gore: str | None
    is_nsfw: bool
    probability: float
