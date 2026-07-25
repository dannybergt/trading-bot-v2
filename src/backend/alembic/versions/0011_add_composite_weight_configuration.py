"""Add `composite_weight_configuration` table.

Persists an operator override of the composite decision-score axis weights
(app/composite_score.py) so an admin can tune them from the UI, and so the
roadmap-2d backtest calibration can later write a calibrated set. Unlike
`platform_configuration` these are plain numbers, not secrets, so the value is
stored in clear text as a small JSON object. Singleton row (id=1); the read
path falls back to the in-code DEFAULT_WEIGHTS when the row is absent or
invalid, so this migration is safe to apply ahead of any code that writes it.

Adding a fresh table is additive and non-destructive; downgrade drops it.

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-07-25 12:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "composite_weight_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("weights_json", sa.Text(), nullable=False),
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
        op.f("ix_composite_weight_configuration_id"),
        "composite_weight_configuration",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_composite_weight_configuration_id"),
        table_name="composite_weight_configuration",
    )
    op.drop_table("composite_weight_configuration")
