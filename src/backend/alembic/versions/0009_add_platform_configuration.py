"""Add `platform_configuration` table.

Persists encrypted operator-level provider keys (e.g. ALPHA_VANTAGE_API_KEY,
FMP_API_KEY) so admins can configure data sources from the UI instead of
editing `.env.local` and restarting the backend.

Values are Fernet-encrypted with `APP_ENCRYPTION_KEY` (same wrapper as the
existing per-user Alpaca secret column). Lookup precedence at read time:
DB (when configured) > environment variable > None. The table is
deliberately excluded from the platform backup payload — encrypted blobs
without the encryption key are not restore-friendly, and a backup that
carries both ciphertext and key would be a single-file leak target.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-13 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_platform_configuration_key",
        "platform_configuration",
        ["key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_configuration_key", table_name="platform_configuration")
    op.drop_table("platform_configuration")
