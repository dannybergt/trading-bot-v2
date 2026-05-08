"""Add audit_events table for sensitive-action logging.

Revision ID: f1a8c2d6e7b9
Revises: c8e2a1b9d4f3
Create Date: 2026-05-08 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a8c2d6e7b9"
down_revision: Union[str, None] = "c8e2a1b9d4f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        # user_id is nullable so failed-login attempts (where the user
        # could not be identified) can still leave a record.
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("actor_fingerprint", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False, server_default="success"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ip_fingerprint", sa.String(), nullable=True),
        sa.Column("user_agent_fingerprint", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_id"), "audit_events", ["id"], unique=False)
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"], unique=False)
    op.create_index(op.f("ix_audit_events_resource_type"), "audit_events", ["resource_type"], unique=False)
    op.create_index(op.f("ix_audit_events_created_at"), "audit_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_resource_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_id"), table_name="audit_events")
    op.drop_table("audit_events")
