from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "yral-nsfw-detector"
    environment: str = "local"

    internal_request_hmac_secret: SecretStr | None = Field(
        default=None,
        repr=False,
        alias="INTERNAL_REQUEST_HMAC_SECRET",
    )
    internal_request_max_skew_sec: int = Field(
        default=300,
        alias="INTERNAL_REQUEST_MAX_SKEW_SEC",
    )

    postgres_database_url: SecretStr | None = Field(default=None, repr=False, alias="POSTGRES_DATABASE_URL")

    kvrocks_host: str | None = Field(default=None, alias="KVROCKS_HOST")
    kvrocks_port: int = Field(default=6379, alias="KVROCKS_PORT")
    kvrocks_password: SecretStr | None = Field(default=None, repr=False, alias="KVROCKS_PASSWORD")
    kvrocks_tls_enabled: bool = Field(default=False, alias="KVROCKS_TLS_ENABLED")
    kvrocks_cluster_enabled: bool = Field(default=True, alias="KVROCKS_CLUSTER_ENABLED")
    kvrocks_max_connections: int = Field(default=500, alias="KVROCKS_MAX_CONNECTIONS")
    kvrocks_socket_timeout_seconds: float = Field(default=5.0, alias="KVROCKS_SOCKET_TIMEOUT_SECONDS")
    kvrocks_socket_connect_timeout_seconds: float = Field(default=5.0, alias="KVROCKS_SOCKET_CONNECT_TIMEOUT_SECONDS")
    kvrocks_health_check_interval_seconds: int = Field(default=30, alias="KVROCKS_HEALTH_CHECK_INTERVAL_SECONDS")
    kvrocks_ssl_ca_cert: str | None = Field(default=None, alias="KVROCKS_SSL_CA_CERT")
    kvrocks_ssl_client_cert: str | None = Field(default=None, alias="KVROCKS_SSL_CLIENT_CERT")
    kvrocks_ssl_client_key: str | None = Field(default=None, alias="KVROCKS_SSL_CLIENT_KEY")

    clickhouse_primary_database_url: SecretStr | None = Field(
        default=None, repr=False, alias="CLICKHOUSE_PRIMARY_DATABASE_URL"
    )
    clickhouse_secondary_database_url: SecretStr | None = Field(
        default=None, repr=False, alias="CLICKHOUSE_SECONDARY_DATABASE_URL"
    )
    clickhouse_secure: bool = Field(default=True, alias="CLICKHOUSE_SECURE")
    clickhouse_verify: bool = Field(default=True, alias="CLICKHOUSE_VERIFY")
    clickhouse_database: str = Field(default="yral", alias="CLICKHOUSE_DATABASE")
    clickhouse_user: SecretStr | None = Field(default=None, repr=False, alias="CLICKHOUSE_USER")
    clickhouse_password: SecretStr | None = Field(default=None, repr=False, alias="CLICKHOUSE_PASSWORD")
    clickhouse_nsfw_table: str = Field(default="video_nsfw_detection", alias="CLICKHOUSE_NSFW_TABLE")
    clickhouse_nsfw_agg_table: str = Field(default="video_nsfw_agg", alias="CLICKHOUSE_NSFW_AGG_TABLE")
    clickhouse_excluded_videos_table: str = Field(default="excluded_videos", alias="CLICKHOUSE_EXCLUDED_VIDEOS_TABLE")
    clickhouse_storage_actions_table: str = "video_nsfw_storage_actions"

    storj_interface_url: str | None = Field(default=None, alias="STORJ_INTERFACE_URL")
    storj_interface_token: SecretStr | None = Field(default=None, repr=False, alias="STORJ_INTERFACE_TOKEN")
    storj_interface_timeout_seconds: float = 10.0

    api_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("API_BASE_URL", "API_BASE_URL "),
    )
    api_key: SecretStr | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("API_KEY", "API_KEY "),
    )
    model_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MODEL_NAME", "MODEL_NAME "),
    )
    model_provider: str = "openai-compatible"
    model_version: str | None = None

    sentry_dsn: SecretStr | None = Field(default=None, repr=False, alias="SENTRY_DSN")
    sentry_send_default_pii: bool = Field(default=False, alias="SENTRY_SEND_DEFAULT_PII")

    default_policy_version: str = "nsfw_policy_v1"
    visual_prompt_version: str = "visual_batch_moderation_v1"
    image_prompt_version: str = "image_generation_moderation_v1"
    image_text_prompt_version: str = "image_prompt_generation_moderation_v1"
    text_prompt_version: str = "text_moderation_v1"
    aggregation_version: str = "hard_any_frame_v1"
    frame_batch_size: int = 5
    gpu_max_concurrency: int = 5
    gpu_max_attempts: int = 3
    gpu_retry_base_delay_seconds: float = Field(default=0.25, alias="GPU_RETRY_BASE_DELAY_SECONDS")
    image_max_bytes: int = 10 * 1024 * 1024
    image_download_timeout_seconds: float = Field(default=30.0, alias="IMAGE_DOWNLOAD_TIMEOUT_SECONDS")
    image_download_max_attempts: int = Field(default=3, alias="IMAGE_DOWNLOAD_MAX_ATTEMPTS")
    image_download_retry_base_delay_seconds: float = Field(
        default=0.5,
        alias="IMAGE_DOWNLOAD_RETRY_BASE_DELAY_SECONDS",
    )

    video_download_timeout_seconds: float = 120.0
    video_max_bytes: int = 512 * 1024 * 1024
    video_temp_root: str = "/tmp/nsfw"
    ffprobe_timeout_seconds: float = 30.0
    ffmpeg_timeout_seconds: float = 300.0
    move_threshold: float = 0.8

    queue_stream_name: str = "nsfw:queue:video_detection"
    queue_group_name: str = "nsfw_video_workers"
    queue_consumer_name: str | None = Field(default=None, alias="QUEUE_CONSUMER_NAME")
    queue_read_count: int = Field(default=1, alias="QUEUE_READ_COUNT")
    queue_block_ms: int = Field(default=5000, alias="QUEUE_BLOCK_MS")
    queue_max_attempts: int = Field(default=3, alias="QUEUE_MAX_ATTEMPTS")
    queue_dlq_stream_name: str = "nsfw:queue:video_detection:dlq"
    clickhouse_buffer_video_results_key: str = "nsfw:clickhouse_buffer:video_results"
    clickhouse_buffer_legacy_key: str = "nsfw:clickhouse_buffer:legacy_nsfw_agg"
    clickhouse_buffer_storage_actions_key: str = "nsfw:clickhouse_buffer:storage_actions"
    runtime_nsfw_key_prefix: str = "offchain:video_nsfw:"

    def internal_request_secret(self) -> str | None:
        if self.internal_request_hmac_secret is None:
            return None
        return self.internal_request_hmac_secret.get_secret_value()

    def is_kvrocks_configured(self) -> bool:
        return bool(self.kvrocks_host)

    def is_gpu_configured(self) -> bool:
        return bool(self.api_base_url and self.api_key and self.model_name)

    def is_clickhouse_configured(self) -> bool:
        return bool(self.clickhouse_primary_database_url)

    def is_postgres_configured(self) -> bool:
        return bool(self.postgres_database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_from_mapping(values: dict[str, Any]) -> Settings:
    return Settings.model_validate(values)
