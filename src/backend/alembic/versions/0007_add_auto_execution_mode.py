"""Add `mode` column to auto_execution_limits.

Lets users opt into paper-only automation (the safe path used to validate
the loop end-to-end) versus live automation against Alpaca (gated until
the user explicitly flips it). Default is `paper` — every existing row
becomes paper-only on upgrade.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-08 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auto_execution_limits",
        sa.Column("mode", sa.String(), nullable=False, server_default="paper"),
    )


def downgrade() -> None:
    op.drop_column("auto_execution_limits", "mode")
