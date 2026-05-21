from __future__ import annotations

from app.errors.application_error import ApplicationError


class UserNotFoundError(ApplicationError):
    http_status = 404
    detail = "User not found"
