"""Composite decision-score tests.

Verifies each axis mapping, the weighted combination, missing-axis
renormalisation, and the verdict thresholds.
"""
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app import composite_score as cs  # noqa: E402


class AxisTests(unittest.TestCase):
    def test_technical_axis_from_probability(self):
        self.assertAlmostEqual(cs.technical_axis({"probabilityUp": 1.0}), 1.0)
        self.assertAlmostEqual(cs.technical_axis({"probabilityUp": 0.5}), 0.0)
        self.assertAlmostEqual(cs.technical_axis({"probabilityUp": 0.0}), -1.0)

    def test_technical_axis_synthetic_is_none(self):
        self.assertIsNone(cs.technical_axis({"probabilityUp": 0.9, "synthetic": True}))
        self.assertIsNone(cs.technical_axis(None))

    def test_technical_axis_confidence_fallback(self):
        self.assertAlmostEqual(
            cs.technical_axis({"direction": "UP", "confidence": 0.8}), 0.6
        )
        self.assertAlmostEqual(
            cs.technical_axis({"direction": "DOWN", "confidence": 0.8}), -0.6
        )

    def test_analyst_axis(self):
        c = {"stance": "bullish", "targetUpsidePct": 25.0}
        self.assertAlmostEqual(cs.analyst_axis(c), 0.8)  # (0.6 + 1.0)/2
        self.assertAlmostEqual(cs.analyst_axis({"stance": "bearish"}), -0.6)
        self.assertIsNone(cs.analyst_axis(None))

    def test_fundamentals_axis(self):
        # healthy P/E, strong ROE, low debt -> positive
        info = {"trailingPE": 18.0, "returnOnEquity": 0.20, "debtToEquity": 40.0}
        val = cs.fundamentals_axis(info)
        self.assertIsNotNone(val)
        self.assertGreater(val, 0.4)
        self.assertIsNone(cs.fundamentals_axis({}))

    def test_news_axis(self):
        self.assertAlmostEqual(cs.news_axis(0.4), 0.4)
        self.assertAlmostEqual(cs.news_axis(5.0), 1.0)  # clamped
        self.assertIsNone(cs.news_axis(None))


class CompositeTests(unittest.TestCase):
    def test_weighted_combination_and_breakdown(self):
        result = cs.compute_composite(
            prediction={"probabilityUp": 1.0},          # technical +1
            analyst={"stance": "bullish", "targetUpsidePct": 25.0},  # +0.8
            fundamentals_info={"trailingPE": 18.0, "returnOnEquity": 0.20},  # +0.5
            news_sentiment=0.4,                          # +0.4
        )
        self.assertIsNotNone(result)
        # fundamentals: PE 18 -> +0.5, ROE 0.20 -> +1.0, avg = 0.75
        # 0.4*1 + 0.25*0.8 + 0.2*0.75 + 0.15*0.4 = 0.81 (weights sum to 1)
        self.assertAlmostEqual(result["score"], 0.81, places=2)
        self.assertEqual(result["verdict"], "BUY")
        self.assertEqual(len(result["breakdown"]), 4)
        self.assertTrue(all(b["available"] for b in result["breakdown"]))

    def test_missing_axis_renormalises(self):
        # Only technical present -> score equals that axis, weights renormalised.
        result = cs.compute_composite(
            prediction={"probabilityUp": 0.75},   # +0.5
            analyst=None,
            fundamentals_info=None,
            news_sentiment=None,
        )
        self.assertAlmostEqual(result["score"], 0.5, places=3)
        avail = {b["axis"]: b["available"] for b in result["breakdown"]}
        self.assertTrue(avail["technical"])
        self.assertFalse(avail["news"])

    def test_all_missing_returns_none(self):
        self.assertIsNone(
            cs.compute_composite(
                prediction=None, analyst=None, fundamentals_info=None, news_sentiment=None
            )
        )

    def test_verdict_thresholds(self):
        hold = cs.compute_composite(
            prediction={"probabilityUp": 0.52}, analyst=None,
            fundamentals_info=None, news_sentiment=None,
        )
        self.assertEqual(hold["verdict"], "HOLD")
        sell = cs.compute_composite(
            prediction={"probabilityUp": 0.1}, analyst=None,
            fundamentals_info=None, news_sentiment=None,
        )
        self.assertEqual(sell["verdict"], "SELL")


if __name__ == "__main__":
    unittest.main()
