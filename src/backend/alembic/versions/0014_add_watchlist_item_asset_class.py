"""Add `asset_class` to `watchlist_items`.

Die Anlageklasse eines Watchlist-Eintrags wurde bisher pro Anfrage neu
abgeleitet — entweder aus einem Stammdatenabruf (yfinance `.info`, der unter
Drosselung `429` liefert und den Anfragepfad blockiert) oder aus dem vom Nutzer
vergebenen Anzeigenamen (Substring-Heuristik ueber `ETF_HINT_PATTERNS`). Sie
entscheidet aber darueber, welcher Anbieter die Kurshistorie liefert. Ein
Anzeigetext darf das nicht steuern, und ein Anbieteraufruf pro Anfrage soll es
nicht muessen.

Die Spalte ist `nullable`: `NULL` heisst "noch nicht aufgeloest". Bestandszeilen
verhalten sich damit unveraendert, bis sie das erste Mal gelesen werden; dann
wird die Klasse einmal aufgeloest und geschrieben. Bewusst **kein** Backfill in
der Migration (§9: kein Backfill in einer Schema-Migration, und er braeuchte
Anbieteraufrufe).

Additiv und zerstoerungsfrei; `downgrade` entfernt die Spalte wieder.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-11 16:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watchlist_items",
        sa.Column("asset_class", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("watchlist_items", "asset_class")
