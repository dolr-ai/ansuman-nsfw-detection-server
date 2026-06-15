from datetime import UTC, datetime

from app.repositories.clickhouse.excluded_videos_repository import ClickHouseExcludedVideosRepository
from app.repositories.clickhouse.video_result_repository import ClickHouseVideoResultRepository
from app.schemas.clickhouse import ExcludedVideoRow, VideoNsfwDetectionRow


class FakeClickHouseClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[list[object]], list[str]]] = []

    def insert(self, table_name: str, data: list[list[object]], *, column_names: list[str]) -> None:
        self.calls.append((table_name, data, column_names))


def test_clickhouse_insert_uses_column_names_and_replacing_column() -> None:
    now = datetime.now(UTC)
    client = FakeClickHouseClient()
    repo = ClickHouseVideoResultRepository(client, "yral")

    repo.insert_rows(
        "video_nsfw_detection",
        [
            VideoNsfwDetectionRow(
                video_id="video",
                job_id="job",
                publisher_user_id="user",
                post_id=None,
                canister_id=None,
                source_video_uri="https://example.com/video.mp4",
                source_object_version="",
                upload_event_id=None,
                status="classified",
                policy_version="nsfw_policy_v1",
                prompt_version="visual_batch_moderation_v1",
                aggregation_version="hard_any_frame_v1",
                model_provider="openai-compatible",
                model_name="model",
                model_version=None,
                duration_seconds=1.0,
                frames_extracted=1,
                frames_processed=1,
                frame_batch_size=5,
                final_is_nsfw=False,
                final_score=0.0,
                final_top_category="safe",
                max_overall_severity=0,
                nsfw_frame_count=0,
                total_frame_count=1,
                max_suggestive_severity=0,
                max_nudity_severity=0,
                max_porn_severity=0,
                max_gore_severity=0,
                max_violence_severity=0,
                max_self_harm_severity=0,
                max_hate_or_extremism_severity=0,
                max_drugs_severity=0,
                max_unknown_severity=0,
                max_sexual_minor_content_severity=0,
                move_required=False,
                move_threshold=0.8,
                storj_move_status="not_required",
                legacy_nsfw_ec="neutral",
                legacy_nsfw_gore="VERY_UNLIKELY",
                frame_results_json="[]",
                final_response_json="{}",
                created_at=now,
                updated_at=now,
                updated_at_replacing=now,
            )
        ],
    )

    table_name, data, columns = client.calls[0]
    assert table_name == "yral.video_nsfw_detection"
    assert "_updated_at" in columns
    assert "updated_at_replacing" not in columns
    assert len(data) == 1
    assert len(data[0]) == len(columns)


def test_excluded_video_insert_uses_replacing_column() -> None:
    now = datetime.now(UTC)
    client = FakeClickHouseClient()
    repo = ClickHouseExcludedVideosRepository(client, "yral")

    repo.insert_rows(
        "excluded_videos",
        [
            ExcludedVideoRow(
                video_id="video",
                excluded_at=now,
                exclusion_reason="banned",
                updated_at_replacing=now,
            )
        ],
    )

    table_name, data, columns = client.calls[0]
    assert table_name == "yral.excluded_videos"
    assert columns == ["video_id", "excluded_at", "exclusion_reason", "_updated_at"]
    assert len(data) == 1
    assert len(data[0]) == len(columns)
