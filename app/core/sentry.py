import logging
from collections.abc import Mapping
from typing import Any

from app.config.settings import Settings

_LOG = logging.getLogger(__name__)


def init_sentry(settings: Settings) -> None:
    if settings.sentry_dsn is None:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        send_default_pii=settings.sentry_send_default_pii,
        environment=settings.environment,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
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
            scope.capture_exception(exc)
    except Exception as capture_err:
        _LOG.warning("sentry capture_exception failed: %s", capture_err)
