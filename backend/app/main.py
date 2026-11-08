import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from app.config import Settings
from app.api.routers.auth import router as auth_router
from app.api.routers.ml_ingest import router as ml_ingest_router
from app.api.routers.operations import router as operations_router
from app.api.routers.telemetry import router as telemetry_router
from app.api.routers.users import router as users_router
from app.db.session import build_engine, build_session_factory, get_db
from app.errors import AppError
from app.logging_config import configure_logging
from app.services.demo_seed import seed_demo

logger = logging.getLogger("amrin.api")


def create_app(settings: Settings | Mapping[str, Any] | None = None) -> FastAPI:
    """Build a configured AMRIN API app, optionally with isolated test settings."""
    configure_logging()
    if settings is None:
        resolved_settings = Settings()
    elif isinstance(settings, Settings):
        resolved_settings = settings
    else:
        resolved_settings = Settings(**settings)

    application = FastAPI(title="AMRIN API", version="0.1.0")
    application.state.settings = resolved_settings
    application.state.engine = build_engine(resolved_settings.database_url)
    application.state.session_factory = build_session_factory(application.state.engine)
    if resolved_settings.demo_mode:
        with application.state.session_factory.begin() as session:
            seed_demo(session)
    application.include_router(auth_router)
    application.include_router(operations_router)
    application.include_router(telemetry_router)
    application.include_router(users_router)
    application.include_router(ml_ingest_router)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-ML-API-Key", "X-Sensor-API-Key"],
    )

    @application.middleware("http")
    async def enforce_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > resolved_settings.max_content_length
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": {"code": "invalid_content_length", "message": "Content-Length must be an integer"}},
                )
            if too_large:
                return JSONResponse(
                    status_code=413,
                    content={"error": {"code": "request_too_large", "message": "Request exceeds the configured size limit"}},
                )
        return await call_next(request)

    @application.get("/api/health", tags=["health"])
    def health():
        try:
            with application.state.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1 FROM users LIMIT 1")
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "database": "unavailable"},
            )
        return {"status": "ok"}

    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        error: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            error["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content={"error": error})

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": f"http_{exc.status_code}", "message": message}},
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", exc_info=exc)
        message = "Internal server error"
        if resolved_settings.environment.lower() not in {"production", "prod"}:
            message = str(exc) or message
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_server_error", "message": message}},
        )

    return application


app = create_app()

__all__ = ["app", "create_app", "get_db"]
