"""Add `display_currency` column to users.

Persists the ISO-4217 currency the user wants money values displayed in.
Default `"USD"` so every existing row stays compatible with the prior
(implicit-USD) behavior; new users inherit the same default.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-12 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "display_currency",
            sa.String(length=8),
            nullable=False,
            server_default="USD",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "display_currency")
