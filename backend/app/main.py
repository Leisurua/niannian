import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.platform.config import get_settings
from app.platform.errors import AppError, app_error_response, error_response
from app.platform.logging import configure_logging, log_event
from app.platform.request_id import RequestIdMiddleware


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("nianian.api")

app = FastAPI(title="NianNian API", version="0.1.0", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(RequestIdMiddleware)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    log_event(logger, logging.WARNING, "APP_ERROR", error_code=exc.code)
    return app_error_response(request, exc)


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    log_event(logger, logging.WARNING, "HTTP_ERROR", error_code="HTTP_ERROR")
    return error_response(
        request,
        status_code=exc.status_code,
        code="HTTP_ERROR",
        message=str(exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    log_event(logger, logging.WARNING, "VALIDATION_ERROR", error_code="VALIDATION_ERROR")
    details = [
        {"field": ".".join(str(part) for part in item["loc"]), "reason": item["type"]}
        for item in exc.errors()
    ]
    return error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=details,
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log_event(logger, logging.ERROR, "UNHANDLED_APPLICATION_ERROR", error_code="INTERNAL_ERROR")
    return error_response(
        request,
        status_code=500,
        code="INTERNAL_ERROR",
        message="Internal server error",
    )


@app.get("/health", tags=["system"])
async def health(request: Request) -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env, "request_id": request.state.request_id}
