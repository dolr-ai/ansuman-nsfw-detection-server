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

