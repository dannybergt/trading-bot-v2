"""News sentiment scoring.

Default backend is VADER (`vaderSentiment.SentimentIntensityAnalyzer`),
chosen because it's small (~30 KB), pre-trained on social-media + news
language, and finance-friendly enough that words like "beat", "miss",
"upgrade", "downgrade" already lean the score in the right direction.
A score in [-1, 1] is returned, mirroring the prior TextBlob signature
so downstream consumers (`MarketDataService.get_market_news`, the
recommendation explainer) need no changes.

`SENTIMENT_PROVIDER=finbert` is a forward-looking opt-in switch. FinBERT
gives noticeably better results on financial news but pulls in PyTorch
plus a ~400 MB model and roughly doubles container size. The switch is
documented but currently falls back to VADER with a warning log: turning
it on requires adding `transformers` + a `finbert` model loader, which
is a deliberate later upgrade once the container size cost is accepted.
"""
from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

_BULLISH_THRESHOLD = float(os.getenv("SENTIMENT_BULLISH_THRESHOLD", "0.1"))
_BEARISH_THRESHOLD = float(os.getenv("SENTIMENT_BEARISH_THRESHOLD", "-0.1"))

_analyzer: SentimentIntensityAnalyzer | None = None
_analyzer_lock = Lock()


def _get_analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            if _analyzer is None:
                _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def analyze_sentiment_basic(text: str) -> float:
    """Return a [-1, 1] sentiment score for `text`.

    Uses VADER's `compound` field, which already lies in [-1, 1] and
    aggregates positive/negative/neutral lexicon hits with intensity
    modifiers and negation handling.
    """
    if not text:
        return 0.0
    provider = os.getenv("SENTIMENT_PROVIDER", "vader").lower()
    if provider == "finbert":
        logger.warning(
            "sentiment_provider_finbert_not_yet_supported_falling_back_to_vader"
        )
    scores = _get_analyzer().polarity_scores(text)
    return float(scores.get("compound", 0.0))


def analyze_news(news_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score a list of news items. Each item must carry `title`/`summary`.

    Returns the augmented list with `score` (float, [-1, 1]) and `label`
    (`bullish`, `bearish`, or `neutral`). Threshold defaults are tunable
    via `SENTIMENT_BULLISH_THRESHOLD` / `SENTIMENT_BEARISH_THRESHOLD`.
    """
    results: list[dict[str, Any]] = []
    for item in news_items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".strip()
        score = analyze_sentiment_basic(text)
        if score > _BULLISH_THRESHOLD:
            sentiment_label = "bullish"
        elif score < _BEARISH_THRESHOLD:
            sentiment_label = "bearish"
        else:
            sentiment_label = "neutral"
        results.append(
            {
                "title": item.get("title"),
                "summary": item.get("summary"),
                "score": score,
                "label": sentiment_label,
                "timestamp": item.get("providerPublishTime"),
                "url": item.get("url"),
                "source": item.get("source"),
            }
        )
    return results
