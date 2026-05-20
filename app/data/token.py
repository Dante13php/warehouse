from dataclasses import dataclass


@dataclass
class TokenData:
    sub: str
    tenant_id: str
    role: str

    @classmethod
    def from_claims(cls, claims: dict) -> "TokenData":
        return cls(
            sub=claims["sub"],
            tenant_id=claims["tenant_id"],
            role=claims["role"],
        )
