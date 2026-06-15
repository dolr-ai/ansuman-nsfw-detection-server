import hashlib
import os
from pathlib import Path

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster

from app.config.settings import Settings


def create_kvrocks_client(settings: Settings) -> Redis | RedisCluster:
    ssl_ca_data = _pem_data(settings.kvrocks_ssl_ca_cert)
    ssl_ca_certs = None if ssl_ca_data else settings.kvrocks_ssl_ca_cert
    ssl_certfile = _pem_file(settings.kvrocks_ssl_client_cert)
    ssl_keyfile = _pem_file(settings.kvrocks_ssl_client_key)
    client_cls = RedisCluster if settings.kvrocks_cluster_enabled else Redis
    return client_cls(
        host=settings.kvrocks_host,
        port=settings.kvrocks_port,
        password=settings.kvrocks_password.get_secret_value() if settings.kvrocks_password else None,
        ssl=settings.kvrocks_tls_enabled,
        ssl_ca_certs=ssl_ca_certs,
        ssl_ca_data=ssl_ca_data,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
        decode_responses=True,
        max_connections=settings.kvrocks_max_connections,
        socket_timeout=settings.kvrocks_socket_timeout_seconds,
        socket_connect_timeout=settings.kvrocks_socket_connect_timeout_seconds,
        health_check_interval=settings.kvrocks_health_check_interval_seconds,
    )


def _pem_data(value: str | None) -> str | None:
    if value and "-----BEGIN " in value:
        return value
    return None


def _pem_file(value: str | None) -> str | None:
    if not value:
        return None
    if "-----BEGIN " not in value:
        return value

    cert_dir = Path("/tmp/nsfw-kvrocks-certs")
    cert_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    path = cert_dir / f"{digest}.pem"
    if not path.exists():
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)
    return str(path)
