"""Add `composite_snapshot` table (forward-collection for 2d-3 calibration).

Persists one row per (symbol, UTC date) with the composite verdict, each
axis's raw value and the close price at recommendation time; a background
labeling pass later fills the realised forward return. This is what lets the
otherwise un-backtestable analyst/news axes ever be calibrated (see the 2d
ADR). Additive and non-destructive; downgrade drops the table.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-25 13:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "composite_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("axis_technical", sa.Float(), nullable=True),
        sa.Column("axis_analyst", sa.Float(), nullable=True),
        sa.Column("axis_fundamentals", sa.Float(), nullable=True),
        sa.Column("axis_news", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("verdict", sa.String(length=8), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("forward_close", sa.Float(), nullable=True),
        sa.Column("forward_return_pct", sa.Float(), nullable=True),
        sa.Column("realized_up", sa.Boolean(), nullable=True),
        sa.Column("labeled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "symbol", "snapshot_date", name="uq_composite_snapshot_symbol_date"
        ),
    )
    op.create_index(
        op.f("ix_composite_snapshot_id"), "composite_snapshot", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_composite_snapshot_symbol"),
        "composite_snapshot",
        ["symbol"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_composite_snapshot_symbol"), table_name="composite_snapshot")
    op.drop_index(op.f("ix_composite_snapshot_id"), table_name="composite_snapshot")
    op.drop_table("composite_snapshot")
