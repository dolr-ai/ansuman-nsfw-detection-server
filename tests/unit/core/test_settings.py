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
