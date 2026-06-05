from app.config.settings import Settings


def init_sentry(settings: Settings) -> None:
    if settings.sentry_dsn is None:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        send_default_pii=settings.sentry_send_default_pii,
        environment=settings.environment,
    )

