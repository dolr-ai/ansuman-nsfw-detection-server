# yral-nsfw-detector

Internal NSFW detection service for Yral. The current branch is migrating the old
gRPC pipeline into `app/legacy/` and adding a FastAPI REST API plus worker
foundation.

## Development

```bash
uv sync
make run
make worker
make flush-worker
make lint
make test
```

The REST API runs on `PORT` or `8080` by default.

## REST API

Liveness:

```text
GET /health
```

Readiness:

```text
GET /ready
```

Video enqueue:

```text
POST /v1/videos/detect
```

Video status:

```text
GET /v1/videos/{video_id}/status
```

Manual human-approved ban:

```text
POST /v1/videos/{video_id}/ban
```

`/v1/videos/{video_id}/ban` writes `yral.excluded_videos` and the legacy
`yral.video_nsfw_agg` compatibility row synchronously. It does not enqueue video
processing and does not write classifier rows to `yral.video_nsfw_detection`.

All `/v1` endpoints require internal HMAC headers:

```text
X-Internal-Timestamp: unix timestamp seconds
X-Internal-Signature: hex(hmac_sha256(secret, signature_message))
```

Signature message:

```text
TIMESTAMP
METHOD
PATH
SHA256(raw_body)
```

`SHA256(raw_body)` is computed over the exact HTTP request bytes sent on the
wire. JSON whitespace and key order therefore matter to the signature. For
`GET /v1/videos/{video_id}/status`, sign the SHA256 of an empty body.

This auth is intentionally stateless. A captured request can be replayed inside
the timestamp skew window, so callers should keep `/v1` on the internal network
and use short skew values where possible.

Configure the shared secret with `INTERNAL_REQUEST_HMAC_SECRET`.

KVRocks/Redis is used for durable video enqueue when KVRocks env vars are
configured. It is not used for HMAC nonce storage. Tests use in-memory
repositories through the same interfaces.

Useful KVRocks/Redis pool knobs:

```text
KVROCKS_MAX_CONNECTIONS=500
KVROCKS_POOL_MAX_ATTEMPTS=3
KVROCKS_POOL_RETRY_BASE_DELAY_SECONDS=0.05
KVROCKS_SOCKET_TIMEOUT_SECONDS=5
KVROCKS_SOCKET_CONNECT_TIMEOUT_SECONDS=5
KVROCKS_HEALTH_CHECK_INTERVAL_SECONDS=30
```

Manual ban writes use these ClickHouse table env vars:

```text
CLICKHOUSE_EXCLUDED_VIDEOS_TABLE=excluded_videos
CLICKHOUSE_NSFW_AGG_TABLE=video_nsfw_agg
```

## Legacy

The previous gRPC service and old GCS/BigQuery pipeline are not part of the new
REST path. New production modules must not import from `app/legacy/`.
