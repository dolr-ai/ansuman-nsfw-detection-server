from fastapi import APIRouter, Depends

from app.api.deps import require_signed_request
from app.api.v1 import routes_health, routes_images, routes_text, routes_videos

api_router = APIRouter()
api_router.include_router(routes_health.router)

v1_router = APIRouter(prefix="/v1", dependencies=[Depends(require_signed_request)])
v1_router.include_router(routes_videos.router)
v1_router.include_router(routes_images.router)
v1_router.include_router(routes_text.router)

api_router.include_router(v1_router)

