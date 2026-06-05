from pydantic import BaseModel


class SignedRequestContext(BaseModel):
    timestamp: int
