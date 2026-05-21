from __future__ import annotations

from app.errors.application_error import ApplicationError


class ForbiddenError(ApplicationError):
    http_status = 403
    detail = "Forbidden"
