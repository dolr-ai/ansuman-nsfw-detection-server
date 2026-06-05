import base64
import mimetypes
from pathlib import Path

from openai import AsyncOpenAI

from app.config.settings import Settings


def create_gpu_openai_client(settings: Settings) -> AsyncOpenAI:
    if not settings.api_base_url or not settings.api_key:
        raise ValueError("GPU API_BASE_URL and API_KEY are required")
    return AsyncOpenAI(
        base_url=settings.api_base_url,
        api_key=settings.api_key.get_secret_value(),
    )


class GpuOpenAIClient:
    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        if settings.model_name is None:
            raise ValueError("MODEL_NAME is required")
        self._settings = settings
        self._client = client or create_gpu_openai_client(settings)

    async def moderate_images(self, *, prompt: str, image_paths: list[Path]) -> str:
        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        for image_path in image_paths:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _image_data_url(image_path)},
                }
            )

        response = await self._client.chat.completions.create(
            model=self._settings.model_name,
            messages=[{"role": "user", "content": content}],
            temperature=0,
        )
        message_content = response.choices[0].message.content
        if isinstance(message_content, str):
            return message_content
        if isinstance(message_content, list):
            return "".join(str(part) for part in message_content)
        return str(message_content)

    async def moderate_text(self, *, prompt: str, text: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._settings.model_name,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            temperature=0,
        )
        message_content = response.choices[0].message.content
        if isinstance(message_content, str):
            return message_content
        if isinstance(message_content, list):
            return "".join(str(part) for part in message_content)
        return str(message_content)


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
