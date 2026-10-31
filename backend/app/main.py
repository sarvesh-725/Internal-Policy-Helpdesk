import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from jwt import InvalidTokenError

from app.api.router import api_router
from app.api.routes.system import healthz, readyz
from app.auth.dependencies import AuthenticationError, AuthorizationError
from app.config import get_settings
from app.observability.setup import configure_observability, current_trace_id, request_trace_context


logger = logging.getLogger("nodeswarm")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/docs" if settings.app_env == "development" else None)
    configure_observability(app, settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Last-Event-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        with request_trace_context(request_id):
            request.state.trace_id = current_trace_id()
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "trace_id": getattr(request.state, "trace_id", None),
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    @app.exception_handler(AuthenticationError)
    async def authentication_error(request: Request, _: AuthenticationError) -> JSONResponse:
        return safe_error(request, 401, "authentication_required", "A valid sign-in token is required.")

    @app.exception_handler(AuthorizationError)
    async def authorization_error(request: Request, _: AuthorizationError) -> JSONResponse:
        return safe_error(request, 403, "access_denied", "You do not have access to this resource.")

    @app.exception_handler(InvalidTokenError)
    async def invalid_token_error(request: Request, _: InvalidTokenError) -> JSONResponse:
        return safe_error(request, 401, "authentication_required", "A valid sign-in token is required.")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return safe_error(request, 422, "invalid_request", "The request format is invalid.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        messages = {401: "A valid sign-in token is required.", 403: "You do not have access to this resource.", 404: "The requested resource was not found.", 409: "The request cannot be completed in its current state.", 422: "The request cannot be processed."}
        return safe_error(request, exc.status_code, "request_failed", messages.get(exc.status_code, "The request could not be completed."))

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, _: Exception) -> JSONResponse:
        # Do not write provider/database exception text because it can contain an unsafe user/model value.
        logger.error(
            "unhandled_request_failure",
            extra={"request_id": request.state.request_id, "trace_id": getattr(request.state, "trace_id", None), "path": request.url.path},
        )
        return safe_error(request, 500, "internal_error", "An unexpected error occurred.")

    app.add_api_route("/healthz", healthz, methods=["GET"], response_model=None, include_in_schema=False)
    app.add_api_route("/readyz", readyz, methods=["GET"], response_model=None, include_in_schema=False)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


def safe_error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)},
    )


app = create_app()
