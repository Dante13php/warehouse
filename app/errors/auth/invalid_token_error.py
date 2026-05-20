from __future__ import annotations

from app.errors.application_error import ApplicationError


class InvalidTokenError(ApplicationError):
    http_status = 401
    detail = "Invalid or expired refresh token"
    headers = {"WWW-Authenticate": "Bearer"}
