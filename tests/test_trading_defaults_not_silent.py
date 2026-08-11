"""Ein frisches Konto handelt nicht gegen eine Schwelle, die niemand gewaehlt hat.

Der Befund (2026-08-11, im STATE als §13-Punkt gefuehrt): `models.py` setzt
`trade_fee_absolute=1` und `min_target_yield=1` als **Datenbank-Vorgaben**, und
die Onboarding-Bewertung liest daraus "konfiguriert":

    completed: portfolio.min_target_yield > 0
               && (trade_fee_absolute > 0 || trade_fee_percent > 0)

Beide Bedingungen sind fuer ein frisch registriertes Konto erfuellt, ohne dass
der Nutzer etwas eingegeben hat. Der Pflichtschritt "Trading defaults" gilt beim
ersten Login als erledigt, und die Empfehlungen laufen gegen eine 1-%-Schwelle
plus 1 Waehrungseinheit Gebuehr, die niemand gewaehlt hat.

**Was hier geaendert wird und was nicht.** Die Vorgabewerte bleiben, wie sie
sind — sie sind konservativ (sie *blockieren* eher eine Empfehlung, als eine
zusaetzliche zuzulassen), und welche Zahlen richtig sind, entscheidet der
Mensch. Geaendert wird die **Aussage darueber**: "vom Nutzer gesetzt" wird von
"Vorgabe der Datenbank" unterscheidbar.

Geprueft wird:
  1. die Praemisse — ein frisch angelegter Nutzer erfuellt die alte Bedingung,
  2. ein frisch angelegter Nutzer hat **keinen** Bestaetigungszeitpunkt,
  3. das Speichern der Einstellungen setzt ihn,
  4. die Antwort des Endpunkts traegt ihn (ohne das kann die Oberflaeche die
     Unterscheidung nicht treffen — der stille Rueckweg),
  5. der Schnappschuss traegt ihn durch Export und Import.
"""
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


class FreshAccountTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.database import Base

        # `app.models` muss **vor** `create_all` importiert sein, sonst kennt
        # `Base.metadata` die Tabellen noch nicht und der erste Fall der Klasse
        # laeuft gegen eine leere Datenbank. Reihenfolgeabhaengig und damit
        # genau die Sorte Fehler, die nur beim ersten Lauf auffaellt.
        import app.models  # noqa: F401

        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)()

    def tearDown(self):
        self.db.close()

    def _frischer_nutzer(self):
        from app.models import User

        user = User(email="neu@example.com", hashed_password="x")
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def test_die_praemisse_gilt_noch(self):
        # Ohne diesen Fall wuesste niemand, ob der Rest ein echtes Problem
        # behandelt oder eines, das laengst weg ist.
        user = self._frischer_nutzer()
        alte_bedingung = user.min_target_yield > 0 and (
            user.trade_fee_absolute > 0 or user.trade_fee_percent > 0
        )
        self.assertTrue(
            alte_bedingung,
            "die Vorgabewerte erfuellen die alte Bedingung nicht mehr — dieser "
            "Fall und sein Fix sind dann gegenstandslos",
        )

    def test_ein_frisches_konto_hat_nichts_bestaetigt(self):
        user = self._frischer_nutzer()
        self.assertIsNone(
            user.trading_defaults_set_at,
            "ein frisches Konto gilt als konfiguriert, obwohl niemand etwas "
            "gewaehlt hat",
        )

    def test_speichern_setzt_den_zeitpunkt(self):
        from app.auth_routes import PortfolioSettingsRequest, update_my_portfolio_settings

        user = self._frischer_nutzer()
        with patch("app.audit_service.log_event"):
            antwort = update_my_portfolio_settings(
                PortfolioSettingsRequest(
                    trade_fee_absolute=1,
                    trade_fee_percent=0,
                    min_target_yield=1,
                    capital_gains_tax_bps=2637,
                ),
                current_user=user,
                db=self.db,
            )

        self.assertIsNotNone(user.trading_defaults_set_at)
        # Auch wenn der Nutzer genau die Vorgabewerte bestaetigt: die
        # Bestaetigung ist die Entscheidung, nicht der Wert.
        self.assertEqual(user.min_target_yield, 1)
        self.assertIsNotNone(
            antwort.trading_defaults_set_at,
            "der Endpunkt gibt den Zeitpunkt nicht zurueck — die Oberflaeche "
            "kann die Unterscheidung dann nicht treffen",
        )

    def test_der_lesende_endpunkt_traegt_den_zeitpunkt(self):
        from app.auth_routes import get_my_portfolio_settings

        user = self._frischer_nutzer()
        antwort = get_my_portfolio_settings(user)
        self.assertIsNone(antwort.trading_defaults_set_at)


class OnboardingRuleTests(unittest.TestCase):
    """Der stille Rueckweg auf der anderen Seite: das Backend kann den
    Zeitpunkt liefern, und die Oberflaeche liest ihn trotzdem nicht."""

    def test_the_onboarding_step_reads_the_confirmation_not_the_values(self):
        quelle = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "frontend"
            / "src"
            / "auth"
            / "useOnboarding.ts"
        ).read_text(encoding="utf-8")

        trading_block = quelle[quelle.index('id: "trading"') : quelle.index('id: "taxes"')]
        self.assertIn(
            "trading_defaults_set_at",
            trading_block,
            "der Schritt bewertet weiter die Werte selbst — die Vorgaben der "
            "Datenbank gelten damit als Auswahl des Nutzers",
        )
        self.assertNotIn(
            "min_target_yield > 0",
            trading_block,
            "die alte Bedingung steht noch da",
        )


class SnapshotTests(unittest.TestCase):
    def test_export_and_import_carry_the_confirmation(self):
        import inspect

        from app import backup_service

        quelle = inspect.getsource(backup_service)
        self.assertIn('"trading_defaults_set_at"', quelle)
        self.assertIn("trading_defaults_set_at=", quelle)


if __name__ == "__main__":
    unittest.main()
