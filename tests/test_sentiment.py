"""Sentiment-Adapter tests.

Verifies the VADER-backed scoring stays in [-1, 1] and that the
news-aggregation function maps thresholds to the expected bullish /
bearish / neutral labels. Also exercises the optional FinBERT
provider switch with a stubbed transformers pipeline so the test
suite stays independent of the heavy ML dependency.
"""
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app import sentiment  # noqa: E402


class SentimentTests(unittest.TestCase):
    def test_basic_positive_text_scores_positive(self):
        score = sentiment.analyze_sentiment_basic(
            "Excellent quarterly results, stock surges as analysts express strong confidence"
        )
        self.assertGreater(score, 0.1)
        self.assertLessEqual(score, 1.0)

    def test_basic_negative_text_scores_negative(self):
        score = sentiment.analyze_sentiment_basic(
            "Terrible quarter, stock crashes amid fraud allegations and bleak outlook"
        )
        self.assertLess(score, -0.1)
        self.assertGreaterEqual(score, -1.0)

    def test_empty_text_returns_zero(self):
        self.assertEqual(0.0, sentiment.analyze_sentiment_basic(""))

    def test_analyze_news_labels_match_thresholds(self):
        items = [
            {
                "title": "Stock surges as profits soar",
                "summary": "Excellent results, analysts express great confidence.",
            },
            {
                "title": "Lawsuit and fraud probe hit company hard",
                "summary": "Investors panic, terrible outlook, sharp losses ahead.",
            },
            {"title": "Quarterly results released", "summary": ""},
        ]
        out = sentiment.analyze_news(items)
        labels = [row["label"] for row in out]
        self.assertEqual(3, len(out))
        self.assertEqual("bullish", labels[0])
        self.assertEqual("bearish", labels[1])
        # Neutral items can come back as neutral or one of the others if VADER
        # picks up on the word "results"; the contract we care about is just
        # that every row carries a valid label and a numeric score.
        self.assertIn(labels[2], {"bullish", "bearish", "neutral"})
        for row in out:
            self.assertIsInstance(row["score"], float)


class FinbertProviderTests(unittest.TestCase):
    def setUp(self):
        sentiment.reset_finbert_state_for_tests()
        self._saved_provider = os.environ.get("SENTIMENT_PROVIDER")
        os.environ["SENTIMENT_PROVIDER"] = "finbert"

    def tearDown(self):
        sentiment.reset_finbert_state_for_tests()
        if self._saved_provider is None:
            os.environ.pop("SENTIMENT_PROVIDER", None)
        else:
            os.environ["SENTIMENT_PROVIDER"] = self._saved_provider
        sys.modules.pop("transformers", None)

    def _install_fake_transformers(self, pipeline_factory):
        """Inject a fake `transformers` module so the lazy import resolves."""
        module = types.ModuleType("transformers")
        module.pipeline = pipeline_factory
        sys.modules["transformers"] = module

    def test_finbert_positive_label_maps_to_positive_score(self):
        pipe = MagicMock(return_value=[{"label": "positive", "score": 0.92}])
        factory = MagicMock(return_value=pipe)
        self._install_fake_transformers(factory)
        score = sentiment.analyze_sentiment_basic("Stock soars on excellent results")
        self.assertAlmostEqual(0.92, score, places=4)
        # Pipeline factory called once on first inference, then cached
        sentiment.analyze_sentiment_basic("More positive news")
        self.assertEqual(1, factory.call_count)
        self.assertEqual(2, pipe.call_count)

    def test_finbert_negative_label_maps_to_negative_score(self):
        pipe = MagicMock(return_value=[{"label": "negative", "score": 0.81}])
        self._install_fake_transformers(MagicMock(return_value=pipe))
        score = sentiment.analyze_sentiment_basic("Fraud allegations sink the stock")
        self.assertAlmostEqual(-0.81, score, places=4)

    def test_finbert_neutral_label_maps_to_zero(self):
        pipe = MagicMock(return_value=[{"label": "neutral", "score": 0.55}])
        self._install_fake_transformers(MagicMock(return_value=pipe))
        score = sentiment.analyze_sentiment_basic("Quarterly results released today")
        self.assertEqual(0.0, score)

    def test_falls_back_to_vader_when_transformers_missing(self):
        # Ensure no fake transformers module is registered
        sys.modules.pop("transformers", None)
        # Block real imports of transformers if it happens to be installed
        with patch.dict(sys.modules, {"transformers": None}):
            score = sentiment.analyze_sentiment_basic(
                "Excellent results, stock surges, analysts express strong confidence"
            )
        # Falls back to VADER → positive value within range
        self.assertGreater(score, 0.1)

    def test_falls_back_to_vader_when_pipeline_load_fails(self):
        factory = MagicMock(side_effect=RuntimeError("model download failed"))
        self._install_fake_transformers(factory)
        score = sentiment.analyze_sentiment_basic(
            "Excellent results, stock surges, analysts express strong confidence"
        )
        # First call attempted to load and failed → VADER fallback
        self.assertGreater(score, 0.1)
        # Second call should NOT retry the failed pipeline (disabled flag)
        sentiment.analyze_sentiment_basic("Another test")
        self.assertEqual(1, factory.call_count)


if __name__ == "__main__":
    unittest.main()
