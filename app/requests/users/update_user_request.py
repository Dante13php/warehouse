from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator

_PIN_MIN_LEN = 6
_PIN_MAX_LEN = 14


class UpdateUserRequest(BaseModel):
    """Validated PATCH /users/{user_id} body. PATCH semantics: every field is
    optional and only submitted fields are validated/applied.

    The service applies ``model_dump(exclude_unset=True)`` so unset fields are
    never touched (RULES: PATCH validates only submitted fields).
    """

    email: EmailStr | None = None
    password: str | None = None
    role: Literal["manager", "staff"] | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_pin(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.isdigit():
            raise ValueError("password must contain digits only")
        if not (_PIN_MIN_LEN <= len(v) <= _PIN_MAX_LEN):
            raise ValueError(
                f"password must be between {_PIN_MIN_LEN} and {_PIN_MAX_LEN} digits"
            )
        return v
