from __future__ import annotations

from app.errors.application_error import ApplicationError


class UserAlreadyExistsError(ApplicationError):
    http_status = 409
    detail = "A user with this email already exists"
