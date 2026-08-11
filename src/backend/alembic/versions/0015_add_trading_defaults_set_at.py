"""Add `trading_defaults_set_at` to `users`.

`models.py` setzt `trade_fee_absolute=1` und `min_target_yield=1` als
Datenbank-Vorgaben. Die Onboarding-Bewertung las daraus "konfiguriert" — beide
Bedingungen sind fuer ein frisch registriertes Konto erfuellt, ohne dass der
Nutzer etwas eingegeben hat. Ein frisches Konto handelte damit gegen eine
1-%-Schwelle plus 1 Waehrungseinheit Gebuehr, die niemand gewaehlt hat.

Die Werte bleiben unveraendert. Unterscheidbar wird die **Aussage** darueber:
`NULL` heisst "Vorgabe der Datenbank", ein Zeitstempel heisst "vom Nutzer
gesetzt".

**Der einmalige Datenschritt** setzt den Zeitstempel fuer Bestandsnutzer, deren
Werte von den Vorgaben abweichen — abweichen konnten sie nur, wenn jemand sie
gesetzt hat. Wer noch exakt auf den Vorgaben steht, ist genau die Gruppe, die
nie gewaehlt hat, und wird beim naechsten Login danach gefragt. Der Schritt ist
deterministisch und idempotent; die Tabelle ist klein (Einzelnutzer- bis
Kleingruppen-Betrieb), deshalb kein Batching noetig. §9 verbietet Backfills
**grosser** Tabellen in Schema-Migrationen — dieser Fall ist einer
`UPDATE ... WHERE`-Anweisung ueber wenige Zeilen.

Ausdruecklich in Kauf genommen: wer bewusst exakt 1/0/1/0 gewaehlt hat, wird
einmal erneut gefragt. Ein Speichern raeumt das ab. Die Gegenrichtung — jemandem
eine Auswahl zu unterstellen, die er nie getroffen hat — ist der Fehler, den
diese Migration behebt.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-11 17:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("trading_defaults_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE users
           SET trading_defaults_set_at = created_at
         WHERE trading_defaults_set_at IS NULL
           AND NOT (
                 COALESCE(trade_fee_absolute, 1) = 1
             AND COALESCE(trade_fee_percent, 0) = 0
             AND COALESCE(min_target_yield, 1) = 1
             AND COALESCE(capital_gains_tax_bps, 0) = 0
             AND COALESCE(income_tax_bps, 0) = 0
           )
        """
    )


def downgrade() -> None:
    op.drop_column("users", "trading_defaults_set_at")
