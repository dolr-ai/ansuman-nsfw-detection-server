from clickhouse_connect.driver.exceptions import DatabaseError
from pydantic import SecretStr

from app.config.settings import Settings
from app.core.lifecycle import build_manual_ban_service
from app.main import create_app


def clickhouse_settings() -> Settings:
    return Settings(
        _env_file=None,
        internal_request_hmac_secret=SecretStr("test-secret"),
        clickhouse_primary_database_url="https://clickhouse.local:8443",
        clickhouse_user=SecretStr("nsfw_detector"),
        clickhouse_password=SecretStr("bad-password"),
    )


def test_manual_ban_service_is_disabled_when_clickhouse_client_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fail_create_clickhouse_client(settings: Settings):  # type: ignore[no-untyped-def]
        raise DatabaseError("authentication failed")

    monkeypatch.setattr("app.core.lifecycle.create_clickhouse_client", fail_create_clickhouse_client)

    assert build_manual_ban_service(clickhouse_settings()) is None


def test_create_app_does_not_crash_when_manual_ban_clickhouse_client_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fail_create_clickhouse_client(settings: Settings):  # type: ignore[no-untyped-def]
        raise DatabaseError("authentication failed")

    monkeypatch.setattr("app.core.lifecycle.create_clickhouse_client", fail_create_clickhouse_client)

    app = create_app(settings=clickhouse_settings())

    assert app.state.manual_ban_service is None
