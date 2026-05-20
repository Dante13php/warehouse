from dataclasses import dataclass
from typing import Any


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
