from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.data.abstract_data import (
    DATETIME,
    INT,
    STRING,
    AbstractData,
)


@dataclass
class UserData(AbstractData):
    """The general User management entity (distinct from the auth-identity
    ``AuthUser``; see plan Q1).

    Field names match the ``users`` table columns exactly. ``id`` is an
    auto-increment integer (plan Q3). ``password_hash`` is part of the entity
    but MUST NEVER be returned to a client: use :meth:`to_response` for the safe
    serialization. ``to_dict()`` (inherited) DOES include ``password_hash`` and
    must only be used internally, never as an HTTP response body.
    """

    FIELDS = {
        "id": INT,
        "tenant_id": STRING,
        "email": STRING,
        "password_hash": STRING,
        "role": STRING,
        "created_at": DATETIME,
        "updated_at": DATETIME,
    }

    id: int | None = None
    tenant_id: str | None = None
    email: str | None = None
    password_hash: str | None = None
    role: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_response(self) -> dict[str, Any]:
        """Client-safe serialization: every field EXCEPT ``password_hash``.

        Datetimes are emitted as ISO 8601 UTC with a ``Z`` suffix.
        """
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "role": self.role,
            "created_at": _iso_z(self.created_at),
            "updated_at": _iso_z(self.updated_at),
        }


def _iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    # AbstractData.fix_type normalizes datetimes to tz-aware UTC, so isoformat
    # yields a +00:00 offset; render it as the canonical trailing Z.
    text = value.isoformat()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text
