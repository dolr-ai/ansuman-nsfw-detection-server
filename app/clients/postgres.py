from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config.settings import Settings


def create_postgres_engine(settings: Settings) -> AsyncEngine:
    if settings.postgres_database_url is None:
        raise ValueError("POSTGRES_DATABASE_URL is required")
    return create_async_engine(settings.postgres_database_url.get_secret_value())

