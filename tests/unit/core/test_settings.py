from pydantic import SecretStr

from app.config.settings import Settings


def test_settings_reads_internal_hmac_secret() -> None:
    settings = Settings(_env_file=None, INTERNAL_REQUEST_HMAC_SECRET=SecretStr("internal-token"))

    assert settings.internal_request_secret() == "internal-token"


def test_settings_repr_redacts_secrets() -> None:
    settings = Settings(
        _env_file=None,
        internal_request_hmac_secret=SecretStr("secret-value"),
        api_key=SecretStr("gpu-secret"),
    )

    rendered = repr(settings)

    assert "secret-value" not in rendered
    assert "gpu-secret" not in rendered


def test_settings_reads_kvrocks_pool_options() -> None:
    settings = Settings(
        _env_file=None,
        KVROCKS_MAX_CONNECTIONS=750,
        KVROCKS_POOL_MAX_ATTEMPTS=4,
        KVROCKS_POOL_RETRY_BASE_DELAY_SECONDS=0.1,
        KVROCKS_SOCKET_TIMEOUT_SECONDS=3.5,
        KVROCKS_SOCKET_CONNECT_TIMEOUT_SECONDS=1.5,
        KVROCKS_HEALTH_CHECK_INTERVAL_SECONDS=10,
    )

    assert settings.kvrocks_max_connections == 750
    assert settings.kvrocks_pool_max_attempts == 4
    assert settings.kvrocks_pool_retry_base_delay_seconds == 0.1
    assert settings.kvrocks_socket_timeout_seconds == 3.5
    assert settings.kvrocks_socket_connect_timeout_seconds == 1.5
    assert settings.kvrocks_health_check_interval_seconds == 10
