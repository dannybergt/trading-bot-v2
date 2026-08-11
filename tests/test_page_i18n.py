"""Guard, dass die Oberflaeche keine unuebersetzte Kopie traegt.

Der Anlass (2026-08-06): die UX-Direktive (`docs/admin/project-plan.md`,
"DE/EN parallel") ist verbindlich, die AdminPage war davon aber ausgenommen —
938 Zeilen mit genau zwei `t()`-Aufrufen.

Warum ein Browserschritt dafuer nicht reicht: die ui-regression sieht **einen**
Datenzustand. Der Konfigurations-Dialog oeffnet sich nur nach einem Klick, die
Kalibrierungs-Meldung erscheint nur nach einem Lauf, der Leerzustand der
Sicherungen nur ohne Sicherungen. Eine deutsche Ueberschrift auf `/admin`
beweist also genau die Ueberschrift — nicht die Seite. Dieser Test liest
stattdessen die Quelle und verlangt fuer **jeden** sichtbaren Textknoten und
jedes sichtbare Attribut einen Weg durch `t()`.

**Befund 2026-08-11, und der Grund fuer die Umschrift:** die erste Fassung
entfernte vor der Pruefung jeden `{...}`-Ausdruck. Damit verschwand auch jeder
bedingt gerenderte Zweig — `{x ? (<p>Asset mix</p>) : null}` — und dort steht
der meiste sichtbare Text. Der Guard konnte seinen eigenen Fehlerfall
strukturell nicht sehen: auf der AdminPage meldete er 0 Treffer, ueber alle
Seiten hinweg lagen **165** unuebersetzte Literale, davon 129 allein auf der
Analyse-Seite. `_jsx_text_nodes` laeuft jetzt als Zustandsmaschine, die in
Ausdruecke hineingeht, sobald sie Markup enthalten.

`STRICT_PAGES` sind die Seiten, die sauber sein **muessen**. `OFFENE_SEITEN`
sind die, die es noch nicht sind — mit einem Grund und ohne Zahl, denn eine
Zahl im Kommentar verrottet. Eine Seite, die in keiner der beiden Listen steht,
macht den Guard rot: eine neue Seite kann sich nicht still an der Uebersetzung
vorbeischleichen.

`test_i18n_bundles.py` prueft die andere Haelfte: dass zu jedem Schluessel beide
Sprachen existieren. Beide zusammen ergeben die Zusage.
"""
import json
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = PROJECT_ROOT / "src" / "frontend" / "src"
ADMIN_PAGE = FRONTEND_SRC / "pages" / "AdminPage.tsx"
I18N_DIR = FRONTEND_SRC / "i18n"
PAGES_DIR = FRONTEND_SRC / "pages"

# Seiten, die sauber sein muessen. Diese Liste ist die Ratsche: eine Seite
# kommt dazu, wenn sie uebersetzt ist, und faellt nie wieder heraus.
STRICT_PAGES = ("AdminPage.tsx", "DashboardPage.tsx")

# Seiten, die es noch nicht sind — mit Grund, ohne Zahl. Eine Zahl im Kommentar
# waere in einer Woche falsch, und der Guard soll nicht behaupten, was er nicht
# nachrechnet.
OFFENE_SEITEN = {
    "AnalysisPage.tsx": "der groesste Posten; Kennzahlen, Zonen, Erklaerbarkeit und Fundamentaldaten stehen fest auf Englisch",
    "AlertsPage.tsx": "ein Platzhalter-Attribut",
    "SettingsPage.tsx": "ein Platzhalter-Attribut",
    "LoginPage.tsx": "ein aria-label",
    "RegisterPage.tsx": "ein aria-label",
    "WatchlistsPage.tsx": "ein Trennzeichen-Text mit Bezeichner",
    "AutoExecutionPage.tsx": "Tabellenkoepfe der Ereignisliste",
    "DiscoverPage.tsx": "Tabellenkoepfe und Spaltenbeschriftungen",
    "NewsHubPage.tsx": "Anbieternamen als Beschriftung",
    "ScannerPage.tsx": "sauber, aber noch ohne Attributpruefung in der Ratsche",
    "OnboardingPage.tsx": "sauber, aber noch ohne Attributpruefung in der Ratsche",
    "PaperTradingPage.tsx": "noch nicht geprueft",
    "DocsPage.tsx": "noch nicht geprueft",
    "ForgotPasswordPage.tsx": "noch nicht geprueft",
    "ResetPasswordPage.tsx": "noch nicht geprueft",
}

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
    """Buchstaeblicher Text zwischen zwei Tags — auch in bedingten Zweigen.

    Drei Lagen werden unterschieden: Text zwischen Tags, das Innere eines Tags
    (Attribute), und Ausdruecke. Ein Ausdruck wird verworfen, sobald er kein
    Markup enthaelt; enthaelt er welches, wird ab dem ersten Tag weitergelesen.
    Der JS-Rumpf davor ("items.map((x) => (") faellt damit weg.
    """
    nodes: list[str] = []
    _walk_jsx(source, nodes)
    return nodes


# JS-Bindeglieder zwischen zwei Zweigen eines Ausdrucks (") : null",
# ") : other ? ("). Sie stehen zwischen zwei Tags und saehen sonst wie Text
# aus. In sichtbarer Kopie kommt keine dieser Folgen vor.
_JS_GLUE = re.compile(r"\)\s*:|\?\s*\(|===|=>|&&")


def _walk_jsx(source: str, out: list[str]) -> None:
    index, length = 0, len(source)
    buf: list[str] = []

    def flush():
        text = " ".join("".join(buf).split())
        buf.clear()
        if text and _LETTER_RUN.search(text) and not _JS_GLUE.search(text):
            out.append(text)

    while index < length:
        char = source[index]
        if char == "<":
            flush()
            index = _skip_tag(source, index)
            continue
        if char == "{":
            flush()
            inner, index = _read_braces(source, index)
            first_tag = inner.find("<")
            if first_tag != -1:
                _walk_jsx(inner[first_tag:], out)
            continue
        buf.append(char)
        index += 1
    # Bewusst kein flush am Ende: was nach dem letzten Tag steht, ist der
    # JS-Rumpf des Ausdrucks, kein sichtbarer Text. Sichtbarer Text steht in
    # JSX immer vor einem schliessenden Tag, also vor einem "<".
    buf.clear()


def _skip_tag(source: str, start: int) -> int:
    """Ueberspringt ein Tag inklusive Attributwerten und geschachtelter Braces."""
    index, length = start + 1, len(source)
    while index < length:
        char = source[index]
        if char in "\"'`":
            index = _skip_string(source, index)
            continue
        if char == "{":
            _, index = _read_braces(source, index)
            continue
        if char == ">":
            return index + 1
        index += 1
    return length


def _skip_string(source: str, start: int) -> int:
    quote = source[start]
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
            continue
        if source[index] == quote:
            return index + 1
        index += 1
    return len(source)


def _read_braces(source: str, start: int) -> tuple[str, int]:
    depth, index, length = 0, start, len(source)
    while index < length:
        char = source[index]
        if char in "\"'`":
            index = _skip_string(source, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : index], index + 1
        index += 1
    return source[start + 1 :], length


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


class PageI18nTests(unittest.TestCase):
    """Die Seiten aus `STRICT_PAGES` tragen keinen festen Text."""

    def _quelle(self, name: str) -> str:
        pfad = PAGES_DIR / name
        self.assertTrue(pfad.exists(), f"{pfad} is missing")
        return _strip_comments(pfad.read_text())

    def test_jede_seite_ist_eingeordnet(self):
        """Eine neue Seite steht in genau einer der beiden Listen.

        Ohne diesen Fall koennte eine ganze Seite unuebersetzt dazukommen, ohne
        dass irgendetwas rot wird — die Ratsche haette ein Loch in der Groesse
        einer Seite.
        """
        vorhanden = {pfad.name for pfad in PAGES_DIR.glob("*.tsx")}
        eingeordnet = set(STRICT_PAGES) | set(OFFENE_SEITEN)
        self.assertEqual(
            set(),
            vorhanden - eingeordnet,
            f"Seiten in keiner Liste: {sorted(vorhanden - eingeordnet)}",
        )
        self.assertEqual(
            set(),
            eingeordnet - vorhanden,
            f"gelistete Seiten, die es nicht gibt: {sorted(eingeordnet - vorhanden)}",
        )
        self.assertEqual(
            set(),
            set(STRICT_PAGES) & set(OFFENE_SEITEN),
            "eine Seite steht in beiden Listen",
        )

    def test_no_literal_text_nodes(self):
        """Kein sichtbarer Text steht buchstaeblich im JSX."""
        for name in STRICT_PAGES:
            with self.subTest(page=name):
                quelle = self._quelle(name)
                offenders: list[str] = []
                for span in _jsx_spans(quelle):
                    offenders += _jsx_text_nodes(span)
                self.assertEqual(
                    [],
                    offenders,
                    f"untranslated literal text in {name}: " + json.dumps(offenders[:20]),
                )

    def test_no_literal_visible_attributes(self):
        """placeholder/title/aria-label tragen keinen festen Text."""
        for name in STRICT_PAGES:
            with self.subTest(page=name):
                offenders = _visible_attr_literals(self._quelle(name))
                self.assertEqual(
                    [],
                    offenders,
                    f"untranslated attribute copy in {name}: " + json.dumps(offenders[:20]),
                )

    def test_no_literal_browser_dialogs(self):
        """alert/confirm/prompt bekommen ihren Text aus dem Bundle.

        Diese drei sind der Sonderfall: sie stehen nicht im JSX, sind aber das
        Sichtbarste ueberhaupt — ein modaler Dialog. In der alten Fassung
        fragten sie auf Englisch nach einem neuen Passwort.
        """
        for name in STRICT_PAGES:
            with self.subTest(page=name):
                offenders = _dialog_literals(self._quelle(name))
                self.assertEqual(
                    [],
                    offenders,
                    f"untranslated browser dialog copy in {name}: " + json.dumps(offenders[:20]),
                )

    def test_referenced_keys_exist_in_both_bundles(self):
        """Jeder `t("admin...")`- und `t("dashboard...")`-Aufruf trifft einen Schluessel.

        i18next rendert einen unbekannten Pfad als sich selbst — ein Tippfehler
        zeigt dem Nutzer `admin.users.colEmial` und faellt sonst nirgends auf.
        """
        self.source = "".join(self._quelle(name) for name in STRICT_PAGES)
        referenced = sorted(
            set(re.findall(r't\(\s*"((?:admin|dashboard|tooltips\.admin)[^"]*)"', self.source))
        )
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
