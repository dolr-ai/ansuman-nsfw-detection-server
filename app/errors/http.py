from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.sentry import capture_exception
from app.errors import codes
from app.errors.base import AppError


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        capture_exception(
            exc,
            tags={
                "component": "api",
                "error_code": exc.code,
                "http_status": str(exc.status_code),
            },
            context={
                "method": request.method,
                "path": request.url.path,
                "error_code": exc.code,
                "error_message": exc.message,
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": str(exc.status_code), "message": exc.detail}},
    )


async def validation_error_handler(_: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": codes.VALIDATION_ERROR, "message": str(exc)}},
    )


async def request_validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    missing_headers = {
        str(error["loc"][1]).lower()
        for error in exc.errors()
        if len(error["loc"]) >= 2 and error["loc"][0] == "header" and error["type"] == "missing"
    }
    if missing_headers & {"x-internal-timestamp", "x-internal-signature"}:
        return JSONResponse(
            status_code=401,
            content={"error": {"code": codes.AUTH_MISSING_HEADERS, "message": "missing internal auth headers"}},
        )
    return JSONResponse(
        status_code=422,
        content={"error": {"code": codes.VALIDATION_ERROR, "message": str(exc)}},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    capture_exception(
        exc,
        tags={
            "component": "api",
            "operation": "unhandled_exception",
        },
        context={
            "method": request.method,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"error": {"code": codes.SERVICE_UNAVAILABLE, "message": "internal server error"}},
    )
