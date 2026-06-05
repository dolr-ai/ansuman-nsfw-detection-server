from urllib.parse import urlparse

from app.config.settings import Settings


def create_clickhouse_client(settings: Settings):  # type: ignore[no-untyped-def]
    import clickhouse_connect

    if settings.clickhouse_primary_database_url is None:
        raise ValueError("CLICKHOUSE_PRIMARY_DATABASE_URL is required")

    parsed = urlparse(settings.clickhouse_primary_database_url.get_secret_value())
    database = parsed.path.lstrip("/") or settings.clickhouse_database
    username = settings.clickhouse_user.get_secret_value() if settings.clickhouse_user else parsed.username
    password = settings.clickhouse_password.get_secret_value() if settings.clickhouse_password else parsed.password
    secure = settings.clickhouse_secure or parsed.scheme == "https"

    return clickhouse_connect.get_client(
        host=parsed.hostname,
        port=parsed.port,
        username=username,
        password=password,
        database=database,
        secure=secure,
        verify=settings.clickhouse_verify,
    )
