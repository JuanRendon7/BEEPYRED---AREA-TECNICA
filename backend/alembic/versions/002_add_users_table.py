"""add users table

Revision ID: 002
Revises: 001
Create Date: 2026-04-26

NOTA: Agregar tabla users para autenticacion JWT (Phase 2 AUTH-01).
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("idx_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_users_username", table_name="users")
    op.drop_table("users")
