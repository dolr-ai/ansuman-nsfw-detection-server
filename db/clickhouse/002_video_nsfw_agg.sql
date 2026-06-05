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

