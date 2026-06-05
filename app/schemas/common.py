from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class ReadinessDependency(BaseModel):
    name: str
    ready: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    dependencies: list[ReadinessDependency]

