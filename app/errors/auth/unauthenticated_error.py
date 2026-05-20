from __future__ import annotations

from app.errors.application_error import ApplicationError


class UnauthenticatedError(ApplicationError):
    http_status = 401
    detail = "Authentication required"
    headers = {"WWW-Authenticate": "Bearer"}
