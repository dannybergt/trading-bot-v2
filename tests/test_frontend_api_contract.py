"""Guard the contract between the frontend API client and its call sites.

Der Anlass (2026-08-05): `apiFetch` serialisiert seinen Body selbst. Zwei
Aufrufer in `AutoExecutionPage.tsx` uebergaben trotzdem `JSON.stringify(...)`.
Der Body war damit ein JSON-*String* statt eines Objekts, die Endpunkte
erwarten `dict` — jedes Speichern der Risikolimits und **jeder Druck auf den
Not-Halt-Schalter** lief in 422.

Warum das monatelang unentdeckt blieb: `FetchOptions.body` ist `unknown`
typisiert, damit beliebige Nutzlasten durchgehen. TypeScript kann den Fehler
also strukturell nicht sehen, und keine Regression rief die beiden Endpunkte
auf. Ein Test, der die Endpunkte mit einem *korrekten* Body aufruft, haette
den Fehler ebenfalls nicht gefunden — er sitzt im Aufrufer, nicht im Endpunkt.

Diese Datei prueft deshalb die Verdrahtung statt der Nutzlast: sie liest die
Serialisierungszusage aus `client.ts` und haelt danach jeden Aufrufer dagegen.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = PROJECT_ROOT / "src" / "frontend" / "src"
API_CLIENT = FRONTEND_SRC / "api" / "client.ts"

# Aufrufe, die bewusst am Client vorbei mit dem nackten fetch() arbeiten und
# darum selbst serialisieren muessen. Aktuell genau einer: der Token-Refresh
# laeuft vor/ohne Authorization-Header und kann apiFetch nicht benutzen, weil
# apiFetch bei 401 selbst wieder den Refresh anstossen wuerde (Rekursion).
RAW_FETCH_ALLOWED = {
    ("api/client.ts", "attemptRefresh"),
}


def _source_files() -> list[Path]:
    return sorted(
        path
        for path in FRONTEND_SRC.rglob("*.ts*")
        if path.suffix in {".ts", ".tsx"} and "node_modules" not in path.parts
    )


def _rel(path: Path) -> str:
    return path.relative_to(FRONTEND_SRC).as_posix()


class ApiClientSerialisationContractTests(unittest.TestCase):
    def test_client_serialises_the_body_itself(self):
        """Die Zusage, gegen die alle Aufrufer geprueft werden.

        Faellt dieser Test, ist nicht der Aufrufer falsch, sondern die
        Grundannahme dieser Datei — dann gehoeren die Aufrufer angepasst und
        dieser Test mit ihnen.
        """
        source = API_CLIENT.read_text()
        self.assertRegex(
            source,
            r"body:\s*body === undefined \? undefined : JSON\.stringify\(body\)",
            "apiFetch serialisiert den Body nicht mehr selbst -- die Annahme "
            "dieser Guard-Datei stimmt nicht mehr",
        )

    def test_no_call_site_serialises_twice(self):
        """Kein apiFetch-Aufrufer darf seinen Body vorserialisieren."""
        offenders: list[str] = []
        for path in _source_files():
            source = path.read_text()
            if "apiFetch" not in source:
                continue
            for match in re.finditer(r"body:\s*JSON\.stringify\(", source):
                line_no = source.count("\n", 0, match.start()) + 1
                # Der Refresh-Pfad in client.ts benutzt das nackte fetch().
                if (_rel(path), "attemptRefresh") in RAW_FETCH_ALLOWED and _in_raw_fetch(
                    source, match.start()
                ):
                    continue
                offenders.append(f"{_rel(path)}:{line_no}")

        self.assertEqual(
            [],
            offenders,
            "apiFetch serialisiert den Body bereits selbst. Diese Aufrufer "
            "serialisieren ein zweites Mal und schicken damit einen "
            "JSON-String statt eines Objekts (FastAPI antwortet 422): "
            + ", ".join(offenders),
        )


def _in_raw_fetch(source: str, index: int) -> bool:
    """Steht die Fundstelle in einem direkten fetch()-Aufruf statt in apiFetch?

    Bewusst grob: es genuegt, den naechsten Aufruf oberhalb der Fundstelle zu
    bestimmen. Steht dort `fetch(` ohne vorangestelltes `api`, serialisiert der
    Aufrufer zu Recht selbst.
    """
    prefix = source[:index]
    last_api_fetch = prefix.rfind("apiFetch(")
    last_raw_fetch = max(prefix.rfind(" fetch("), prefix.rfind("await fetch("))
    return last_raw_fetch > last_api_fetch


if __name__ == "__main__":
    unittest.main()
