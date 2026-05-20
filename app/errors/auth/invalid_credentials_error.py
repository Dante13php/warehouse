from __future__ import annotations

from app.errors.application_error import ApplicationError


class InvalidCredentialsError(ApplicationError):
    http_status = 401
    detail = "Invalid credentials"
    headers = {"WWW-Authenticate": "Bearer"}
