"""create users table

Revision ID: 0001_create_users
Revises:
Create Date: 2026-05-21 00:00:00.000000

First revision of the per-tenant ``client_template`` lineage. Creates the
``users`` table that backs the Users domain (CRUD endpoints) and the real
``UserStorage``/``UserLookupService``.

Design decisions (see docs/plans/2026-05-20-users-endpoint.md, FINAL answers):

- Q3: ``id`` is an auto-increment integer (``BIGINT GENERATED ALWAYS AS
  IDENTITY``), NOT a UUID. No extension dependency.
- Q4: ``email`` is ``TEXT`` and unique **per tenant** — ``UNIQUE (tenant_id,
  email)``. Normalized lowercase at the request boundary.
- Q5: Row-Level Security is enabled with a tenant-isolation policy keyed off the
  ``app.tenant_id`` session GUC (``current_setting('app.tenant_id', true)``).
  Because nothing wires that GUC yet (the per-request ``SET LOCAL`` lands with
  the tenant-routing task), the policy is shipped **permissive-until-wired**
  (it allows the row when the GUC is unset/empty) so reads do not silently
  return zero rows before routing exists. Application-layer ``tenant_id``
  filtering in ``UserStorage`` is the primary enforcement today; RLS is the
  second layer that becomes strict once the GUC is set.
- ``role`` is a Postgres ENUM ``user_role`` with values ``manager``/``staff``.

upgrade(): create enum -> create table -> unique constraint -> enable + policy.
downgrade(): drop policy -> drop table -> drop enum (symmetric).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_create_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE user_role AS ENUM ('manager', 'staff')"
    )

    op.execute(
        """
        CREATE TABLE users (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id UUID NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role user_role NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_users_tenant_email UNIQUE (tenant_id, email)
        )
        """
    )

    # RLS: second enforcement layer on top of the always-present tenant_id
    # filter in UserStorage. Permissive-until-GUC-wired (see module docstring):
    # the row is visible when the request has SET LOCAL app.tenant_id to this
    # row's tenant, OR when the GUC is not set yet (interim, before routing).
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON users
        USING (
            current_setting('app.tenant_id', true) IS NULL
            OR current_setting('app.tenant_id', true) = ''
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) IS NULL
            OR current_setting('app.tenant_id', true) = ''
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON users")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TYPE IF EXISTS user_role")
