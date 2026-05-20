from __future__ import annotations

from typing import Any


class ApplicationError(Exception):
    """Base class for all domain errors raised by the application.

    Carries the HTTP status and detail that the central FastAPI exception
    handler (see ``app/main.py``) uses to build the response. Subclasses set
    ``http_status``/``detail`` (and optionally ``headers``) so controllers and
    services never translate errors to ``HTTPException`` manually — they raise a
    domain error and it bubbles up to the global handler (the CloudSale flat-flow
    pattern).
    """

    http_status: int = 400
    detail: str = "Bad Request"
    headers: dict[str, str] | None = None

    def __init__(
        self,
        detail: str | None = None,
        *,
        http_status: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if detail is not None:
            self.detail = detail
        if http_status is not None:
            self.http_status = http_status
        if headers is not None:
            self.headers = headers
        super().__init__(self.detail)

    def export(self) -> dict[str, Any]:
        return {"detail": self.detail}
