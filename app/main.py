import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.controllers.auth.router import router as auth_router
from app.infrastructure.auth_middleware import AuthMiddleware

# PRODUCTION REQUIREMENT: This application must be deployed behind a TLS-terminating
# reverse proxy (e.g., nginx, Caddy, or a cloud load balancer). The app itself does
# not terminate TLS. All plaintext traffic must be blocked at the network boundary.

logger = logging.getLogger(__name__)

app = FastAPI(title="Warehouse")

# Authentication middleware runs before all route handlers, establishing request
# identity (JWT bearer, then API key) on request.state for get_ioc to read.
app.add_middleware(AuthMiddleware)

app.include_router(auth_router)


def _build_validation_error_response(exc: RequestValidationError) -> dict:
    """Build the unified validation-error envelope for HTTP 422 responses.

    Shape::

        {
            "error": {
                "code": "V001",
                "message": "The request contains invalid query or body parameters.",
                "details": [{"loc": [...], "msg": "..."}]
            }
        }

    The noisy ``ctx`` and ``url`` fields from Pydantic's raw error objects are
    stripped so consumers receive a stable, clean structure.
    """
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
    """Reshape FastAPI/Pydantic 422 errors into the unified validation envelope.

    Only ``RequestValidationError`` is reshaped here. ``ResponseValidationError``
    and other exceptions are unaffected and continue to use FastAPI's default
    handling.
    """
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
