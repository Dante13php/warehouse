from dataclasses import dataclass
from typing import Any


# Auth identity data stays a plain @dataclass (NOT AbstractData): it has no
# expanded fields and no type-coercion need (from_row already casts), and it
# carries password_hash which must never be serialized via to_dict(). Adding an
# AbstractData FIELDS map / to_dict() here would create a credential-leak risk
# with no current benefit.
@dataclass
class AuthUser:
    id: str
    tenant_id: str
    email: str
    role: str
    password_hash: str

    @classmethod
    def from_row(cls, row: Any) -> "AuthUser":
        return cls(
            id=str(row.id),
            tenant_id=str(row.tenant_id),
            email=row.email,
            role=row.role,
            password_hash=row.password_hash,
        )
