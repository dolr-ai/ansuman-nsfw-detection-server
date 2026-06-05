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

All `/v1` endpoints require HMAC headers:

```text
X-Yral-Service: off-chain-agent
X-Yral-Timestamp: unix timestamp seconds
X-Yral-Nonce: unique nonce
X-Yral-Signature: hex(hmac_sha256(secret, canonical_request))
```

Canonical request:

```text
METHOD
PATH
TIMESTAMP
NONCE
SHA256(raw_body)
```

The first implementation uses KVRocks/Redis for nonce replay protection and
durable video enqueue when KVRocks env vars are configured. Tests use in-memory
repositories through the same interfaces.

## Legacy

The previous gRPC service and old GCS/BigQuery pipeline code live under
`app/legacy/`. New production modules must not import from `app/legacy/`.
