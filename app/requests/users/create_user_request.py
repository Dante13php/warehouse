from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator

_PIN_MIN_LEN = 6
_PIN_MAX_LEN = 14


class CreateUserRequest(BaseModel):
    """Validated POST /users body. All validation happens here; downstream
    layers trust the result (RULES: Request layer is the boundary).

    - ``email``: valid address, normalized to trimmed lowercase to match the
      per-tenant unique key (plan Q4).
    - ``password``: numeric PIN, digits only, length 6-14 (plan Q9).
    - ``role``: ``manager`` or ``staff`` (the ``user_role`` enum).
    """

    email: EmailStr
    password: str
    role: Literal["manager", "staff"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("password must contain digits only")
        if not (_PIN_MIN_LEN <= len(v) <= _PIN_MAX_LEN):
            raise ValueError(
                f"password must be between {_PIN_MIN_LEN} and {_PIN_MAX_LEN} digits"
            )
        return v
