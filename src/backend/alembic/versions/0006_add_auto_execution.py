"""Add auto_execution_limits and auto_execution_events tables.

Revision ID: b3c4d5e6f7a8
Revises: f1a8c2d6e7b9
Create Date: 2026-05-08 17:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "f1a8c2d6e7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auto_execution_limits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Master kill-switch. Default false. Even when true, no automation
        # trades unless evaluate_proposal returns allowed=true AND every
        # halt-trigger check passes AND the Net-Yield-Gate passes.
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_position_size_usd", sa.Float(), nullable=False, server_default="500"),
        sa.Column("max_daily_loss_usd", sa.Float(), nullable=False, server_default="200"),
        sa.Column("max_open_positions", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("max_portfolio_beta", sa.Float(), nullable=False, server_default="2.0"),
        # Comma-separated list of asset classes the user opts into for
        # automation (e.g. "stock,etf"). Empty string = none allowed.
        sa.Column("allowed_asset_classes", sa.String(), nullable=False, server_default=""),
        # JSON map of strategy_name -> percent of total budget. Optional —
        # empty string treated as "no per-strategy split."
        sa.Column("per_strategy_budget_pct", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_auto_execution_limits_user_id"),
    )
    op.create_index(op.f("ix_auto_execution_limits_id"), "auto_execution_limits", ["id"], unique=False)

    op.create_table(
        "auto_execution_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Free-form proposal id so the same evaluation can later be matched
        # to its actual broker order.
        sa.Column("proposal_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("side", sa.String(), nullable=True),
        # proposed | accepted | rejected | executed | failed | halted
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auto_execution_events_id"), "auto_execution_events", ["id"], unique=False)
    op.create_index(op.f("ix_auto_execution_events_user_id"), "auto_execution_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_auto_execution_events_status"), "auto_execution_events", ["status"], unique=False)
    op.create_index(op.f("ix_auto_execution_events_created_at"), "auto_execution_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_auto_execution_events_created_at"), table_name="auto_execution_events")
    op.drop_index(op.f("ix_auto_execution_events_status"), table_name="auto_execution_events")
    op.drop_index(op.f("ix_auto_execution_events_user_id"), table_name="auto_execution_events")
    op.drop_index(op.f("ix_auto_execution_events_id"), table_name="auto_execution_events")
    op.drop_table("auto_execution_events")
    op.drop_index(op.f("ix_auto_execution_limits_id"), table_name="auto_execution_limits")
    op.drop_table("auto_execution_limits")
