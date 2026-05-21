from __future__ import annotations

import logging

from sqlalchemy import text

from app.data.data_collection import DataCollection
from app.data.user_data import UserData
from app.storages.abstract_storage import AbstractStorage

logger = logging.getLogger(__name__)


class UserStorage(AbstractStorage):
    """The only layer that touches the ``users`` table.

    Every authenticated query filters by ``self.tenant_id`` (sourced from the
    verified JWT claims via the IoC). Reads return ``UserData`` /
    ``DataCollection[UserData]`` / ``None``; ``delete`` returns a bool. No
    transactions are started here (the controller wraps mutations). Generated
    ``id``/timestamps are assigned back onto the passed ``UserData`` on insert.

    SQLAlchemy Core ``text()`` is used because the project has no ORM models.
    """

    _COLUMNS = "id, tenant_id, email, password_hash, role, created_at, updated_at"

    async def get_by_email(self, email: str) -> UserData | None:
        """Look up a user by email, scoped to the request's tenant.

        When ``self.tenant_id`` is present (authenticated request) the query is
        ``tenant_id``-scoped. At login there are no claims, so ``tenant_id`` is
        ``None``; the request's bound session targets a single tenant-private
        DB, so email is unambiguous within it (plan Q8). The returned row's
        ``tenant_id`` is authoritative.
        """
        tenant_id = self._ioc.tenant_id
        if tenant_id is not None:
            sql = text(
                f"SELECT {self._COLUMNS} FROM users "
                "WHERE tenant_id = :tenant_id AND email = :email"
            )
            params = {"tenant_id": tenant_id, "email": email}
        else:
            sql = text(
                f"SELECT {self._COLUMNS} FROM users WHERE email = :email"
            )
            params = {"email": email}

        result = await self.session.execute(sql, params)
        row = result.mappings().first()
        if row is None:
            return None
        return UserData.from_row(row)

    async def get_by_id(self, user_id: int) -> UserData | None:
        sql = text(
            f"SELECT {self._COLUMNS} FROM users "
            "WHERE tenant_id = :tenant_id AND id = :id"
        )
        result = await self.session.execute(
            sql, {"tenant_id": self.tenant_id, "id": user_id}
        )
        row = result.mappings().first()
        if row is None:
            return None
        return UserData.from_row(row)

    async def list(self) -> DataCollection[UserData]:
        sql = text(
            f"SELECT {self._COLUMNS} FROM users "
            "WHERE tenant_id = :tenant_id ORDER BY created_at, id"
        )
        result = await self.session.execute(sql, {"tenant_id": self.tenant_id})
        collection: DataCollection[UserData] = DataCollection()
        for row in result.mappings().all():
            collection.add(UserData.from_row(row))
        return collection

    async def create(self, user: UserData) -> UserData:
        sql = text(
            "INSERT INTO users (tenant_id, email, password_hash, role) "
            "VALUES (:tenant_id, :email, :password_hash, :role) "
            f"RETURNING {self._COLUMNS}"
        )
        result = await self.session.execute(
            sql,
            {
                "tenant_id": self.tenant_id,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
            },
        )
        row = result.mappings().one()
        created = UserData.from_row(row)
        # Assign generated PK/timestamps back onto the passed-in object.
        user.id = created.id
        user.tenant_id = created.tenant_id
        user.created_at = created.created_at
        user.updated_at = created.updated_at
        return created

    async def update(self, user: UserData) -> UserData | None:
        sql = text(
            "UPDATE users SET email = :email, password_hash = :password_hash, "
            "role = :role, updated_at = now() "
            "WHERE tenant_id = :tenant_id AND id = :id "
            f"RETURNING {self._COLUMNS}"
        )
        result = await self.session.execute(
            sql,
            {
                "tenant_id": self.tenant_id,
                "id": user.id,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        return UserData.from_row(row)

    async def delete(self, user_id: int) -> bool:
        sql = text(
            "DELETE FROM users WHERE tenant_id = :tenant_id AND id = :id"
        )
        result = await self.session.execute(
            sql, {"tenant_id": self.tenant_id, "id": user_id}
        )
        return result.rowcount > 0
