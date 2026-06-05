from app.models.video_result import VideoModerationResult
from app.schemas.legacy import LegacyNsfwAggRow


def map_legacy_nsfw_ec(final_top_category: str) -> str:
    mapping = {
        "porn": "explicit",
        "nudity": "nudity",
        "suggestive": "provocative",
        "sexual_minor_content": "explicit",
    }
    return mapping.get(final_top_category, "neutral")


def map_legacy_nsfw_gore(max_category_severities: dict[str, int]) -> str:
    severity = max(
        max_category_severities.get("gore", 0),
        max_category_severities.get("violence", 0),
    )
    if severity >= 5:
        return "VERY_LIKELY"
    if severity >= 4:
        return "LIKELY"
    if severity >= 3:
        return "POSSIBLE"
    if severity >= 1:
        return "UNLIKELY"
    return "VERY_UNLIKELY"


def to_legacy_nsfw_agg(
    result: VideoModerationResult,
    historical_gcs_video_id: str | None = None,
) -> LegacyNsfwAggRow:
    return LegacyNsfwAggRow(
        video_id=result.video_id,
        gcs_video_id=historical_gcs_video_id,
        nsfw_ec=result.legacy_nsfw_ec,
        nsfw_gore=result.legacy_nsfw_gore,
        is_nsfw=result.final_is_nsfw,
        probability=result.final_score,
    )

