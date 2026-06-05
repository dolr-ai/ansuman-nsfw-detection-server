# NSFW Detection Repo Revamp Implementation Plan

This plan converts the current `nsfw_detect` Python gRPC service into an internal REST API plus worker system. The service will own request authentication, durable enqueue, video download, FFmpeg frame extraction, batched GPU moderation calls, PostgreSQL frame-level storage, final ClickHouse writes, legacy ClickHouse compatibility writes, KVRocks runtime compatibility, and Storj NSFW bucket movement.

The current repo contains a small gRPC service and old pipeline support code:

- `server.py`: current gRPC server.
- `nsfw_detector.proto`, `nsfw_detector_pb2.py`, `nsfw_detector_pb2_grpc.py`: generated gRPC API.
- `nsfw_detect_utils.py`: old local image classifiers plus Google Vision gore detection.
- `bigquery_client.py`: old embedding-probability lookup.
- `utils/gcs_utils.py`: old GCS frame utility.
- `localping.py`, `ping_server.py`, `concurrent_ping.py`: old gRPC callers/smoke tools.

All legacy code should move under `app/legacy/` during the migration. New production code should not import legacy modules except behind explicit compatibility feature flags.

## Locked Decisions

These are now treated as implementation decisions, not open questions:

1. `POST /v1/videos/detect` is asynchronous and returns `202 Accepted` after durable enqueue.
2. Queue/worker retries own failed processing; off-chain retries only failed enqueue/API calls.
3. Request signing uses a new HMAC shared secret.
4. Off-chain cuts over fully to REST behind a feature flag.
5. Frame-level data lives only in PostgreSQL.
6. ClickHouse stores final video-level results, the old-compatible `video_nsfw_agg` shape, and storage-move audit rows.
7. A mapper function converts the new final result into the old NSFW aggregate schema and writes it to a new ClickHouse legacy table with the old columns.
8. The old BigQuery table is not a required online write target for this service.
9. The service uses env vars already present in this repo, loaded through typed config.
10. The model response schema is provisional until the final structured prompt is provided.
11. A video is flagged if any processed frame is NSFW. Do not average away one bad frame.
12. Storj move threshold is `final_score >= 0.8`.
13. If a Storj move is required and fails, the worker attempt fails. Final PostgreSQL, KVRocks, and ClickHouse writes for that attempt must be rolled back or not performed. The queue retries the job.
14. Per-frame model failures are not stored in PostgreSQL. Retry the failed model request/batch; if retries are exhausted, the whole worker attempt fails or the video is sent to terminal failure according to retry budget.

## Target Flow

```text
off-chain-agent
  -> signed REST request
  -> nsfw_detect FastAPI
  -> durable video job enqueue
  -> worker claims job
  -> worker downloads video from Storj/source URL
  -> ffprobe + ffmpeg
  -> one frame per second
  -> frame batches of five
  -> OpenAI-compatible GPU server
  -> retry failed model request/batch
  -> PostgreSQL frame/video transaction staging
  -> hard any-frame NSFW policy
  -> if final_score >= 0.8, storj-interface /move-to-nsfw
  -> commit PostgreSQL frame/video/storage-action rows
  -> transform final result into old schema
  -> buffer/write new ClickHouse final table
  -> write old-compatible ClickHouse table
  -> write KVRocks runtime compatibility key
  -> mark job classified
```

The important ordering rule is: do not publish final result state to ClickHouse or KVRocks until required Storj movement has succeeded. This avoids a final database state that says "moved/NSFW" while storage movement failed.

## Recommended Stack

- Python: 3.11 or 3.12.
- Package manager: `uv`.
- API: `FastAPI`.
- Runtime server: `uvicorn` or `gunicorn` with `uvicorn.workers.UvicornWorker`.
- Schemas: `pydantic`.
- PostgreSQL: SQLAlchemy async or `asyncpg`.
- PostgreSQL migrations: `alembic`.
- ClickHouse: `clickhouse-connect`.
- KVRocks: `redis-py` against Redis-compatible protocol.
- GPU model client: official `openai` Python client pointed at the OpenAI-compatible Vast AI endpoint.
- HTTP download and Storj interface calls: `httpx.AsyncClient`.
- Video tooling: system `ffmpeg` and `ffprobe`.
- Retries: `tenacity` or small local retry helper.
- Error tracking: `sentry-sdk`.
- Tests: `pytest`, `pytest-asyncio`, `httpx`, fake repositories/clients.
- Lint/format: `ruff`; optional type check with `mypy` or `pyright` once models stabilize.

## File And Folder Structure

Use a layered structure. Keep it explicit, but avoid excessive abstraction.

```text
nsfw_detect/
  app/
    __init__.py
    main.py

    api/
      __init__.py
      deps.py
      router.py
      v1/
        __init__.py
        routes_health.py
        routes_images.py
        routes_text.py
        routes_videos.py

    config/
      __init__.py
      settings.py
      logging.py

    core/
      __init__.py
      constants.py
      lifecycle.py
      security.py
      sentry.py
      time.py

    middleware/
      __init__.py
      error_handler.py
      request_id.py
      signed_request.py

    errors/
      __init__.py
      base.py
      codes.py
      http.py

    schemas/
      __init__.py
      auth.py
      common.py
      image.py
      text.py
      video.py
      model_output.py
      clickhouse.py
      legacy.py
      storage_action.py

    models/
      __init__.py
      enums.py
      frame_result.py
      storage_action.py
      video_job.py
      video_metadata.py
      video_result.py

    repositories/
      __init__.py
      base.py
      unit_of_work.py
      postgres/
        __init__.py
        base.py
        frame_result_repository.py
        storage_action_repository.py
        video_job_repository.py
        video_metadata_repository.py
        video_result_repository.py
      clickhouse/
        __init__.py
        base.py
        legacy_nsfw_agg_repository.py
        storage_action_repository.py
        video_result_repository.py
      kvrocks/
        __init__.py
        auth_nonce_repository.py
        clickhouse_buffer_repository.py
        queue_repository.py
        runtime_nsfw_repository.py

    clients/
      __init__.py
      clickhouse.py
      gpu_openai.py
      http.py
      kvrocks.py
      postgres.py
      storj_interface.py

    services/
      __init__.py
      base.py
      aggregation_service.py
      auth_service.py
      clickhouse_flush_service.py
      frame_extraction_service.py
      gpu_moderation_service.py
      image_detection_service.py
      legacy_mapping_service.py
      queue_service.py
      storage_move_service.py
      text_detection_service.py
      video_detection_service.py

    prompts/
      visual_batch_moderation_v1.txt
      text_moderation_v1.txt

    workers/
      __init__.py
      clickhouse_flush_worker.py
      video_worker.py

    utils/
      __init__.py
      file_cleanup.py
      hashing.py
      json.py
      redaction.py
      subprocess.py

    legacy/
      __init__.py
      grpc_server.py
      nsfw_detector.proto
      nsfw_detector_pb2.py
      nsfw_detector_pb2_grpc.py
      nsfw_detect_utils.py
      bigquery_client.py
      localping.py
      ping_server.py
      concurrent_ping.py
      utils/
        gcs_utils.py

  alembic/
    env.py
    script.py.mako
    versions/

  db/
    clickhouse/
      001_video_nsfw_detection.sql
      002_video_nsfw_agg.sql
      003_video_nsfw_storage_actions.sql
    postgres/
      README.md

  scripts/
    create_clickhouse_tables.py
    enqueue_test_video.py
    flush_clickhouse_buffer.py
    smoke_image_url.py
    smoke_text.py
    smoke_video_detect.py

  tests/
    unit/
      api/
      repositories/
      services/
    integration/
      api/
      workers/
    fixtures/
      videos/
      images/
      model_responses/

  Makefile
  pyproject.toml
  README.md
```

### Dependency Direction

Use this dependency direction only:

```text
routes -> services -> repositories -> clients/database
```

Rules:

- Routes validate HTTP and call services.
- Services own business logic and orchestration.
- Repositories own CRUD/persistence.
- Clients own external protocol details.
- Models are internal domain objects.
- Schemas are API, model-response, and database serialization shapes.
- Legacy code is isolated under `app/legacy/` and not imported by new code.

### Base Classes

Use base classes only where they remove obvious duplication:

- `BaseRepository`: stores shared client/session and logger; common helpers for execute/fetch operations.
- `PostgresRepository`: repository base bound to the current SQLAlchemy/asyncpg session.
- `ClickHouseRepository`: repository base with insert/query helpers and table-name helpers.
- `BaseService`: stores settings and logger; no heavy framework or inheritance tree.
- `UnitOfWork`: manages a PostgreSQL transaction for final job writes.

Do not create generic CRUD layers for every entity if the table behavior is specific. Prefer direct repository methods like `insert_frame_results`, `mark_job_processing`, `insert_final_result`, and `insert_legacy_nsfw_agg_rows`.

## Makefile Targets

Add a `Makefile` that wraps common development and runtime commands:

```makefile
.PHONY: install run worker flush-worker lint format check test test-unit test-integration migrate db-upgrade db-downgrade ch-ddl smoke-video smoke-image smoke-text

install:
	uv sync

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8080} --reload

worker:
	uv run python -m app.workers.video_worker

flush-worker:
	uv run python -m app.workers.clickhouse_flush_worker

lint:
	uv run ruff check app tests scripts

format:
	uv run ruff format app tests scripts

check: lint test

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

db-upgrade:
	uv run alembic upgrade head

db-downgrade:
	uv run alembic downgrade -1

ch-ddl:
	uv run python scripts/create_clickhouse_tables.py

smoke-video:
	uv run python scripts/smoke_video_detect.py

smoke-image:
	uv run python scripts/smoke_image_url.py

smoke-text:
	uv run python scripts/smoke_text.py
```

## API Contract

### HMAC Authentication

All internal endpoints require HMAC request signing.

Headers:

```text
X-Yral-Service: off-chain-agent
X-Yral-Timestamp: unix timestamp seconds
X-Yral-Nonce: unique nonce
X-Yral-Signature: hex(hmac_sha256(secret, canonical_request))
```

Canonical request:

```text
METHOD\nPATH\nTIMESTAMP\nNONCE\nSHA256(raw_body)
```

Validation:

- Reject missing headers.
- Reject unknown service name.
- Reject timestamps outside `AUTH_TIMESTAMP_SKEW_SECONDS`.
- Reject replayed nonce using KVRocks key `nsfw:auth_nonce:{service}:{nonce}` with TTL.
- Compare signatures using constant-time comparison.
- Secret lookup comes from typed config, not from route code.

### `POST /v1/videos/detect`

Main stateful video endpoint. It only validates, authenticates, and durably enqueues.

Request:

```json
{
  "job_id": "nsfw:<video_id>:<policy_version>:<source_object_version>",
  "video_id": "video-id",
  "publisher_user_id": "principal-or-user-id",
  "source_video_uri": "https://...",
  "post_id": "post-id-or-null",
  "canister_id": "canister-id-or-null",
  "source_object_version": "etag-or-empty-string",
  "upload_event_id": "event-id-or-null",
  "upload_created_at": "2026-06-05T00:00:00Z",
  "policy_version": "nsfw_policy_v1",
  "trace_id": "trace-id"
}
```

Response:

```json
{
  "job_id": "nsfw:video-id:nsfw_policy_v1:",
  "video_id": "video-id",
  "status": "queued",
  "trace_id": "trace-id"
}
```

HTTP status: `202 Accepted`.

Idempotency:

- If the same `job_id` is already queued/processing/classified, return `202` with the current status.
- If the same `video_id + source_object_version + policy_version` is already terminal, do not enqueue duplicate work.

### `GET /v1/videos/{video_id}/status`

Returns current job state and final result if present.

Statuses:

```text
queued
processing
classified
failed_retryable
failed_terminal
superseded
```

### Stateless APIs

- `POST /v1/images/detect-url`
- `POST /v1/images/detect-base64`
- `POST /v1/text/detect`

These endpoints call the model and return structured output. They do not write PostgreSQL or ClickHouse.

### Health APIs

- `GET /health`: liveness only.
- `GET /ready`: checks PostgreSQL, KVRocks, ClickHouse, GPU reachability if configured, and `ffmpeg`/`ffprobe` availability.

## Queue And Retry Design

Use KVRocks for the first implementation unless a stronger queue is introduced.

Preferred if supported by the deployed KVRocks version:

```text
Redis Streams + consumer group
stream: nsfw:queue:video_detection
consumer group: nsfw_video_workers
DLQ stream: nsfw:queue:video_detection:dlq
```

Fallback if streams are not available:

```text
nsfw:queue:video_detection             list or sorted set
nsfw:queue:video_detection:processing  processing lease set
nsfw:queue:video_detection:retry       retry sorted set by next_attempt_at
nsfw:queue:video_detection:dlq         dead-letter list
```

Retry behavior:

- The API returns `202` only after the job is durably enqueued.
- Worker attempts use exponential backoff with jitter.
- Retryable stages: download timeout, temporary storage 404, ffprobe timeout, ffmpeg transient failure, GPU timeout/5xx, malformed model batch response, PostgreSQL write failure, ClickHouse flush failure, Storj move failure.
- Non-retryable stages after validation: unsupported/corrupt video, no video stream, permanently unauthorized source URL.
- Store retry count and last error on the job state.
- Move exhausted jobs to DLQ.
- Never mark a failed or unclassifiable video as clean.

GPU model failure rule:

- Retry the failed model request or batch.
- Do not insert a per-frame model failure row into PostgreSQL.
- If model retries are exhausted, fail the worker attempt; the queue retry decides whether the whole job is retried or DLQed.

## Video Download And Storj Source Handling

The worker downloads the source URL directly. This is equivalent to the Rust pattern:

```rust
let response = reqwest::Client::new().get(&url).send().await?;
```

Python implementation shape:

```python
async def download_video(source_url: str, output_path: Path, settings: Settings) -> None:
    bytes_written = 0
    timeout = httpx.Timeout(settings.video_download_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", source_url) as response:
            response.raise_for_status()
            with output_path.open("wb") as file:
                async for chunk in response.aiter_bytes():
                    bytes_written += len(chunk)
                    if bytes_written > settings.video_max_bytes:
                        raise VideoTooLargeError(bytes_written)
                    file.write(chunk)
    if bytes_written == 0:
        raise EmptyVideoDownloadError()
```

Rules:

- Redact signed URLs from logs and Sentry.
- Enforce max bytes and timeout.
- Write to `/tmp/nsfw/<job_id>/source.mp4`.
- Clean up the temp directory in `finally`.
- Do not reconstruct Storj URLs in the worker if off-chain already sent a trusted source URL.

## Frame Extraction

Baseline extraction:

```text
ffmpeg -loglevel error -i source.mp4 -vf fps=1 -q:v 3 /tmp/nsfw/<job_id>/frames/frame-%06d.jpg
```

Rules:

- Run `ffprobe` first and store metadata.
- Extract one frame per second.
- Batch frames in groups of five for the GPU request.
- For the final short batch, send the actual count and require the model response count to match.
- Add frame dedupe/motion selection later only if GPU cost requires it. First production release should prefer recall over aggressive dropping.

## Structured Visual Prompt

The visual prompt is provisional until the final structured response prompt is provided. The service should isolate prompt text in `app/prompts/visual_batch_moderation_v1.txt` and keep `prompt_version` in config/data rows.

Refined batch prompt:

```text
You are an image moderation classifier.

You will receive N images from the same video, in order. N is between 1 and 5.
Analyze each image independently for unsafe or NSFW content.
Return only valid JSON. Do not explain outside JSON.
Return a JSON array with exactly N objects. The object at index 0 must describe image 0, index 1 must describe image 1, and so on.

Categories:
- safe
- suggestive
- nudity
- porn
- gore
- violence
- self_harm
- hate_or_extremism
- drugs
- unknown
- sexual_minor_content

Severity scale for unsafe categories:
0 = not present
1 = very mild or uncertain
2 = mild
3 = moderate
4 = strong
5 = explicit or severe

Rules:
- Do not over-classify. If visual evidence is weak, use a lower severity.
- If the image is unclear or ambiguous, use top_category "unknown".
- If multiple unsafe categories are present, score all relevant categories.
- Choose top_category based on the highest unsafe severity.
- If no unsafe category is visible, use top_category "safe", is_nsfw false, and overall_severity 0.
- If explicit sexual content involving a person who appears under 18 is present or suspected, set top_category "sexual_minor_content", is_nsfw true, and overall_severity 5.
- Keep reason short and factual.
- Return JSON only.

Each array item must use exactly this shape:
{
  "frame_index": 0,
  "top_category": "safe | suggestive | nudity | porn | gore | violence | self_harm | hate_or_extremism | drugs | unknown | sexual_minor_content",
  "is_nsfw": false,
  "overall_severity": 0,
  "categories": {
    "safe": 0,
    "suggestive": 0,
    "nudity": 0,
    "porn": 0,
    "gore": 0,
    "violence": 0,
    "self_harm": 0,
    "hate_or_extremism": 0,
    "drugs": 0,
    "unknown": 0,
    "sexual_minor_content": 0
  },
  "reason": "Short factual reason for the classification."
}
```

Validation:

- Response must parse as JSON.
- Top-level response must be an array.
- Array length must equal images sent.
- Each object must have the expected fields.
- Each category score must be an integer `0..5`.
- `frame_index` must map back to the input frame.
- Any parse/validation failure retries the same model request/batch.

## PostgreSQL Tables

Use PostgreSQL for jobs, frame-level successful model responses, video metadata, final result, and successful storage action details.

Provisioning status:

- Database `nsfw_detection` exists.
- User/owner `nsfw_detector` exists.
- The following tables have been created in schema `public` and are owned by `nsfw_detector`:
  - `nsfw_video_jobs`
  - `nsfw_frame_results`
  - `nsfw_video_results`
  - `nsfw_storage_actions`

### `nsfw_video_jobs`

```sql
CREATE TABLE nsfw_video_jobs (
    job_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    source_object_version TEXT NOT NULL DEFAULT '',
    policy_version TEXT NOT NULL,
    status TEXT NOT NULL,
    publisher_user_id TEXT NOT NULL,
    post_id TEXT,
    canister_id TEXT,
    source_video_uri TEXT NOT NULL,
    upload_event_id TEXT,
    trace_id TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    UNIQUE (video_id, source_object_version, policy_version)
);
```

### `nsfw_frame_results`

```sql
CREATE TABLE nsfw_frame_results (
    frame_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES nsfw_video_jobs(job_id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    frame_index INTEGER NOT NULL,
    frame_timestamp_seconds DOUBLE PRECISION NOT NULL,
    frame_hash TEXT,
    prompt_version TEXT NOT NULL,
    model_provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT,
    top_category TEXT NOT NULL,
    is_nsfw BOOLEAN NOT NULL,
    overall_severity SMALLINT NOT NULL CHECK (overall_severity BETWEEN 0 AND 5),
    safe_severity SMALLINT NOT NULL CHECK (safe_severity BETWEEN 0 AND 5),
    suggestive_severity SMALLINT NOT NULL CHECK (suggestive_severity BETWEEN 0 AND 5),
    nudity_severity SMALLINT NOT NULL CHECK (nudity_severity BETWEEN 0 AND 5),
    porn_severity SMALLINT NOT NULL CHECK (porn_severity BETWEEN 0 AND 5),
    gore_severity SMALLINT NOT NULL CHECK (gore_severity BETWEEN 0 AND 5),
    violence_severity SMALLINT NOT NULL CHECK (violence_severity BETWEEN 0 AND 5),
    self_harm_severity SMALLINT NOT NULL CHECK (self_harm_severity BETWEEN 0 AND 5),
    hate_or_extremism_severity SMALLINT NOT NULL CHECK (hate_or_extremism_severity BETWEEN 0 AND 5),
    drugs_severity SMALLINT NOT NULL CHECK (drugs_severity BETWEEN 0 AND 5),
    unknown_severity SMALLINT NOT NULL CHECK (unknown_severity BETWEEN 0 AND 5),
    sexual_minor_content_severity SMALLINT NOT NULL CHECK (sexual_minor_content_severity BETWEEN 0 AND 5),
    reason TEXT NOT NULL,
    raw_response JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, frame_index)
);
```

### `nsfw_video_results`

```sql
CREATE TABLE nsfw_video_results (
    job_id TEXT PRIMARY KEY REFERENCES nsfw_video_jobs(job_id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    aggregation_version TEXT NOT NULL,
    final_is_nsfw BOOLEAN NOT NULL,
    final_score DOUBLE PRECISION NOT NULL,
    final_top_category TEXT NOT NULL,
    max_overall_severity SMALLINT NOT NULL,
    nsfw_frame_count INTEGER NOT NULL,
    total_frame_count INTEGER NOT NULL,
    move_required BOOLEAN NOT NULL,
    move_threshold DOUBLE PRECISION NOT NULL,
    legacy_nsfw_ec TEXT NOT NULL,
    legacy_nsfw_gore TEXT NOT NULL,
    final_response JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `nsfw_storage_actions`

```sql
CREATE TABLE nsfw_storage_actions (
    action_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES nsfw_video_jobs(job_id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    publisher_user_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    final_score DOUBLE PRECISION NOT NULL,
    request_url TEXT NOT NULL,
    request_body JSONB NOT NULL,
    response_status INTEGER,
    response_body TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
```

Commit rules:

- Frame rows, final row, legacy mapping state, and storage action success row should be committed in one PostgreSQL transaction after classification and required Storj move succeeds.
- If required Storj move fails, rollback this transaction and let the queue retry.
- ClickHouse and KVRocks final writes happen only after this successful transaction.

## Hard Video Policy And Legacy Mapping

This section serves two purposes:

1. Derive the new canonical final video result.
2. Map that canonical result into the old `video_nsfw_agg` schema.

The old mapping is only for the legacy-compatible table. New readers should use the canonical ClickHouse table.

### Frame To Video Policy

Unsafe categories:

```text
suggestive
nudity
porn
gore
violence
self_harm
hate_or_extremism
drugs
sexual_minor_content
```

Rules:

- `frame_is_nsfw = model_response.is_nsfw OR top_category in unsafe_categories OR overall_severity >= 3`.
- `final_is_nsfw = any(frame_is_nsfw for all processed frames)`.
- `max_overall_severity = max(frame.overall_severity)`.
- `final_score = max_overall_severity / 5.0`.
- `final_top_category` is the top category of the frame with the highest severity. Tie-break by risk order: `sexual_minor_content`, `porn`, `nudity`, `gore`, `violence`, `self_harm`, `hate_or_extremism`, `drugs`, `suggestive`, `unknown`, `safe`.
- `move_required = final_score >= 0.8`.

This means one NSFW frame flags the whole video. No averaging is used to make a video safe.

### Legacy Field Mapping

Old-compatible ClickHouse table fields:

```text
video_id
gcs_video_id
nsfw_ec
nsfw_gore
is_nsfw
probability
```

`gcs_video_id` is nullable. New rows from the revamped pipeline should set it to `NULL` because the new flow no longer depends on GCS. Backfilled or historical rows can keep the old value, for example `gs://yral-videos/<video_id>.mp4`.

Mapper function:

```python
def to_legacy_nsfw_agg(
    result: VideoModerationResult,
    historical_gcs_video_id: str | None = None,
) -> LegacyNsfwAggRow:
    return LegacyNsfwAggRow(
        video_id=result.video_id,
        gcs_video_id=historical_gcs_video_id,
        nsfw_ec=map_legacy_nsfw_ec(result),
        nsfw_gore=map_legacy_nsfw_gore(result),
        is_nsfw=result.final_is_nsfw,
        probability=result.final_score,
    )
```

`nsfw_ec` mapping:

```text
final_top_category = porn -> explicit
final_top_category = nudity -> nudity
final_top_category = suggestive -> provocative
final_top_category = sexual_minor_content -> explicit
otherwise -> neutral
```

`nsfw_gore` mapping:

```text
gore severity >= 5 or violence severity >= 5 -> VERY_LIKELY
gore severity >= 4 or violence severity >= 4 -> LIKELY
gore severity >= 3 or violence severity >= 3 -> POSSIBLE
gore severity >= 1 or violence severity >= 1 -> UNLIKELY
otherwise -> VERY_UNLIKELY
```

## ClickHouse Tables In `yral`

Current provisioning target is the existing ClickHouse database `yral`. Because the `nsfw_detector` user currently has direct table grants and no confirmed cluster/macros are available to the service user, start with direct `ReplacingMergeTree` tables. If ClickHouse admin later confirms cluster/macros, migrate the DDL to local replicated tables plus distributed tables.

Provisioning status:

- `yral.video_nsfw_agg` has been created with `gcs_video_id Nullable(String)`.
- `yral.video_nsfw_detection` has been created with the canonical schema below.
- `yral.video_nsfw_storage_actions` has been created with the storage-action audit schema below.
- Both tables currently use direct `ReplacingMergeTree`, not replicated/distributed cluster tables.

### Canonical Final Table

Confirmed with `DESCRIBE TABLE yral.video_nsfw_detection`: 45 columns, types as shown below.

```sql
CREATE TABLE IF NOT EXISTS yral.video_nsfw_detection
(
    video_id String,
    job_id String,
    publisher_user_id String,
    post_id Nullable(String),
    canister_id Nullable(String),
    source_video_uri String,
    source_object_version String,
    upload_event_id Nullable(String),

    status LowCardinality(String),
    policy_version String,
    prompt_version String,
    aggregation_version String,
    model_provider LowCardinality(String),
    model_name String,
    model_version Nullable(String),

    duration_seconds Float32,
    frames_extracted UInt32,
    frames_processed UInt32,
    frame_batch_size UInt8,

    final_is_nsfw UInt8,
    final_score Float32,
    final_top_category LowCardinality(String),
    max_overall_severity UInt8,
    nsfw_frame_count UInt32,
    total_frame_count UInt32,

    max_suggestive_severity UInt8,
    max_nudity_severity UInt8,
    max_porn_severity UInt8,
    max_gore_severity UInt8,
    max_violence_severity UInt8,
    max_self_harm_severity UInt8,
    max_hate_or_extremism_severity UInt8,
    max_drugs_severity UInt8,
    max_unknown_severity UInt8,
    max_sexual_minor_content_severity UInt8,

    move_required UInt8,
    move_threshold Float32,
    storj_move_status LowCardinality(String),

    legacy_nsfw_ec LowCardinality(String),
    legacy_nsfw_gore LowCardinality(String),

    frame_results_json String,
    final_response_json String,

    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'),
    _updated_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(_updated_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY (video_id, policy_version, source_object_version);
```

### Old-Compatible `video_nsfw_agg` Table

This mirrors the old BigQuery schema shown for `yral_ds.video_nsfw_agg`, with one intentional change: `gcs_video_id` is nullable because new rows no longer come from the GCS-based pipeline.

```sql
CREATE TABLE IF NOT EXISTS yral.video_nsfw_agg
(
    video_id String,
    gcs_video_id Nullable(String),
    nsfw_ec Nullable(String),
    nsfw_gore Nullable(String),
    is_nsfw UInt8,
    probability Float32,
    created_at DateTime64(3, 'UTC') DEFAULT now64(3),
    updated_at DateTime64(3, 'UTC') DEFAULT now64(3),
    _updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_updated_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY video_id;
```

### Storage Move Detail Table

Confirmed with `DESCRIBE TABLE yral.video_nsfw_storage_actions`: 15 columns, types as shown below.

```sql
CREATE TABLE IF NOT EXISTS yral.video_nsfw_storage_actions
(
    action_id String,
    video_id String,
    job_id String,
    publisher_user_id String,
    action_type LowCardinality(String),
    threshold Float32,
    final_score Float32,
    status LowCardinality(String),
    request_url String,
    request_body_json String,
    response_status Nullable(UInt16),
    response_body String,
    created_at DateTime64(3, 'UTC'),
    completed_at Nullable(DateTime64(3, 'UTC')),
    _updated_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(_updated_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY (video_id, job_id, action_id);
```

## Storj Move Integration

Move videos through the existing external service, not by talking to Storj directly.

Endpoint:

```text
POST {STORJ_INTERFACE_URL}/move-to-nsfw
Authorization: Bearer {STORJ_INTERFACE_TOKEN}
Body: {"publisher_user_id": "...", "video_id": "..."}
```

Python client shape:

```python
class StorjInterfaceClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http_client = http_client

    async def move_to_nsfw(self, publisher_user_id: str, video_id: str) -> StorjMoveResponse:
        url = f"{self._settings.storj_interface_url.rstrip('/')}/move-to-nsfw"
        response = await self._http_client.post(
            url,
            json={
                "publisher_user_id": publisher_user_id,
                "video_id": video_id,
            },
            headers={"Authorization": f"Bearer {self._settings.storj_interface_token}"},
            timeout=self._settings.storj_interface_timeout_seconds,
        )
        response.raise_for_status()
        return StorjMoveResponse(
            status_code=response.status_code,
            body=response.text,
        )
```

Rules:

- Only call when `move_required = true` (`final_score >= 0.8`).
- Move uses `publisher_user_id` and `video_id`; it does not use the public MP4 URL.
- The endpoint should be idempotent. If it returns an "already moved" success, treat it as success.
- If move fails, rollback final PostgreSQL writes for that attempt, do not write ClickHouse/KVRocks final state, and let the queue retry.
- Off-chain must remove its old `move2_nsfw_buckets_if_required` call after REST cutover to avoid duplicate moves.

## Worker Transaction And Publish Ordering

Worker stages:

1. Claim job and mark `processing`.
2. Download video.
3. Probe/extract frames.
4. Call GPU model batches and retry malformed/failed batches.
5. Build in-memory frame results and final result.
6. If `move_required`, call Storj interface.
7. Start PostgreSQL unit of work.
8. Insert frame rows, video metadata, final result, and storage action success row.
9. Commit PostgreSQL.
10. Push final row and legacy row to KVRocks ClickHouse buffer.
11. Write `offchain:video_nsfw:{video_id}` runtime compatibility key.
12. Mark job `classified`.

Rollback rules:

- If Storj move fails, no final PostgreSQL transaction is committed and no ClickHouse/KVRocks final state is written.
- If PostgreSQL commit fails, no ClickHouse/KVRocks final state is written; queue retries.
- If ClickHouse flush fails after PostgreSQL commit, keep the rows in KVRocks buffer and retry flush. PostgreSQL remains canonical for that worker output.
- If KVRocks runtime key write fails after PostgreSQL commit, retry that side effect; do not re-run GPU work unless needed.

## KVRocks Usage

Keys:

```text
nsfw:auth_nonce:{service}:{nonce}
nsfw:queue:video_detection
nsfw:queue:video_detection:processing
nsfw:queue:video_detection:retry
nsfw:queue:video_detection:dlq
nsfw:gpu:inflight
nsfw:clickhouse_buffer:video_results
nsfw:clickhouse_buffer:legacy_nsfw_agg
nsfw:clickhouse_buffer:storage_actions
offchain:video_nsfw:{video_id}
```

ClickHouse buffer flush:

- Flush when buffer reaches 50 processed videos.
- Also flush on interval, for example every 30 seconds.
- Remove buffered rows only after insert succeeds.
- Use `ReplacingMergeTree(_updated_at)` to make duplicate flushes safe.

## Off-Chain Migration

Off-chain changes:

- Add feature flag, for example `NSFW_DETECT_REST_ENABLED`.
- Add REST client that signs requests with HMAC.
- Send `source_video_uri`, `publisher_user_id`, `video_id`, `post_id`, `canister_id`, `policy_version`, and `trace_id`.
- Stop using gRPC `NsfwDetectorClient` on the new path.
- Stop calling old frame extraction/GCS upload jobs on the new path.
- Stop calling `move2_nsfw_buckets_if_required` after `nsfw_detect` owns storage movement.
- Keep `/api/v2/posts/nsfw_prob/{video_id}` working by reading KVRocks key written by the new worker.

## Coding Agent Guardrails

These rules are for humans and coding agents implementing the plan. They are meant to prevent invented contracts, schema drift, and accidental legacy behavior.

Do not invent missing contracts:

- Do not invent env var names. Read `app/config/settings.py`, `.env`, and `.env.offchain-fetched`, then add a typed setting only when the var is present or explicitly approved.
- Do not invent ClickHouse cluster names, database names, table names, or macros. Keep `{cluster}`, `{shard}`, and `{replica}` placeholders until the real values are confirmed.
- Do not invent the final model response schema. Keep the parser tied to the prompt version and tests. If the prompt changes, update `schemas/model_output.py` and parser tests in the same phase.
- Do not invent BigQuery writes. The old BigQuery table is not an online write target for this service.
- Do not invent a separate frame-detail ClickHouse table. Frame-level data stays in PostgreSQL unless the plan is explicitly changed.
- Do not call Storj directly. Storage movement only goes through `storj-interface`.
- Do not lower the Storj move threshold from `0.8` unless policy is explicitly changed.
- Do not average frame scores to make a video safe. One NSFW frame flags the whole video.
- Do not store per-frame model failures in PostgreSQL. Retry the failed model request/batch.
- Do not publish final ClickHouse/KVRocks rows before required Storj movement succeeds.
- Do not import from `app/legacy/` in new production modules unless the import is behind an explicit compatibility flag.

Before coding any phase:

- Read the current `plan.md` section for that phase.
- Inspect existing code in the files being touched.
- Add or update tests for the phase before claiming it complete.
- Run the phase test set plus `make lint` or the equivalent `uv run ruff check`.
- If a required external contract is unknown, leave a typed interface and fake in tests rather than guessing live behavior.

When adding abstractions:

- Use base classes only for shared session/client/logger plumbing.
- Prefer explicit repository methods over generic CRUD if behavior is domain-specific.
- Keep routes thin, services orchestration-focused, repositories persistence-focused, and clients protocol-focused.

## Phase Testing Standard

Every phase must include:

1. Unit tests for the new logic added in that phase.
2. A phase integration test that exercises the phase through the highest practical boundary.
3. Regression tests for any old behavior intentionally preserved.
4. Negative tests for failure paths, not only happy paths.
5. A short completion note listing commands run and any known gaps.

Do not add full testing code into this plan. The plan defines what tests must cover.

## Implementation Phases

### Phase 0: Finalize Schema Inputs

Scope:

- Confirm final structured visual batch prompt.
- Confirm exact model response shape after prompt testing.
- Confirm ClickHouse cluster name/macros and table naming.
- Confirm max video size/duration.
- Confirm whether KVRocks Redis Streams are available. If not, choose QStash or the documented fallback before implementing queue code.

Agent guardrails:

- Do not generate production parser logic from an untested prompt.
- Do not replace schema placeholders with guessed ClickHouse values.
- Do not use real `.env` secrets in test fixtures or docs.

Unit tests:

- Prompt fixture validation: example model responses parse against the provisional schema.
- Settings validation: required env vars fail fast when missing, optional vars use documented defaults.
- ClickHouse DDL rendering: placeholders remain placeholders unless real config is provided.

Phase integration test:

- Load settings from a test env file, load prompt fixture, parse sample 1-frame and 5-frame model responses, and render ClickHouse DDL without contacting external services.

Exit criteria:

- Final/temporary prompt version is named.
- Schema uncertainty is documented in `Remaining Open Items`.
- Test fixtures exist for safe, NSFW, malformed, and 5-frame batch responses.

### Phase 1: Project Skeleton And Legacy Isolation

Scope:

- Add new `app/` structure.
- Move current gRPC and old pipeline code into `app/legacy/`.
- Add typed config loading from env.
- Add Makefile and `uv` setup.
- Add FastAPI app, router, middleware, and error handling shell.

Agent guardrails:

- Do not rewrite legacy code while moving it.
- Do not delete generated gRPC files in this phase unless a rollback decision has been made.
- Do not add business logic into route files.
- Do not make old gRPC imports available from new services.

Unit tests:

- App imports without importing `app/legacy/` modules.
- Settings object loads from test env and redacts secrets in repr/log output.
- Error classes map to stable error codes.
- Router registration includes expected v1 route modules.

Phase integration test:

- Start FastAPI test client and call `/health` and `/ready` with fake dependency checks. `/health` should work without external dependencies; `/ready` should report dependency readiness from fakes.

Exit criteria:

- `make lint`, `make test-unit`, and the phase integration test pass.
- Legacy files are isolated under `app/legacy/`.
- New code has no accidental import from legacy modules.

### Phase 2: Auth, Queue, And API

Scope:

- Implement HMAC middleware/dependency.
- Implement KVRocks nonce replay protection.
- Implement durable queue repository/service.
- Implement `POST /v1/videos/detect` returning `202` after durable enqueue.
- Implement status, health, and readiness endpoints.

Agent guardrails:

- Do not accept unsigned requests.
- Do not enqueue before validating HMAC and request schema.
- Do not return `200` for the video enqueue endpoint.
- Do not hand-roll a list-based queue if KVRocks Streams are available.
- Do not make off-chain wait for classification in this endpoint.

Unit tests:

- HMAC canonical string generation.
- Valid signature accepted.
- Wrong signature rejected.
- Missing signature headers rejected.
- Expired timestamp rejected.
- Future timestamp rejected.
- Replayed nonce rejected.
- Nonce TTL is set.
- Video request schema rejects missing `video_id`, `publisher_user_id`, and `source_video_uri`.
- Queue service deduplicates existing `job_id`.
- Queue service schedules retry with increasing backoff.
- Status endpoint maps queued/processing/classified/failed states correctly.

Phase integration test:

- Use FastAPI test client with fake KVRocks. Submit a signed `POST /v1/videos/detect`; assert `202`, one durable queue item, nonce stored, and no worker/classification side effects.
- Repeat the same request; assert idempotent response and no duplicate queue item.

Exit criteria:

- Auth, API, and queue tests pass.
- The route can be exercised without PostgreSQL, ClickHouse, GPU, or Storj.

### Phase 3: PostgreSQL And ClickHouse Foundations

Scope:

- Add Alembic migrations for PostgreSQL tables.
- Add ClickHouse DDL scripts for the 3-node cluster tables.
- Add repositories and unit-of-work.
- Add ClickHouse buffer flush worker.

Agent guardrails:

- Do not store frame-level data in ClickHouse.
- Do not write old BigQuery tables.
- Do not flush final ClickHouse rows before the PostgreSQL unit of work has committed.
- Do not change old-compatible table columns away from `video_id`, `gcs_video_id`, `nsfw_ec`, `nsfw_gore`, `is_nsfw`, `probability` without explicit approval.

Unit tests:

- Alembic metadata includes all required PostgreSQL tables.
- `nsfw_frame_results` enforces one row per `job_id + frame_index`.
- Unit of work commits on success and rolls back on exception.
- PostgreSQL repositories serialize/deserialize video jobs, frame rows, final rows, and storage action rows.
- ClickHouse canonical row serialization includes all required fields.
- ClickHouse legacy row serialization matches old-compatible schema.
- ClickHouse storage action row serialization includes request/response fields.
- Buffer repository keeps rows until flush success.
- Flush worker removes rows only after successful insert.
- Duplicate flush rows remain safe with `_updated_at` semantics.

Phase integration test:

- Apply Alembic migrations to a test PostgreSQL database or isolated test container/fake if DB is unavailable.
- Insert a job, frame rows, final result, and storage action inside a unit of work; force an exception and verify rollback; then run a success path and verify committed rows.
- Run ClickHouse flush service against fake ClickHouse client and assert canonical, legacy, and storage-action inserts are called with expected rows.

Exit criteria:

- Database migrations are reversible in test.
- Repository tests cover commit and rollback.
- No service imports concrete database clients directly; they go through repositories/unit of work.

### Phase 4: Video Processing Worker

Scope:

- Implement source video download.
- Implement `ffprobe` metadata parsing.
- Implement `ffmpeg` one-frame-per-second extraction.
- Implement frame batching in groups of five.
- Implement temp cleanup.

Agent guardrails:

- Do not log signed source URLs.
- Do not reconstruct Storj URL if `source_video_uri` was provided.
- Do not skip `ffprobe` validation.
- Do not leave temp files after success or failure.
- Do not silently mark invalid videos as clean.

Unit tests:

- Download uses HTTP GET and streams to disk.
- Download enforces max bytes.
- Download rejects empty body.
- Download redacts URL in logged errors.
- `ffprobe` parser extracts duration, width, height, fps, codec, and stream presence.
- Invalid/no-video stream produces terminal validation error.
- FFmpeg command uses `fps=1`.
- Frame batching creates groups of five and preserves final short batch.
- Frame timestamps map to frame indexes.
- Temp directory cleanup runs on success, download failure, probe failure, and extraction failure.

Phase integration test:

- Generate or use a tiny fixture video. Run probe/extract/batch end to end without GPU. Assert expected frame count range, batch sizes, metadata fields, and temp cleanup.

Exit criteria:

- Worker can process video bytes up to frame batches with no external model/database dependency.
- Failure modes are classified as retryable vs terminal.

### Phase 5: GPU Moderation And Prompt Validation

Scope:

- Implement OpenAI-compatible GPU client.
- Implement request concurrency limit of 5.
- Implement batch response parser and validation.
- Retry malformed/failed batch responses.
- Add stateless image/text endpoints once the prompt schema is stable.

Agent guardrails:

- Do not assume the GPU response is valid JSON.
- Do not accept a response array with the wrong length.
- Do not accept category severities outside `0..5`.
- Do not store failed frame model responses in PostgreSQL.
- Do not exceed five concurrent GPU requests across active workers.
- Do not let image/text stateless endpoints write PostgreSQL or ClickHouse.

Unit tests:

- GPU client sends image batches with 1, 5, and final-short-batch counts.
- Parser accepts valid 1-frame and 5-frame JSON arrays.
- Parser rejects non-JSON response.
- Parser rejects wrong array length.
- Parser rejects missing fields.
- Parser rejects unknown `top_category`.
- Parser rejects out-of-range severity.
- Retry wrapper retries malformed JSON and transient 5xx/timeout.
- Retry wrapper stops after max attempts.
- Concurrency limiter caps in-flight GPU calls at 5.
- Image URL endpoint returns structured response with fake GPU client and no DB calls.
- Base64 image endpoint validates size/type and returns structured response.
- Text endpoint uses text prompt path, not visual prompt path.

Phase integration test:

- Run frame batches from Phase 4 through a fake GPU server/client that returns a mix of safe and unsafe valid responses. Assert parsed frame results preserve frame order and no PostgreSQL writes happen in this phase unless the worker persistence path is explicitly enabled.
- Run malformed response then valid retry and assert the batch succeeds after retry.

Exit criteria:

- GPU moderation service can process batches deterministically with fakes.
- Parser tests are tied to prompt version.
- Stateless endpoints are tested independently from video persistence.

### Phase 6: Final Policy, Legacy Mapping, And Storage Move

Scope:

- Implement any-frame NSFW policy.
- Implement final result schema.
- Implement legacy `video_nsfw_agg` mapper.
- Implement Storj `/move-to-nsfw` client.
- Enforce `final_score >= 0.8` move threshold.
- Enforce rollback/no-final-publish on required move failure.

Agent guardrails:

- Do not average frames for final safety.
- Do not use `0.4` for Storj movement.
- Do not publish ClickHouse/KVRocks final rows before a required move succeeds.
- Do not treat Storj move failure as classified success.
- Do not call `storj-interface` without bearer auth.
- Do not expose `STORJ_INTERFACE_TOKEN` in logs, Sentry, or tests.

Unit tests:

- One safe frame produces `final_is_nsfw=false`, `final_score=0.0`.
- One NSFW frame among many safe frames produces `final_is_nsfw=true`.
- Severity `4` produces `final_score=0.8` and `move_required=true`.
- Severity `3` flags NSFW but does not require move.
- Tie-break order picks higher-risk category.
- `sexual_minor_content` always maps to highest-risk final category.
- Legacy mapper emits `video_id`, `gcs_video_id`, `nsfw_ec`, `nsfw_gore`, `is_nsfw`, `probability`.
- Legacy `nsfw_ec` mapping covers `porn`, `nudity`, `suggestive`, `sexual_minor_content`, and neutral categories.
- Legacy `nsfw_gore` mapping covers severity bands.
- Storj client sends `publisher_user_id` and `video_id` JSON body.
- Storj client sends bearer token.
- Storj client handles 2xx success and non-2xx failure.
- Required move failure raises a worker-attempt failure before final publish.

Phase integration test:

- Full worker orchestration with fake download/extract/GPU/PostgreSQL/Storj/ClickHouse/KVRocks:
  - Safe video: no Storj move, PostgreSQL commit, ClickHouse/KVRocks final publish.
  - NSFW severity 4 video: Storj move succeeds, PostgreSQL commit, ClickHouse/KVRocks publish.
  - NSFW severity 4 video with Storj failure: PostgreSQL final transaction rolls back, no ClickHouse/KVRocks final rows, job scheduled for retry.

Exit criteria:

- Final policy tests prove one-frame flagging.
- Rollback tests prove no final publish after required move failure.

### Phase 7: Shadow Mode

Scope:

- Enable off-chain REST path behind feature flag for shadow jobs.
- Write new PostgreSQL/ClickHouse results, but initially keep old user-facing behavior if needed.
- Compare old and new score bands.
- Review disagreements.

Agent guardrails:

- Do not disable old path during shadow.
- Do not move buckets from shadow results unless the storage-move flag is explicitly enabled.
- Do not treat disagreement metrics as policy changes without review.
- Do not break `/api/v2/posts/nsfw_prob/{video_id}` during shadow.

Unit tests:

- Feature flag disabled uses old path.
- Feature flag enabled sends signed REST request.
- Shadow mode suppresses storage move if configured.
- Shadow result comparison groups scores into safe, NSFW, and move bands.
- Disagreement logger redacts URLs and tokens.

Phase integration test:

- Off-chain signed request fixture calls NSFW API with REST flag enabled and fake queue. Assert request shape, HMAC headers, `202` response handling, and old path remains available when flag is disabled.
- Shadow comparison service ingests fake old/new results and produces disagreement metrics.

Exit criteria:

- Feature flag can switch paths safely.
- Shadow metrics are available before cutover.

### Phase 8: Cutover

Scope:

- Enable KVRocks runtime compatibility writes from the new worker.
- Enable Storj move from the new worker.
- Disable old gRPC NSFW path in off-chain.
- Disable old Storj move path in off-chain.

Agent guardrails:

- Do not allow both old and new Storj move paths to run for the same upload.
- Do not remove rollback flags until production metrics are stable.
- Do not delete legacy code during cutover.
- Do not change thresholds during cutover.

Unit tests:

- Cutover config enables REST and disables gRPC client.
- Off-chain does not call old `move2_nsfw_buckets_if_required` when new path is enabled.
- KVRocks runtime key shape matches existing `offchain:video_nsfw:{video_id}` reader expectations.
- Rollback config can re-enable old path.

Phase integration test:

- End-to-end fake cutover flow: off-chain REST enqueue, worker classification, optional Storj move, PostgreSQL commit, ClickHouse buffers, KVRocks runtime key, and status endpoint result.
- Verify no old gRPC/storj-move calls are made in the fake call graph.

Exit criteria:

- New path handles the complete production flow in tests.
- Rollback switch is tested.

### Phase 9: Cleanup

Scope:

- Remove legacy imports from new code.
- Delete or archive old gRPC server after rollback window.
- Update README with REST API, Makefile, env vars, queue behavior, and deployment instructions.

Agent guardrails:

- Do not delete legacy code before rollback window has passed.
- Do not remove old env vars until deployment configs are updated.
- Do not remove tests for compatibility key/table while downstream readers still depend on them.

Unit tests:

- Import scan proves new modules do not import `app/legacy/`.
- README smoke commands match Makefile targets.
- Removed env vars are no longer required by settings.
- Compatibility table/key tests remain until readers migrate.

Phase integration test:

- Fresh checkout style smoke: install deps, run lint, run unit tests, start API with fake deps, run worker dry-run or fake-worker test, and run documented smoke scripts against fakes.

Exit criteria:

- Documentation matches code.
- Legacy code is either archived or isolated with no production imports.
- All phase tests and regression tests pass.

## Cross-Phase Test Matrix

Use this matrix to avoid gaps:

- Auth: valid signature, invalid signature, missing headers, replayed nonce, clock skew.
- Queue: enqueue, idempotency, claim, ack, retry, backoff, DLQ.
- Video I/O: valid download, empty download, over-size download, timeout, redacted errors.
- FFmpeg: valid extraction, no-video stream, corrupt video, final short frame batch.
- GPU: valid batch, malformed JSON, wrong count, timeout, retry success, retry exhaustion, concurrency cap.
- Policy: all safe, one NSFW frame, severity thresholds, category tie-break, sexual minor escalation.
- Persistence: PostgreSQL commit, PostgreSQL rollback, ClickHouse serialization, KVRocks buffer retention on flush failure.
- Storage move: no move below `0.8`, move at `0.8`, move success, move failure rollback, bearer auth.
- Compatibility: old `video_nsfw_agg` row shape, KVRocks runtime key shape, off-chain status/read behavior.
- Observability: trace/job/video IDs in logs, URL/token redaction, Sentry tags without secrets.
- Cutover: feature flag disabled, feature flag enabled, rollback, no duplicate storage moves.

## Required Commands Per Phase

At minimum, each phase completion should run:

```text
make lint
make test-unit
make test-integration
```

If the phase touches database migrations or ClickHouse DDL, also run:

```text
make db-upgrade
make ch-ddl
```

If the phase touches API or worker runtime behavior, also run the relevant smoke target against fakes:

```text
make smoke-video
make smoke-image
make smoke-text
```

## Remaining Open Items

1. Final structured visual prompt and exact response schema after model testing.
2. Exact ClickHouse cluster name and macro/table naming convention for the self-hosted 3-node cluster.
3. Whether failed Storj move attempts should be persisted as audit rows despite the rollback requirement. The current plan persists only successful move details in final DB state and relies on logs/Sentry/DLQ for failed attempts.



   ┌─name───────────────────────┬─engine─────────────┬─sorting_key─────────────────────────────────────┬─partition_key────────┐
1. │ video_nsfw_agg             │ ReplacingMergeTree │ video_id                                        │ toYYYYMM(created_at) │
2. │ video_nsfw_detection       │ ReplacingMergeTree │ video_id, policy_version, source_object_version │ toYYYYMM(created_at) │
3. │ video_nsfw_storage_actions │ ReplacingMergeTree │ video_id, job_id, action_id                     │ toYYYYMM(created_at) │
   └────────────────────────────┴────────────────────┴─────────────────────────────────────────────────┴──────────────────────┘

