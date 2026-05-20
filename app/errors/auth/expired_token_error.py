from __future__ import annotations

from app.errors.application_error import ApplicationError


class ExpiredTokenError(ApplicationError):
    http_status = 401
    detail = "Token has expired"
    headers = {"WWW-Authenticate": "Bearer"}
