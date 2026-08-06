"""Guard that the admin surface carries no untranslated copy.

Der Anlass: die UX-Direktive (`docs/admin/project-plan.md`, "DE/EN parallel")
ist verbindlich, die AdminPage war davon aber ausgenommen — 938 Zeilen mit
genau zwei `t()`-Aufrufen fuer Formularlabels. Der Rest, inklusive aller
Tabellenkoepfe, Schaltflaechen und der Erklaertexte zur
Plattform-Konfiguration, stand fest auf Englisch im JSX.

Warum ein Browserschritt dafuer nicht reicht: die ui-regression sieht **einen**
Datenzustand (so benannt am 2026-08-06). Der Konfigurations-Dialog oeffnet sich
nur nach einem Klick, die Kalibrierungs-Meldung erscheint nur nach einem Lauf,
der Leerzustand der Sicherungen nur ohne Sicherungen. Eine deutsche Ueberschrift
auf `/admin` beweist also genau die Ueberschrift — nicht die Seite. Dieser Test
liest stattdessen die Quelle und verlangt fuer **jeden** sichtbaren Textknoten
und jedes sichtbare Attribut einen Weg durch `t()`.

`test_i18n_bundles.py` prueft die andere Haelfte: dass zu jedem Schluessel
beide Sprachen existieren. Beide zusammen ergeben die Zusage.
"""
import json
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = PROJECT_ROOT / "src" / "frontend" / "src"
ADMIN_PAGE = FRONTEND_SRC / "pages" / "AdminPage.tsx"
I18N_DIR = FRONTEND_SRC / "i18n"

# Attribute, deren Wert der Nutzer liest. `placeholder` und `title` stehen
# sichtbar in der Oberflaeche, `aria-label` liest der Screenreader vor.
USER_VISIBLE_ATTRS = ("placeholder", "title", "aria-label")

# Zeichenfolgen, die in keiner Sprache uebersetzt werden: reine Symbole,
# Trennzeichen und Waehrungs-/Einheitenzeichen. Alles mit zwei aufeinander
# folgenden Buchstaben faellt bewusst NICHT hierunter.
_LETTER_RUN = re.compile(r"[A-Za-zÀ-ɏ]{2,}")


def _strip_comments(source: str) -> str:
    """Entfernt Block- und Zeilenkommentare.

    Ohne das melden die deutschen Kommentare in der Datei sich selbst als
    unuebersetzten Text — der Test wuerde seine eigene Dokumentation anzeigen.
    """
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    source = re.sub(r"^[ \t]*//.*$", " ", source, flags=re.M)
    return source


def _jsx_spans(source: str) -> list[str]:
    """Nur die `return (...)`-Bloecke — dort und nur dort steht Markup.

    Ohne diese Eingrenzung liest der Test auch Typdeklarationen wie
    `Record<string, string> = ...` als Textknoten: zwischen dem `>` des
    Generics und dem naechsten `<` steht buchstaeblich etwas.
    """
    spans: list[str] = []
    for match in re.finditer(r"\breturn\s*\(", source):
        depth = 0
        start = match.end() - 1
        for index in range(start, len(source)):
            char = source[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    spans.append(source[start + 1 : index])
                    break
    return spans


def _strip_expressions(source: str) -> str:
    """Ersetzt JSX-Ausdruecke `{...}` durch einen Platzhalter.

    Alles in geschweiften Klammern ist Code, nicht Text: dort steht entweder
    ein `t(...)`-Aufruf oder ein Wert aus dem Backend. Uebrig bleibt genau das,
    was buchstaeblich im Markup steht — die Klasse, die uebersetzt gehoert.
    Die Verschachtelung wird mitgezaehlt, sonst endet die Ersetzung beim
    ersten inneren `}`.
    """
    out: list[str] = []
    depth = 0
    for char in source:
        if char == "{":
            depth += 1
            if depth == 1:
                out.append("\x00")
            continue
        if char == "}":
            if depth > 0:
                depth -= 1
                continue
        if depth == 0:
            out.append(char)
    return "".join(out)


def _jsx_text_nodes(source: str) -> list[str]:
    """Buchstaeblicher Text zwischen zwei Tags."""
    nodes: list[str] = []
    for chunk in re.split(r"<[^>]*>", source):
        text = chunk.replace("\x00", " ").strip()
        if text and _LETTER_RUN.search(text):
            nodes.append(" ".join(text.split()))
    return nodes


def _visible_attr_literals(source: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for attr in USER_VISIBLE_ATTRS:
        for match in re.finditer(rf'\b{re.escape(attr)}="([^"]*)"', source):
            value = match.group(1).strip()
            if value and _LETTER_RUN.search(value):
                found.append((attr, value))
    return found


def _dialog_literals(source: str) -> list[str]:
    """String-Literale, die direkt in einen Browserdialog gehen."""
    found: list[str] = []
    for match in re.finditer(
        r"window\.(?:alert|confirm|prompt)\(\s*([`\"'])(.*?)\1", source, flags=re.S
    ):
        value = match.group(2).strip()
        if value and _LETTER_RUN.search(value):
            found.append(value)
    return found


class AdminPageI18nTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(ADMIN_PAGE.exists(), f"{ADMIN_PAGE} is missing")
        self.raw = ADMIN_PAGE.read_text()
        self.source = _strip_comments(self.raw)

    def test_no_literal_text_nodes(self):
        """Kein sichtbarer Text steht buchstaeblich im JSX."""
        offenders: list[str] = []
        for span in _jsx_spans(self.source):
            offenders += _jsx_text_nodes(_strip_expressions(span))
        self.assertEqual(
            [],
            offenders,
            "untranslated literal text in AdminPage.tsx: " + json.dumps(offenders[:20]),
        )

    def test_no_literal_visible_attributes(self):
        """placeholder/title/aria-label tragen keinen festen Text."""
        offenders = _visible_attr_literals(self.source)
        self.assertEqual(
            [],
            offenders,
            "untranslated attribute copy in AdminPage.tsx: " + json.dumps(offenders[:20]),
        )

    def test_no_literal_browser_dialogs(self):
        """alert/confirm/prompt bekommen ihren Text aus dem Bundle.

        Diese drei sind der Sonderfall: sie stehen nicht im JSX, sind aber das
        Sichtbarste ueberhaupt — ein modaler Dialog. In der alten Fassung
        fragten sie auf Englisch nach einem neuen Passwort.
        """
        offenders = _dialog_literals(self.source)
        self.assertEqual(
            [],
            offenders,
            "untranslated browser dialog copy: " + json.dumps(offenders[:20]),
        )

    def test_referenced_keys_exist_in_both_bundles(self):
        """Jeder `t("admin...")`-Aufruf der Seite trifft einen echten Schluessel.

        i18next rendert einen unbekannten Pfad als sich selbst — ein Tippfehler
        zeigt dem Nutzer `admin.users.colEmial` und faellt sonst nirgends auf.
        """
        referenced = sorted(set(re.findall(r't\(\s*"((?:admin|tooltips\.admin)[^"]*)"', self.source)))
        # Die Achsenbeschriftungen stehen als Konstante in einer Map und
        # laufen ueber `t(COMPOSITE_AXIS_KEY[axis])` — der regulaere Ausdruck
        # oben sieht sie nicht, weil dort kein Literal im Aufruf steht.
        referenced += sorted(set(re.findall(r'"(admin\.composite\.axis\.[^"]+)"', self.source)))
        self.assertGreater(len(referenced), 50, "expected the page to be fully wired")

        for language in ("de.json", "en.json"):
            bundle = json.loads((I18N_DIR / language).read_text())
            missing = []
            for key in referenced:
                node = bundle
                for part in key.split("."):
                    if not isinstance(node, dict) or part not in node:
                        missing.append(key)
                        break
                    node = node[part]
                else:
                    if not isinstance(node, str) or not node.strip():
                        missing.append(key)
            self.assertEqual([], missing, f"missing/blank in {language}: {missing[:20]}")


if __name__ == "__main__":
    unittest.main()
