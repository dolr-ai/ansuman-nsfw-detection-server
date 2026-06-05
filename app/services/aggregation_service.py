from datetime import UTC, datetime

from app.config.settings import Settings
from app.core.constants import MODERATION_CATEGORIES, RISK_ORDER, UNSAFE_CATEGORIES
from app.models.frame_result import FrameModerationResult
from app.models.video_result import VideoModerationResult
from app.services.legacy_mapping_service import map_legacy_nsfw_ec, map_legacy_nsfw_gore


def frame_is_nsfw(frame: FrameModerationResult) -> bool:
    return frame.is_nsfw or frame.top_category in UNSAFE_CATEGORIES or frame.overall_severity >= 3


class AggregationService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def aggregate(
        self,
        *,
        job_id: str,
        video_id: str,
        policy_version: str,
        frames: list[FrameModerationResult],
    ) -> VideoModerationResult:
        if not frames:
            raise ValueError("cannot aggregate an empty frame list")

        max_category_severities = {
            category: max(frame.categories.get(category, 0) for frame in frames)
            for category in MODERATION_CATEGORIES
        }
        nsfw_frame_count = sum(1 for frame in frames if frame_is_nsfw(frame))
        max_overall_severity = max(frame.overall_severity for frame in frames)
        final_is_nsfw = nsfw_frame_count > 0
        final_score = max_overall_severity / 5.0
        final_top_category = self._select_top_category(frames)
        move_required = final_score >= self._settings.move_threshold
        now = datetime.now(UTC)
        final_response = {
            "final_is_nsfw": final_is_nsfw,
            "final_score": final_score,
            "final_top_category": final_top_category,
            "max_overall_severity": max_overall_severity,
            "nsfw_frame_count": nsfw_frame_count,
            "total_frame_count": len(frames),
            "move_required": move_required,
            "max_category_severities": max_category_severities,
        }
        legacy_nsfw_ec = map_legacy_nsfw_ec(final_top_category)
        legacy_nsfw_gore = map_legacy_nsfw_gore(max_category_severities)

        return VideoModerationResult(
            job_id=job_id,
            video_id=video_id,
            policy_version=policy_version,
            prompt_version=self._settings.visual_prompt_version,
            aggregation_version=self._settings.aggregation_version,
            final_is_nsfw=final_is_nsfw,
            final_score=final_score,
            final_top_category=final_top_category,
            max_overall_severity=max_overall_severity,
            nsfw_frame_count=nsfw_frame_count,
            total_frame_count=len(frames),
            move_required=move_required,
            move_threshold=self._settings.move_threshold,
            max_category_severities=max_category_severities,
            legacy_nsfw_ec=legacy_nsfw_ec,
            legacy_nsfw_gore=legacy_nsfw_gore,
            final_response=final_response,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _select_top_category(frames: list[FrameModerationResult]) -> str:
        risk_rank = {category: index for index, category in enumerate(RISK_ORDER)}
        best = max(
            frames,
            key=lambda frame: (
                frame.overall_severity,
                -risk_rank.get(frame.top_category, len(RISK_ORDER)),
            ),
        )
        highest_severity = best.overall_severity
        candidates = [frame.top_category for frame in frames if frame.overall_severity == highest_severity]
        return min(candidates, key=lambda category: risk_rank.get(category, len(RISK_ORDER)))

