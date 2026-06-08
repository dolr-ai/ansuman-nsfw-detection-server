from pydantic import BaseModel, ConfigDict, Field


class ImageUrlDetectRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"image_url": "https://example.com/image.jpg"},
                {
                    "image_url": "https://example.com/image.jpg",
                    "prompt": "Make a cinematic beach dance video.",
                },
            ],
        }
    )

    image_url: str = Field(min_length=1)
    prompt: str | None = None


class ImageBase64DetectRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"image_base64": "/9j/4AAQSkZJRgABAQAAAQABAAD..."},
                {
                    "image_base64": "/9j/4AAQSkZJRgABAQAAAQABAAD...",
                    "prompt": "Make this person nude.",
                },
            ],
        }
    )

    image_base64: str = Field(min_length=1)
    prompt: str | None = None
