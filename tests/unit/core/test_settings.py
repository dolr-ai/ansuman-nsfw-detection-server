from pydantic import SecretStr

from app.config.settings import Settings


def test_settings_maps_existing_grpc_token_to_temp_hmac_secret() -> None:
    settings = Settings(_env_file=None, NSFW_GRPC_TOKEN=SecretStr("legacy-token"))

    assert settings.secret_for_service("off-chain-agent") == "legacy-token"


def test_settings_repr_redacts_secrets() -> None:
    settings = Settings(
        _env_file=None,
        service_hmac_secrets={"off-chain-agent": SecretStr("secret-value")},
        api_key=SecretStr("gpu-secret"),
    )

    rendered = repr(settings)

    assert "secret-value" not in rendered
    assert "gpu-secret" not in rendered

