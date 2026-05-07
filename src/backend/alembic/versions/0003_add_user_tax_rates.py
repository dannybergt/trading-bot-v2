"""Add capital_gains_tax_bps + income_tax_bps to users.

Revision ID: a3c1d4f5e6b7
Revises: d939f2abcdc2
Create Date: 2026-05-07 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c1d4f5e6b7"
down_revision: Union[str, None] = "d939f2abcdc2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("capital_gains_tax_bps", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("income_tax_bps", sa.Integer(), nullable=True, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "income_tax_bps")
    op.drop_column("users", "capital_gains_tax_bps")
