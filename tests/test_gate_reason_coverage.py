"""Jeder Ablehnungsgrund der Automatik braucht einen erklaerenden Satz.

Produktvision Punkt 6: "Erklaerbarkeit ist Kern, nicht Beiwerk". Fuer die
Automatik hiess das bis 2026-08-06 gar nichts — `POST
/api/auto-execution/proposals/evaluate` begruendet jede Ablehnung einzeln und
wurde von keiner Seite aufgerufen. Der einzige Ort, an dem ein Nutzer
nachvollziehen kann, warum nicht gekauft wird, war unerreichbar.

Jetzt zeigt die Analyse-Seite die Gate-Kette. Damit entsteht eine neue
Gefahr: ein im Backend ergaenzter Grund erscheint in der Oberflaeche als
roher Code (`net_yield_gate_blocked`), weil die Uebersetzung fehlt — technisch
gruen, fuer den Nutzer wertlos.

Dieser Guard liest die Gruende **aus dem Backend-Quelltext** statt sie zu
pflegen und verlangt fuer jeden einen Satz in beiden Sprachen. Ein neuer Grund
faellt damit beim Anlegen auf, nicht beim Nutzer.
"""
import ast
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_I18N = PROJECT_ROOT / "src" / "frontend" / "src" / "i18n"

BACKEND_ROOT = PROJECT_ROOT / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    # Im Test-Container liegt das Paket unter /app/app.
    BACKEND_ROOT = PROJECT_ROOT
AUTO_EXECUTION = BACKEND_ROOT / "app" / "auto_execution.py"


def _reason_codes() -> set[str]:
    """Alle Gruende und Halt-Ausloeser aus auto_execution.py.

    Per AST statt per Regex und ohne gepflegte Liste: sonst waere dieser Guard
    genau so aktuell wie die Liste, die er bewachen soll.
    """
    tree = ast.parse(AUTO_EXECUTION.read_text())
    codes: set[str] = set()

    for node in ast.walk(tree):
        # reasons.append("...") / triggers.append("...")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"reasons", "triggers", "halt_triggers"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            codes.add(node.args[0].value)

        # RiskDecision(allowed=False, reasons=["..."])
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RiskDecision"
        ):
            for keyword in node.keywords:
                if keyword.arg in {"reasons", "halt_triggers"} and isinstance(
                    keyword.value, ast.List
                ):
                    for element in keyword.value.elts:
                        if isinstance(element, ast.Constant) and isinstance(
                            element.value, str
                        ):
                            codes.add(element.value)

    return codes


class GateReasonCoverageTests(unittest.TestCase):
    def test_the_backend_actually_declares_reason_codes(self):
        """Sicherung gegen einen Guard, der nichts mehr findet und trotzdem gruen ist."""
        codes = _reason_codes()
        self.assertGreaterEqual(
            len(codes),
            10,
            f"nur {len(codes)} Gruende gefunden -- die Extraktion greift "
            "vermutlich nicht mehr, und dieser Guard bewacht dann nichts",
        )

    def test_every_reason_has_a_sentence_in_both_languages(self):
        codes = _reason_codes()
        for lang in ("en", "de"):
            data = json.loads((FRONTEND_I18N / f"{lang}.json").read_text())
            translated = data["analysis"]["gates"]["reason"]
            missing = sorted(code for code in codes if code not in translated)
            self.assertEqual(
                [],
                missing,
                f"[{lang}] diese Ablehnungsgruende erscheinen in der "
                "Oberflaeche als roher Code statt als Erklaerung: "
                + ", ".join(missing),
            )

    def test_no_stale_sentences_without_a_backend_reason(self):
        """Der umgekehrte Fall: ein Satz, den nie jemand ausloest."""
        codes = _reason_codes()
        data = json.loads((FRONTEND_I18N / "en.json").read_text())
        translated = set(data["analysis"]["gates"]["reason"])
        stale = sorted(translated - codes)
        self.assertEqual(
            [],
            stale,
            "diese Erklaerungen gehoeren zu keinem Grund im Backend mehr: "
            + ", ".join(stale),
        )


if __name__ == "__main__":
    unittest.main()
