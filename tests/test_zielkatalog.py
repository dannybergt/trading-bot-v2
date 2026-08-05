"""Guard fuer den Zielkatalog.

Der Katalog (`docs/verification/zielkatalog.md`) ist der Massstab, gegen den der
`verifier` nachweist, ob das Produkt sein Ziel erreicht. Ein Massstab, der still
veraltet, ist schlimmer als keiner: er behauptet Abdeckung, die es nicht gibt.

Dieser Guard laeuft in Sekunden und braucht keinen Stack. Er prueft die
Eigenschaften, die der Katalog haben muss, damit ein Lauf ueberhaupt aussagekraeftig
sein kann — nicht, ob die Ziele erreicht sind (das ist Sache des Laufs).

Bewusst NICHT geprueft: ob ein Beweisschritt auch wirklich das beweist, was die Zeile
behauptet. Das kann keine Textpruefung leisten; dafuer gibt es die Negativkontrolle
im Lauf.
"""
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KATALOG = REPO_ROOT / "docs" / "verification" / "zielkatalog.md"

# Marker, die eine Zeile als "hat noch keinen Beweis" ausweisen. Sie sind erlaubt —
# eine ehrliche Luecke ist besser als ein erfundener Beweisschritt — aber sie duerfen
# nicht als Beweis durchgehen.
LUECKEN_MARKER = ("Beweisschritt fehlt", "offen bis zur Operationalisierung", "OFFEN")


def _tabellenzeilen(text: str) -> list[list[str]]:
    """Alle Datenzeilen aller Markdown-Tabellen als Spaltenlisten."""
    zeilen = []
    for roh in text.splitlines():
        roh = roh.strip()
        if not roh.startswith("|") or not roh.endswith("|"):
            continue
        spalten = [s.strip() for s in roh.strip("|").split("|")]
        # Kopf- und Trennzeilen ueberspringen
        if not spalten or spalten[0] in ("ID", "") or set(spalten[0]) <= set("-: "):
            continue
        zeilen.append(spalten)
    return zeilen


class ZielkatalogTests(unittest.TestCase):
    def setUp(self):
        if not KATALOG.exists():
            self.fail(
                f"{KATALOG.relative_to(REPO_ROOT)} fehlt — ohne Zielkatalog kann der "
                "verifier nichts nachweisen und meldet NICHT DURCHFUEHRBAR"
            )
        self.text = KATALOG.read_text(encoding="utf-8")
        self.zeilen = _tabellenzeilen(self.text)

    def test_katalog_hat_kernkriterien(self):
        # Ohne Kernzeilen gibt es keine Bruchzahl und damit kein Gesamturteil.
        kern = [z for z in self.zeilen if z[-1] == "Kern"]
        self.assertGreaterEqual(
            len(kern), 5, f"zu wenige Kernkriterien im Katalog: {len(kern)}"
        )

    def test_ids_sind_eindeutig(self):
        # Append-only heisst: eine ID steht fuer genau eine Zusage, dauerhaft.
        ids = [z[0] for z in self.zeilen if re.fullmatch(r"TBV2-Z\d+", z[0])]
        doppelt = {i for i in ids if ids.count(i) > 1}
        self.assertFalse(doppelt, f"doppelt vergebene IDs: {sorted(doppelt)}")
        self.assertGreaterEqual(len(ids), 10, "Katalog wirkt unvollstaendig")

    def test_jede_zeile_hat_zielsatz_und_kriterium(self):
        for zeile in self.zeilen:
            if not re.fullmatch(r"TBV2-Z\d+", zeile[0]):
                continue
            with self.subTest(id=zeile[0]):
                self.assertTrue(zeile[1].strip(), "Zielsatz fehlt")
                self.assertTrue(zeile[2].strip(), "beobachtbares Kriterium fehlt")

    def test_zielsaetze_nennen_ihre_quelle(self):
        # Ein Zielsatz ohne Quellenverweis ist eine Behauptung des Katalogs statt
        # eine Zusage des Produkts. Erweiterungen sind ausgenommen: sie leiten sich
        # aus dem Betrieb ab, nicht aus der Produktvision.
        ohne_quelle = []
        for zeile in self.zeilen:
            if not re.fullmatch(r"TBV2-Z\d+", zeile[0]) or zeile[-1] != "Kern":
                continue
            # Zulaessige Quellen: eine Stelle im Plan (datei:zeile), ein ADR, die
            # UX-Direktive oder ein Paragraph der Constitution. Der erste Entwurf
            # dieser Regel liess nur die ersten drei zu und hat damit TBV2-Z11
            # verworfen, obwohl "§6.2 Autorisierung" eine voellig legitime — und
            # stabilere — Quelle ist als eine Zeilennummer. Korrigiert wurde die
            # Regel, nicht die Zeile.
            if not re.search(
                r"[\w./-]+\.md:\d+|ADR \d{4}-\d{2}-\d{2}|UX-Direktive|§\d+(\.\d+)?", zeile[1]
            ):
                ohne_quelle.append(zeile[0])
        self.assertFalse(
            ohne_quelle,
            f"Kernzeilen ohne Quellenverweis (datei:zeile / ADR / UX-Direktive / §): {ohne_quelle}",
        )

    def test_referenzierte_harnische_existieren(self):
        # Ein Beweisschritt, der auf eine geloeschte Datei zeigt, ist kein Beweis.
        # Faellt die Praemisse weg, meldet sich der Guard, statt still gruen zu bleiben.
        referenzen = set(re.findall(r"`(tests/[\w.\-/]+|ops/[\w.\-/]+)`", self.text))
        self.assertTrue(referenzen, "Katalog referenziert keinen einzigen Harnisch")
        fehlend = [r for r in sorted(referenzen) if not (REPO_ROOT / r).exists()]
        self.assertFalse(fehlend, f"referenzierte Harnische fehlen: {fehlend}")

    def test_beweis_token_kommen_in_den_harnischen_vor(self):
        # Der eigentliche Rott-Schutz: ein Token, das kein Harnisch mehr ausgibt,
        # kann nichts belegen. Wird ein Schritt umbenannt, faellt das hier auf —
        # nicht erst, wenn jemand dem Bericht glaubt.
        ui = (REPO_ROOT / "tests" / "run-ui-regression.mjs").read_text(encoding="utf-8")
        api = (REPO_ROOT / "tests" / "run-api-regression.sh").read_text(encoding="utf-8")
        harnisch_text = ui + api

        tokens = set(re.findall(r"`(ui_[a-z_]+)`", self.text))
        self.assertTrue(tokens, "Katalog nennt kein einziges ui_*-Beweis-Token")
        unbekannt = [t for t in sorted(tokens) if t not in harnisch_text]
        self.assertFalse(
            unbekannt,
            f"Beweis-Token, die kein Harnisch mehr ausgibt: {unbekannt}",
        )

    def test_luecken_sind_als_luecken_markiert_nicht_leer(self):
        # Eine Kernzeile ohne Beweisschritt ist erlaubt — aber sie muss es SAGEN.
        # Eine leere Zelle laese sich als "geprueft" missverstehen.
        for zeile in self.zeilen:
            if not re.fullmatch(r"TBV2-Z\d+", zeile[0]) or zeile[-1] != "Kern":
                continue
            beweis = zeile[4]
            with self.subTest(id=zeile[0]):
                self.assertTrue(beweis.strip(), "Beweisschritt-Zelle ist leer")
                if any(m in beweis for m in LUECKEN_MARKER):
                    continue
                self.assertTrue(
                    re.search(r"`[^`]+`|api-regression|ui-regression", beweis),
                    "Beweisschritt nennt weder Kommando noch Harnisch-Token",
                )


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
