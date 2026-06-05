import argparse
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.clients.clickhouse import create_clickhouse_client
from app.clients.kvrocks import create_kvrocks_client
from app.config.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate live storage integrations with cleanup-safe test IDs.")
    parser.add_argument("--postgres", action="store_true", help="Validate PostgreSQL with insert/query/delete.")
    parser.add_argument("--kvrocks", action="store_true", help="Validate KVRocks with set/get/delete.")
    parser.add_argument("--clickhouse", action="store_true", help="Validate ClickHouse with insert/query/delete mutations.")
    parser.add_argument("--storj-config", action="store_true", help="Validate Storj interface config is present only.")
    parser.add_argument("--all-safe", action="store_true", help="Run all non-Storj-move validations.")
    return parser.parse_args()


async def validate_postgres(settings: Settings, test_id: str) -> dict[str, object]:
    if settings.postgres_database_url is None:
        return {"ok": False, "reason": "POSTGRES_DATABASE_URL is not configured"}

    url = _postgres_async_url(settings.postgres_database_url.get_secret_value())
    engine = create_async_engine(url)
    job_id = f"validate:{test_id}"
    video_id = f"validate-video-{test_id}"
    now = datetime.now(UTC)
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("SELECT 1"))
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO nsfw_video_jobs (
                        job_id, video_id, source_object_version, policy_version, status,
                        publisher_user_id, source_video_uri, trace_id
                    )
                    VALUES (
                        :job_id, :video_id, '', 'nsfw_policy_v1', 'queued',
                        'validate-user', 'https://example.com/validate.mp4', :trace_id
                    )
                    """
                ),
                {"job_id": job_id, "video_id": video_id, "trace_id": test_id},
            )
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO nsfw_frame_results (
                        frame_id, job_id, video_id, frame_index, frame_timestamp_seconds,
                        prompt_version, model_provider, model_name, top_category, is_nsfw,
                        overall_severity, safe_severity, suggestive_severity, nudity_severity,
                        porn_severity, gore_severity, violence_severity, self_harm_severity,
                        hate_or_extremism_severity, drugs_severity, unknown_severity,
                        sexual_minor_content_severity, reason, raw_response
                    )
                    VALUES (
                        :frame_id, :job_id, :video_id, 0, 0.0,
                        'visual_batch_moderation_v1', 'validate', 'validate-model',
                        'safe', false,
                        0, 0, 0, 0,
                        0, 0, 0, 0,
                        0, 0, 0,
                        0, 'validate', CAST(:raw_response AS jsonb)
                    )
                    """
                ),
                {"frame_id": f"{job_id}:0", "job_id": job_id, "video_id": video_id, "raw_response": "{}"},
            )
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO nsfw_video_results (
                        job_id, video_id, policy_version, prompt_version, aggregation_version,
                        final_is_nsfw, final_score, final_top_category, max_overall_severity,
                        nsfw_frame_count, total_frame_count, move_required, move_threshold,
                        legacy_nsfw_ec, legacy_nsfw_gore, final_response
                    )
                    VALUES (
                        :job_id, :video_id, 'nsfw_policy_v1', 'visual_batch_moderation_v1',
                        'hard_any_frame_v1', false, 0.0, 'safe', 0,
                        0, 1, false, 0.8, 'neutral', 'VERY_UNLIKELY', CAST(:final_response AS jsonb)
                    )
                    """
                ),
                {"job_id": job_id, "video_id": video_id, "final_response": "{}"},
            )
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO nsfw_storage_actions (
                        action_id, job_id, video_id, publisher_user_id, action_type,
                        threshold, final_score, request_url, request_body,
                        response_status, response_body, status, completed_at
                    )
                    VALUES (
                        :action_id, :job_id, :video_id, 'validate-user', 'validate_noop',
                        0.8, 0.0, 'https://example.com/noop', CAST(:request_body AS jsonb),
                        200, 'ok', 'succeeded', :completed_at
                    )
                    """
                ),
                {
                    "action_id": f"storage-action:{job_id}",
                    "job_id": job_id,
                    "video_id": video_id,
                    "request_body": "{}",
                    "completed_at": now,
                },
            )
            count = await conn.scalar(
                sa.text("SELECT count(*) FROM nsfw_video_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            )
            await conn.execute(sa.text("DELETE FROM nsfw_video_jobs WHERE job_id = :job_id"), {"job_id": job_id})
        return {"ok": count == 1, "job_id": job_id, "cleanup": "deleted"}
    finally:
        await engine.dispose()


async def validate_kvrocks(settings: Settings, test_id: str) -> dict[str, object]:
    if not settings.is_kvrocks_configured():
        return {"ok": False, "reason": "KVROCKS_HOST is not configured"}

    client = create_kvrocks_client(settings)
    key = f"nsfw:validate:{test_id}"
    try:
        await client.ping()
        await client.set(key, "ok", ex=60)
        value = await client.get(key)
        await client.delete(key)
        return {"ok": value == "ok", "key": key, "cleanup": "deleted"}
    finally:
        await client.aclose()


def validate_clickhouse(settings: Settings, test_id: str) -> dict[str, object]:
    if not settings.is_clickhouse_configured():
        return {"ok": False, "reason": "CLICKHOUSE_PRIMARY_DATABASE_URL is not configured"}

    client = create_clickhouse_client(settings)
    database = settings.clickhouse_database
    video_id = f"validate-video-{test_id}"
    job_id = f"validate:{test_id}"
    now = datetime.now(UTC)

    video_table = f"{database}.{settings.clickhouse_nsfw_table}"
    legacy_table = f"{database}.{settings.clickhouse_nsfw_agg_table}"
    storage_table = f"{database}.{settings.clickhouse_storage_actions_table}"

    video_columns = [
        "video_id",
        "job_id",
        "publisher_user_id",
        "post_id",
        "canister_id",
        "source_video_uri",
        "source_object_version",
        "upload_event_id",
        "status",
        "policy_version",
        "prompt_version",
        "aggregation_version",
        "model_provider",
        "model_name",
        "model_version",
        "duration_seconds",
        "frames_extracted",
        "frames_processed",
        "frame_batch_size",
        "final_is_nsfw",
        "final_score",
        "final_top_category",
        "max_overall_severity",
        "nsfw_frame_count",
        "total_frame_count",
        "max_suggestive_severity",
        "max_nudity_severity",
        "max_porn_severity",
        "max_gore_severity",
        "max_violence_severity",
        "max_self_harm_severity",
        "max_hate_or_extremism_severity",
        "max_drugs_severity",
        "max_unknown_severity",
        "max_sexual_minor_content_severity",
        "move_required",
        "move_threshold",
        "storj_move_status",
        "legacy_nsfw_ec",
        "legacy_nsfw_gore",
        "frame_results_json",
        "final_response_json",
        "created_at",
        "updated_at",
        "_updated_at",
    ]
    video_values = [
        video_id,
        job_id,
        "validate-user",
        None,
        None,
        "https://example.com/validate.mp4",
        "",
        None,
        "classified",
        "nsfw_policy_v1",
        "visual_batch_moderation_v1",
        "hard_any_frame_v1",
        "validate",
        "validate-model",
        None,
        0.0,
        1,
        1,
        5,
        0,
        0.0,
        "safe",
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0.8,
        "not_required",
        "neutral",
        "VERY_UNLIKELY",
        "[]",
        "{}",
        now,
        now,
        now,
    ]

    legacy_columns = ["video_id", "gcs_video_id", "nsfw_ec", "nsfw_gore", "is_nsfw", "probability"]
    legacy_values = [video_id, None, "neutral", "VERY_UNLIKELY", 0, 0.0]

    storage_columns = [
        "action_id",
        "video_id",
        "job_id",
        "publisher_user_id",
        "action_type",
        "threshold",
        "final_score",
        "status",
        "request_url",
        "request_body_json",
        "response_status",
        "response_body",
        "created_at",
        "completed_at",
        "_updated_at",
    ]
    storage_values = [
        f"storage-action:{job_id}",
        video_id,
        job_id,
        "validate-user",
        "validate_noop",
        0.8,
        0.0,
        "succeeded",
        "https://example.com/noop",
        "{}",
        200,
        "ok",
        now,
        now,
        now,
    ]

    try:
        client.command("SELECT 1")
        client.insert(video_table, [video_values], column_names=video_columns)
        client.insert(legacy_table, [legacy_values], column_names=legacy_columns)
        client.insert(storage_table, [storage_values], column_names=storage_columns)
        count = client.query(
            f"SELECT count() FROM {video_table} WHERE video_id = {{video_id:String}}",
            parameters={"video_id": video_id},
        ).result_rows[0][0]
        for table in (video_table, legacy_table, storage_table):
            client.command(
                f"ALTER TABLE {table} DELETE WHERE video_id = {{video_id:String}} SETTINGS mutations_sync = 1",
                parameters={"video_id": video_id},
            )
        return {"ok": count == 1, "video_id": video_id, "cleanup": "delete_mutation_submitted"}
    finally:
        client.close()


def validate_storj_config(settings: Settings) -> dict[str, object]:
    return {
        "ok": bool(settings.storj_interface_url and settings.storj_interface_token),
        "url_configured": bool(settings.storj_interface_url),
        "token_configured": bool(settings.storj_interface_token),
        "move_called": False,
    }


def _postgres_async_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def main() -> None:
    args = parse_args()
    settings = Settings()
    test_id = str(uuid4())
    results: dict[str, object] = {"test_id": test_id}

    if args.all_safe or args.postgres:
        results["postgres"] = await _capture_async(validate_postgres(settings, test_id))
    if args.all_safe or args.kvrocks:
        results["kvrocks"] = await _capture_async(validate_kvrocks(settings, test_id))
    if args.all_safe or args.clickhouse:
        results["clickhouse"] = _capture_sync(lambda: validate_clickhouse(settings, test_id))
    if args.storj_config:
        results["storj"] = validate_storj_config(settings)

    print(results)


async def _capture_async(awaitable) -> dict[str, object]:  # type: ignore[no-untyped-def]
    try:
        return await awaitable
    except Exception as exc:
        return {"ok": False, "error_type": exc.__class__.__name__, "error": str(exc)}


def _capture_sync(func) -> dict[str, object]:  # type: ignore[no-untyped-def]
    try:
        return func()
    except Exception as exc:
        return {"ok": False, "error_type": exc.__class__.__name__, "error": str(exc)}


if __name__ == "__main__":
    asyncio.run(main())
