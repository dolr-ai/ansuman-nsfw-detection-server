from datetime import UTC

import pytest

from app.schemas.video import VideoBanRequest
from app.services.manual_ban_service import ManualBanService


class FakeRepository:
    def __init__(self) -> None:
        self.calls = []

    def insert_rows(self, table_name, rows):  # type: ignore[no-untyped-def]
        self.calls.append((table_name, rows))


@pytest.mark.asyncio
async def test_manual_ban_writes_excluded_and_legacy_rows(test_settings) -> None:  # type: ignore[no-untyped-def]
    excluded_repo = FakeRepository()
    legacy_repo = FakeRepository()
    service = ManualBanService(
        settings=test_settings,
        excluded_videos_repository=excluded_repo,
        legacy_repository=legacy_repo,
    )

    result = await service.ban_video(
        "video-1",
        VideoBanRequest(
            publisher_user_id="user-1",
            post_id="post-1",
            canister_id="canister-1",
            reason="user_report_approved",
            source="google_chat",
            trace_id="trace-1",
        ),
    )

    assert result.status == "banned"
    assert result.excluded_videos_written is True
    assert result.legacy_nsfw_agg_written is True
    assert result.trace_id == "trace-1"

    excluded_table, excluded_rows = excluded_repo.calls[0]
    assert excluded_table == "excluded_videos"
    assert len(excluded_rows) == 1
    assert excluded_rows[0].video_id == "video-1"
    assert excluded_rows[0].exclusion_reason == "banned"
    assert excluded_rows[0].excluded_at.tzinfo == UTC

    legacy_table, legacy_rows = legacy_repo.calls[0]
    assert legacy_table == "video_nsfw_agg"
    assert len(legacy_rows) == 1
    assert legacy_rows[0].video_id == "video-1"
    assert legacy_rows[0].is_nsfw is True
    assert legacy_rows[0].probability == 1.0
    assert legacy_rows[0].nsfw_ec == "explicit"
    assert legacy_rows[0].nsfw_gore == "VERY_UNLIKELY"
