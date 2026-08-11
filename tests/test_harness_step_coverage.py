"""Jeder Harnisch-Schritt ist zugeordnet — als Beweis oder als Vertrag.

Der Zielkatalog prueft eine Richtung: hat jedes Versprechen einen Beweisschritt?
Die Gegenrichtung stand seit dem 2026-08-05 als Fliesstext im Katalog ("43 von
75 Harnisch-Schritten bewachen keine Zielzeile") und ist seitdem still auf 72
von 87 gewachsen. Eine Zahl ueber den eigenen Pruefstand, die niemand
nachrechnet, ist genau die Sorte Aussage, die dieses Projekt in dieser Woche
mehrfach als unwahr entlarvt hat.

Dieser Guard rechnet sie nach. Er verlangt **nicht**, dass jeder Schritt eine
Zielzeile bewacht — die meisten sollen das gar nicht. Er verlangt, dass jeder
Schritt **eingeordnet** ist: entweder nennt ihn der Katalog als Beweisschritt,
oder er steht in `schritte-ohne-zielzeile.md`. Ein neuer Schritt, der weder das
eine noch das andere ist, macht ihn rot.

Und er haelt die Liste sauber: ein Eintrag, den kein Harnisch mehr ausgibt, und
ein Eintrag, der inzwischen im Katalog steht, fallen ebenfalls auf. Damit kann
die Liste nur schrumpfen oder bewusst wachsen — nicht still.

Bewusst NICHT geprueft: ob ein Schritt das prueft, was seine Einordnung
behauptet. Das kann keine Textpruefung leisten.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KATALOG = REPO_ROOT / "docs" / "verification" / "zielkatalog.md"
LISTE = REPO_ROOT / "docs" / "verification" / "schritte-ohne-zielzeile.md"
UI_HARNISCH = REPO_ROOT / "tests" / "run-ui-regression.mjs"
API_HARNISCH = REPO_ROOT / "tests" / "run-api-regression.sh"

# `ui_regression` ist kein Schritt, sondern der Name des Laufs in seinen
# Sammelmeldungen ("UI regression passed for ...").
KEIN_SCHRITT = {"ui_regression"}


def ui_schritte(text: str) -> set[str]:
    return set(re.findall(r'console\.log\(`?"?(ui_[a-z_0-9]+) ', text)) - KEIN_SCHRITT


def api_schritte(text: str) -> set[str]:
    return set(re.findall(r'print\(f?"([a-z][^"]*?) ok(?:"|\s|\[)', text))


class HarnessStepCoverageTests(unittest.TestCase):
    def setUp(self):
        for pfad in (KATALOG, LISTE, UI_HARNISCH, API_HARNISCH):
            if not pfad.exists():
                self.fail(f"{pfad.relative_to(REPO_ROOT)} fehlt")
        self.katalog = KATALOG.read_text(encoding="utf-8")
        self.liste = LISTE.read_text(encoding="utf-8")
        self.schritte = ui_schritte(UI_HARNISCH.read_text(encoding="utf-8")) | api_schritte(
            API_HARNISCH.read_text(encoding="utf-8")
        )

    def _im_katalog(self, schritt: str) -> bool:
        return f"`{schritt}`" in self.katalog

    def _in_der_liste(self, schritt: str) -> bool:
        return f"`{schritt}`" in self.liste

    def test_es_gibt_ueberhaupt_schritte(self):
        # Faellt die Extraktion (umbenannte Ausgabe, geaendertes Format), waere
        # ohne diesen Fall alles andere leer und damit gruen.
        self.assertGreater(
            len(self.schritte), 50, f"zu wenige Schritte erkannt: {len(self.schritte)}"
        )

    def test_jeder_schritt_ist_eingeordnet(self):
        offen = sorted(
            schritt
            for schritt in self.schritte
            if not self._im_katalog(schritt) and not self._in_der_liste(schritt)
        )
        self.assertEqual(
            [],
            offen,
            "diese Schritte sind weder im Zielkatalog als Beweis genannt noch in "
            "schritte-ohne-zielzeile.md eingeordnet — sie pruefen etwas, aber "
            f"niemand weiss wogegen: {offen}",
        )

    def test_die_liste_nennt_keinen_schritt_den_es_nicht_mehr_gibt(self):
        genannt = set(re.findall(r"`([a-z][a-z0-9 _.+/-]*)`", self.liste))
        # Nur Namen, die dem Muster eines Schrittes folgen; Dateipfade und
        # Feldnamen aus dem Fliesstext bleiben aussen vor.
        verdaechtig = {
            name
            for name in genannt
            if (name.startswith("ui_") or " " in name) and "/" not in name and "." not in name
        }
        verwaist = sorted(verdaechtig - self.schritte)
        self.assertEqual(
            [],
            verwaist,
            "die Liste nennt Schritte, die kein Harnisch mehr ausgibt — sie "
            f"behauptet damit eine Einordnung, die ins Leere zeigt: {verwaist}",
        )

    def test_die_zahl_in_der_liste_stimmt(self):
        """Die Kopfzeile nennt zwei Zahlen. Sie sind der Grund, warum es diese
        Datei gibt — eine Zahl ueber den eigenen Pruefstand, die niemand
        nachrechnet, war der Anlass. Also wird sie nachgerechnet."""
        treffer = re.search(
            r"\*\*Stand: (\d+) von (\d+) Schritten steht hier\.\*\*|"
            r"\*\*Stand: (\d+) von (\d+) Schritten stehen hier\.\*\*",
            self.liste,
        )
        self.assertIsNotNone(treffer, "die Kopfzeile nennt keinen Stand mehr")
        gruppen = [wert for wert in treffer.groups() if wert is not None]
        genannt_hier, genannt_gesamt = int(gruppen[0]), int(gruppen[1])

        tatsaechlich_hier = sum(1 for schritt in self.schritte if self._in_der_liste(schritt))
        self.assertEqual(
            (genannt_hier, genannt_gesamt),
            (tatsaechlich_hier, len(self.schritte)),
            f"die Kopfzeile sagt {genannt_hier} von {genannt_gesamt}, "
            f"tatsaechlich sind es {tatsaechlich_hier} von {len(self.schritte)}",
        )

    def test_kein_schritt_steht_in_beiden(self):
        doppelt = sorted(
            schritt
            for schritt in self.schritte
            if self._im_katalog(schritt) and self._in_der_liste(schritt)
        )
        self.assertEqual(
            [],
            doppelt,
            "diese Schritte bewachen laut Katalog eine Zielzeile und stehen "
            f"trotzdem in der Liste der Vertragsschritte: {doppelt}",
        )


if __name__ == "__main__":
    unittest.main()
