from collections.abc import Mapping
from typing import Any

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


def capture_exception(
    exc: BaseException,
    *,
    tags: Mapping[str, str] | None = None,
    context: Mapping[str, Any] | None = None,
) -> None:
    try:
        import sentry_sdk

        with sentry_sdk.new_scope() as scope:
            for key, value in (tags or {}).items():
                scope.set_tag(key, value)
            if context:
                scope.set_context("nsfw_detector", dict(context))
            sentry_sdk.capture_exception(exc)
    except Exception:
        return
