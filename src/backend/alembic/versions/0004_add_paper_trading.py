"""Add paper-trading order and transaction tables.

Revision ID: c8e2a1b9d4f3
Revises: a3c1d4f5e6b7
Create Date: 2026-05-08 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8e2a1b9d4f3"
down_revision: Union[str, None] = "a3c1d4f5e6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.Column(
            "placed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paper_orders_id"), "paper_orders", ["id"], unique=False)
    op.create_index(op.f("ix_paper_orders_user_id"), "paper_orders", ["user_id"], unique=False)
    op.create_index(op.f("ix_paper_orders_symbol"), "paper_orders", ["symbol"], unique=False)
    op.create_index(op.f("ix_paper_orders_status"), "paper_orders", ["status"], unique=False)
    op.create_index(op.f("ix_paper_orders_placed_at"), "paper_orders", ["placed_at"], unique=False)

    op.create_table(
        "paper_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("fee_absolute", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fee_percent_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["paper_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paper_transactions_id"), "paper_transactions", ["id"], unique=False)
    op.create_index(op.f("ix_paper_transactions_user_id"), "paper_transactions", ["user_id"], unique=False)
    op.create_index(op.f("ix_paper_transactions_order_id"), "paper_transactions", ["order_id"], unique=False)
    op.create_index(op.f("ix_paper_transactions_symbol"), "paper_transactions", ["symbol"], unique=False)
    op.create_index(op.f("ix_paper_transactions_executed_at"), "paper_transactions", ["executed_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_paper_transactions_executed_at"), table_name="paper_transactions")
    op.drop_index(op.f("ix_paper_transactions_symbol"), table_name="paper_transactions")
    op.drop_index(op.f("ix_paper_transactions_order_id"), table_name="paper_transactions")
    op.drop_index(op.f("ix_paper_transactions_user_id"), table_name="paper_transactions")
    op.drop_index(op.f("ix_paper_transactions_id"), table_name="paper_transactions")
    op.drop_table("paper_transactions")
    op.drop_index(op.f("ix_paper_orders_placed_at"), table_name="paper_orders")
    op.drop_index(op.f("ix_paper_orders_status"), table_name="paper_orders")
    op.drop_index(op.f("ix_paper_orders_symbol"), table_name="paper_orders")
    op.drop_index(op.f("ix_paper_orders_user_id"), table_name="paper_orders")
    op.drop_index(op.f("ix_paper_orders_id"), table_name="paper_orders")
    op.drop_table("paper_orders")
