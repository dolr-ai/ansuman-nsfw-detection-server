from pydantic import BaseModel


class SignedRequestContext(BaseModel):
    service_name: str
    nonce: str
    timestamp: int

