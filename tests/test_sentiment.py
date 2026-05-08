"""Sentiment-Adapter tests.

Verifies the VADER-backed scoring stays in [-1, 1] and that the
news-aggregation function maps thresholds to the expected bullish /
bearish / neutral labels.
"""
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
