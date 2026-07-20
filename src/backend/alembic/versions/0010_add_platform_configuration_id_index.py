"""Add missing `ix_platform_configuration_id` index.

Migration 0009 created the `platform_configuration` table but omitted the
`id` index that every other table carries via the house convention
(`id = Column(Integer, primary_key=True, index=True)` -> `ix_<table>_id`).
The `PlatformConfiguration` model declares that index, so models and schema
drifted apart — caught by `test_models_match_migration_head`.

This forward-only migration reconciles the two. Creating an index is
additive and non-destructive; on existing Postgres deployments (where 0009
already ran) it simply adds the previously-missing index.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-20 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ix_platform_configuration_id"
TABLE_NAME = "platform_configuration"


def _index_exists(bind) -> bool:
    inspector = inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return False
    return any(idx["name"] == INDEX_NAME for idx in inspector.get_indexes(TABLE_NAME))


def upgrade() -> None:
    # Idempotent: on a legacy volume where `platform_configuration` was
    # materialized by the init_db `create_all` safety net (which builds the
    # table WITH this index, because the model declares index=True) rather than
    # by migration 0009, the index already exists. Creating it again would
    # raise "relation already exists" and break the boot — the exact drift class
    # this migration is meant to reconcile. Guard on the inspector instead.
    bind = op.get_bind()
    if not _index_exists(bind):
        op.create_index(op.f(INDEX_NAME), TABLE_NAME, ["id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind):
        op.drop_index(op.f(INDEX_NAME), table_name=TABLE_NAME)
