"""Add composite-gate columns to `auto_execution_limits` (roadmap 2b).

`composite_gate_enabled` (default true) and `min_composite_confidence`
(default 0.15) let each user require the composite decision-score to agree with
the ML direction — and clear a confidence bar — before an auto-trade fires. The
gate is purely additive (it can only block), so defaulting it on is a safe,
conservative default. Columns are added with a server default so existing rows
backfill; additive and non-destructive.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-25 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auto_execution_limits",
        sa.Column(
            "composite_gate_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "auto_execution_limits",
        sa.Column(
            "min_composite_confidence",
            sa.Float(),
            nullable=False,
            server_default="0.15",
        ),
    )


def downgrade() -> None:
    op.drop_column("auto_execution_limits", "min_composite_confidence")
    op.drop_column("auto_execution_limits", "composite_gate_enabled")
