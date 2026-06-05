from pydantic import BaseModel, Field


class ImageUrlDetectRequest(BaseModel):
    image_url: str = Field(min_length=1)


class ImageBase64DetectRequest(BaseModel):
    image_base64: str = Field(min_length=1)

