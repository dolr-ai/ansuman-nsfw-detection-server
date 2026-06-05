import shutil

from app.config.settings import Settings


class ReadinessService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check(self) -> list[dict[str, object]]:
        return [
            self._dependency("internal_auth", self._settings.internal_request_secret() is not None, "configured"),
            self._dependency("postgres", self._settings.is_postgres_configured(), "configured"),
            self._dependency("kvrocks", self._settings.is_kvrocks_configured(), "configured"),
            self._dependency("clickhouse", self._settings.is_clickhouse_configured(), "configured"),
            self._dependency("gpu", self._settings.is_gpu_configured(), "configured"),
            self._dependency("ffmpeg", shutil.which("ffmpeg") is not None, "binary available"),
            self._dependency("ffprobe", shutil.which("ffprobe") is not None, "binary available"),
        ]

    @staticmethod
    def _dependency(name: str, ready: bool, detail: str) -> dict[str, object]:
        return {"name": name, "ready": ready, "detail": detail if ready else f"not {detail}"}
