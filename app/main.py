import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.controllers.auth.auth import router as auth_router
from app.errors.application_error import ApplicationError
from app.infrastructure.auth_middleware import AuthMiddleware

# PRODUCTION REQUIREMENT: This application must be deployed behind a TLS-terminating
# reverse proxy (e.g., nginx, Caddy, or a cloud load balancer). The app itself does
# not terminate TLS. All plaintext traffic must be blocked at the network boundary.

logger = logging.getLogger(__name__)

app = FastAPI(title="Warehouse")

app.add_middleware(AuthMiddleware)

app.include_router(auth_router)


def _build_validation_error_response(exc: RequestValidationError) -> dict:
    details = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg", "")}
        for err in exc.errors()
    ]
    return {
        "error": {
            "code": "V001",
            "message": "The request contains invalid query or body parameters.",
            "details": details,
        }
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.debug(
        "Request validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=_build_validation_error_response(exc),
    )


@app.exception_handler(ApplicationError)
async def application_error_handler(
    request: Request, exc: ApplicationError
) -> JSONResponse:
    logger.debug(
        "Application error on %s %s: %s",
        request.method,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": exc.export()},
        headers=exc.headers,
    )
