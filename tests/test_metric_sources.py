"""Wachen fuer die Herkunft jeder angezeigten Kennzahl (TBV2-Z06 b).

Drei Klassen von Fehlern sollen hier auffallen, bevor sie jemand sieht:

1. **Eine Kennzahlen-Sektion ohne Herkunftshinweis.** Der Katalogsatz
   lautet "jede angezeigte Kennzahl nennt Provider und Zeitstempel" — eine
   neue Sektion, die das nicht tut, macht die Zeile still unwahr. Der
   Guard zaehlt die Sektionen der Analyse-Seite selbst ab, statt sich auf
   eine gepflegte Liste zu verlassen; wer eine neue baut, muss sie
   entweder verdrahten oder hier begruenden.
2. **Ein erfundener Zeitstempel.** Ein Eintrag darf keinen Zeitpunkt
   nennen, ohne dessen Bedeutung zu nennen, und keine Bedeutung ohne
   Zeitpunkt.
3. **Zwei Antworten auf dieselbe Frage.** Was die Datenqualitaets-Karte
   als `full`/`partial` fuehrt, muss in der Herkunftskarte verfuegbar
   sein — und umgekehrt. Genau diese Sorte Widerspruch (Regel K) hat die
   Onboarding-Karte am 2026-08-06 zu Fall gebracht.
"""
import os
import re
import sys
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

REPO_ROOT = Path(__file__).resolve().parents[1]
# Im Container liegt das Paket direkt unter /app, im Checkout unter
# src/backend — dieselbe Aufloesung wie in den uebrigen Tests.
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = REPO_ROOT
sys.path.insert(0, str(BACKEND_ROOT))

from app import data_quality_service as dq  # noqa: E402
from app import metric_sources as ms  # noqa: E402

ANALYSIS_PAGE = REPO_ROOT / "src" / "frontend" / "src" / "pages" / "AnalysisPage.tsx"

# Komponenten der Analyse-Seite, die bewusst keinen eigenen
# Herkunftshinweis tragen — mit dem Grund, aus dem das richtig ist.
SOURCE_TIP_EXEMPT = {
    "DataQualitySection": "ist selbst der Herkunfts- und Vertrauensbericht",
    "RatingCard": "Unterkarte von ResearchDepthSection, deren Hinweis sie mit abdeckt",
}


def _page_source() -> str:
    return ANALYSIS_PAGE.read_text(encoding="utf-8")


def _component_bodies(source: str) -> dict[str, str]:
    """Rumpf jeder `function XxxSection|XxxCard` bis zur naechsten Funktion."""
    starts = [
        (match.group(1), match.start())
        for match in re.finditer(r"^function ([A-Za-z]+(?:Section|Card))\(", source, re.MULTILINE)
    ]
    bodies: dict[str, str] = {}
    for index, (name, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(source)
        bodies[name] = source[start:end]
    return bodies


class SourceMapContractTests(unittest.TestCase):
    def test_every_key_is_rendered_somewhere(self):
        page = _page_source()
        used = set(re.findall(r'sourceKey="([a-z_]+)"', page))
        missing = sorted(set(ms.DISPLAY_SOURCE_KEYS) - used)
        self.assertEqual(
            [],
            missing,
            f"Herkunftskarte fuehrt Schluessel, die keine Sektion anzeigt: {missing}",
        )

    def test_no_frontend_key_is_unknown_to_the_backend(self):
        page = _page_source()
        used = set(re.findall(r'sourceKey="([a-z_]+)"', page))
        unknown = sorted(used - set(ms.DISPLAY_SOURCE_KEYS))
        self.assertEqual(
            [],
            unknown,
            "Die Analyse-Seite fragt Herkunft unter einem Schluessel ab, den das "
            f"Backend nicht kennt (das Tooltip bliebe leer): {unknown}",
        )

    def test_every_metric_section_states_its_source(self):
        bodies = _component_bodies(_page_source())
        self.assertGreater(len(bodies), 15, "Die Sektionen der Analyse-Seite wurden nicht erkannt")
        without = sorted(
            name
            for name, body in bodies.items()
            if "<SourceTip" not in body and name not in SOURCE_TIP_EXEMPT
        )
        self.assertEqual(
            [],
            without,
            "Kennzahlen-Sektion ohne Herkunftshinweis (TBV2-Z06 b): "
            f"{without}. Entweder <SourceTip> ergaenzen oder in SOURCE_TIP_EXEMPT "
            "mit Grund eintragen.",
        )

    def test_exemptions_still_exist(self):
        # Eine Ausnahme fuer eine geloeschte Komponente verdeckt spaeter eine
        # echte Luecke, weil niemand mehr prueft, wofuer sie stand.
        bodies = _component_bodies(_page_source())
        stale = sorted(set(SOURCE_TIP_EXEMPT) - set(bodies))
        self.assertEqual([], stale, f"Ausnahme ohne Komponente: {stale}")


class SourceEntryInvariantTests(unittest.TestCase):
    def test_no_timestamp_without_meaning_and_no_meaning_without_timestamp(self):
        entries = ms.build_source_map(
            asset_class="stock",
            research_payload=_full_research(),
            stock_payload=_full_stock(),
        )
        self.assertTrue(entries)
        for entry in entries:
            with self.subTest(key=entry["key"]):
                self.assertIn(entry["asOfKind"], ms.ASOF_KINDS)
                if entry["asOf"] is None:
                    self.assertEqual(ms.ASOF_UNKNOWN, entry["asOfKind"])
                else:
                    self.assertNotEqual(ms.ASOF_UNKNOWN, entry["asOfKind"])

    def test_unavailable_entry_names_no_provider(self):
        entries = ms.build_source_map(asset_class="stock", research_payload={}, stock_payload={})
        self.assertTrue(entries)
        for entry in entries:
            with self.subTest(key=entry["key"]):
                if not entry["available"]:
                    self.assertIsNone(entry["asOf"])

    def test_empty_payloads_invent_nothing(self):
        entries = ms.build_source_map(asset_class="stock", research_payload={}, stock_payload={})
        by_key = {entry["key"]: entry for entry in entries}
        for key in ("prediction", "composite", "earnings_calls", "sec_filings", "news"):
            with self.subTest(key=key):
                self.assertFalse(by_key[key]["available"])
                self.assertIsNone(by_key[key]["asOf"])
                self.assertIsNone(by_key[key]["provider"])

    def test_asset_class_gates_the_crypto_entry(self):
        stock_keys = {e["key"] for e in ms.build_source_map(asset_class="stock", research_payload={}, stock_payload={})}
        crypto_keys = {e["key"] for e in ms.build_source_map(asset_class="crypto", research_payload={}, stock_payload={})}
        self.assertNotIn("crypto_metrics", stock_keys)
        self.assertIn("crypto_metrics", crypto_keys)

    def test_newest_date_wins_over_list_order(self):
        # Die alte Fassung nahm das erste Element und unterstellte damit eine
        # Sortierung, die kein Anbietervertrag zusichert.
        rows = [{"date": "2026-01-05"}, {"date": "2026-07-31"}, {"date": "2026-03-02"}]
        self.assertEqual("2026-07-31", ms._newest_date(rows))

    def test_synthetic_bars_name_no_provider(self):
        entries = ms.build_source_map(
            asset_class="stock",
            research_payload={},
            stock_payload={"synthetic": True, "chart_data": [{"date": "2026-08-01", "close": 1.0}]},
        )
        price = next(entry for entry in entries if entry["key"] == "price_history")
        self.assertFalse(price["available"])
        self.assertIsNone(price["provider"])
        self.assertIsNone(price["asOf"])

    def test_list_shaped_bars_do_not_crash_the_map(self):
        # `getattr(value, "index")` trifft an einer Liste die *Methode*
        # `list.index` — der Zugriff starb dort an `len(...)`. Aufgefallen
        # ist das an einem bestehenden Datenqualitaets-Test, nicht an einem
        # neuen: beide Payload-Formen erreichen diese Stelle wirklich.
        entries = ms.build_source_map(
            asset_class="stock",
            research_payload={},
            stock_payload={"data": [{"date": "2026-08-03"}, {"date": "2026-08-04"}]},
        )
        price = next(entry for entry in entries if entry["key"] == "price_history")
        self.assertEqual("2026-08-04", price["asOf"])
        self.assertTrue(price["available"])

    def test_fetch_time_is_not_dressed_up_as_data_age(self):
        entries = ms.build_source_map(
            asset_class="stock",
            research_payload={
                "fundamentals": {"sector": "Technology"},
                "fundamentalsFetchedAt": "2026-08-06T09:00:00+00:00",
                "fundamentalsSource": "FMP",
            },
            stock_payload={},
        )
        fundamentals = next(entry for entry in entries if entry["key"] == "fundamentals")
        self.assertEqual("FMP", fundamentals["provider"])
        self.assertEqual(ms.ASOF_FETCH, fundamentals["asOfKind"])

    def test_empty_sector_shell_is_not_a_source(self):
        # `_empty_payload` fuellt `sectorEtf`, sobald der Sektorname passte —
        # darauf zu pruefen haette jede leere Antwort als Quelle ausgegeben.
        entries = ms.build_source_map(
            asset_class="stock",
            research_payload={
                "sectorContext": {
                    "symbol": "AAPL",
                    "sector": "Technology",
                    "sectorEtf": "XLK",
                    "relativeStrength": {"spy": {"peer": "SPY", "return1m": None, "alpha1m": None}},
                    "correlation": {"benchmark": "SPY", "correlation": None, "beta": None},
                }
            },
            stock_payload={},
        )
        sector = next(entry for entry in entries if entry["key"] == "sector_context")
        self.assertFalse(sector["available"])


class SourceMapAgreesWithConfidenceTests(unittest.TestCase):
    """Regel K: Karte und Herkunftshinweis widersprechen sich nie."""

    #: Schluessel, die beide Seiten fuehren.
    SHARED = (
        "price_history",
        "fundamentals",
        "research_depth",
        "research_signals",
        "earnings_calls",
        "social_sentiment",
        "options_flow",
        "news",
        "macro_context",
    )

    def _report(self, research, stock, asset_class="stock"):
        return dq.evaluate_symbol_data_quality(
            symbol="AAPL",
            asset_class=asset_class,
            research_payload=research,
            stock_payload=stock,
        )

    def test_full_payload_agrees(self):
        self._assert_agreement(self._report(_full_research(), _full_stock()))

    def test_empty_payload_agrees(self):
        self._assert_agreement(self._report({}, {}))

    def _assert_agreement(self, report):
        fields = {entry["key"]: entry["confidence"] for entry in report["fields"]}
        sources = {entry["key"]: entry for entry in report["sources"]}
        for key in self.SHARED:
            if key not in fields or key not in sources:
                continue
            with self.subTest(key=key):
                graded_available = fields[key] in (dq.FULL, dq.PARTIAL)
                self.assertEqual(
                    graded_available,
                    sources[key]["available"],
                    f"Datenqualitaets-Karte sagt '{fields[key]}' fuer {key}, die "
                    f"Herkunftskarte sagt available={sources[key]['available']}",
                )

    def test_report_carries_the_source_map(self):
        report = self._report(_full_research(), _full_stock())
        self.assertIn("sources", report)
        self.assertEqual(
            sorted(entry["key"] for entry in report["sources"]),
            sorted(key for key in ms.DISPLAY_SOURCE_KEYS if key != "crypto_metrics"),
        )

    def test_fundamentals_source_is_not_guessed_as_yfinance(self):
        # Vorher stand fuer jeden FMP-Treffer "yfinance" in der Karte, weil
        # der Research-Payload die Herkunftsflags gar nicht mitfuehrte.
        research = _full_research()
        research["fundamentalsSource"] = "FMP"
        report = self._report(research, _full_stock())
        fundamentals = next(f for f in report["fields"] if f["key"] == "fundamentals")
        self.assertEqual("FMP", fundamentals["provider"])


def _full_research() -> dict:
    return {
        "fundamentals": {
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 3_000_000_000_000,
            "trailingPE": 30.5,
        },
        "fundamentalsSource": "yfinance",
        "fundamentalsFetchedAt": "2026-08-06T09:00:00+00:00",
        "fundamentalsDetail": {"isin": "US0378331005", "revenueDate": "2026-06-30"},
        "researchDepth": {
            "rating": {"date": "2026-07-01", "rating": "A"},
            "estimates": [{"date": "2026-12-31"}],
            "cashflow": [],
            "debt": [],
        },
        "researchSignals": {
            "insiderTrades": [{"transactionDate": "2026-07-20"}],
            "institutionalHoldings": [{"holder": "Vanguard"}],
            "earningsSurprises": [{"date": "2026-05-01"}],
            "upcomingEarnings": "2026-10-30",
        },
        "earningsCalls": [{"date": "2026-05-02"}, {"date": "2026-02-01"}],
        "secFilings": {"filings": [{"date": "2026-07-15", "category": "material"}]},
        "socialSentiment": {
            "combined": {"totalMessages": 42},
            "stocktwits": {"topPosts": [{"created": "2026-08-05T18:00:00Z"}]},
        },
        "optionsFlow": {
            "expiry": "2026-08-21",
            "totalCallVolume": 1200,
            "fetchedAt": "2026-08-06T09:05:00+00:00",
        },
        "sectorContext": {
            "sectorEtf": "XLK",
            "relativeStrength": {"spy": {"peer": "SPY", "alpha1m": 1.2}},
            "correlation": {"benchmark": "SPY", "correlation": 0.8, "beta": 1.1},
            "fetchedAt": "2026-08-06T09:06:00+00:00",
        },
        "macroContext": {
            "vix": {"value": 14.2, "asOf": "2026-08-05"},
            "yield10y": {"value": 4.1, "asOf": "2026-08-05"},
            "dxy": {"value": 103.0, "asOf": "2026-08-04"},
        },
        "research": {"holdings": [{"symbol": "AAPL", "weight": 0.07}]},
        "provider": {"status": "live", "source": "Alpha Vantage", "lastUpdated": "2026-08-05T20:00:00Z"},
        "news": {
            "items": [
                {"timestamp": "2026-08-06T07:00:00Z"},
                {"timestamp": "2026-08-05T07:00:00Z"},
                {"timestamp": "2026-08-04T07:00:00Z"},
            ],
            "provider": {"source": "FMP", "lastUpdated": "2026-08-06T07:00:00Z"},
        },
    }


def _full_stock() -> dict:
    return {
        "synthetic": False,
        "provider": {"status": "live", "source": "Alpaca"},
        "chart_data": [{"date": f"2026-0{month}-01", "close": 100.0} for month in range(1, 8)] * 6,
        "prediction": {"direction": "UP", "confidence": 0.7, "modelTrainedAt": "2026-08-01T04:00:00+00:00"},
        "composite": {"verdict": "buy", "score": 0.6},
    }


if __name__ == "__main__":
    unittest.main()
