from pydantic import BaseModel, Field


class TextDetectRequest(BaseModel):
    text: str = Field(min_length=1)

