"""News sentiment scoring.

Default backend is VADER (`vaderSentiment.SentimentIntensityAnalyzer`),
chosen because it's small (~30 KB), pre-trained on social-media + news
language, and finance-friendly enough that words like "beat", "miss",
"upgrade", "downgrade" already lean the score in the right direction.
A score in [-1, 1] is returned, mirroring the prior TextBlob signature
so downstream consumers (`MarketDataService.get_market_news`, the
recommendation explainer) need no changes.

`SENTIMENT_PROVIDER=finbert` switches to ProsusAI/finbert via the
HuggingFace transformers pipeline. FinBERT gives noticeably better
results on financial news but pulls in PyTorch plus a ~400 MB model
and roughly doubles container size — the dependency lives in
`requirements-finbert.txt` and is opt-in. If `transformers` is not
installed (or the model fails to load), the switch logs a warning
once and silently falls back to VADER, so a misconfigured deployment
degrades gracefully instead of crashing the request path.
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
FINBERT_MODEL_NAME = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")
# FinBERT tokenizer truncates at 512 tokens; cap inputs roughly so we
# don't ship multi-thousand-character earnings transcripts in one call.
FINBERT_MAX_CHARS = 1500

_analyzer: SentimentIntensityAnalyzer | None = None
_analyzer_lock = Lock()

_finbert_pipeline: Any | None = None
_finbert_lock = Lock()
_finbert_disabled = False  # set True after a load failure so we stop retrying


def _get_analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            if _analyzer is None:
                _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def _get_finbert_pipeline() -> Any | None:
    """Lazy-load the FinBERT pipeline. Returns None when unavailable.

    Caches the pipeline at module level so repeated requests reuse the
    same loaded model. A single load failure flips `_finbert_disabled`
    so we don't keep paying the import-and-fail cost on every call.
    """
    global _finbert_pipeline, _finbert_disabled
    if _finbert_disabled:
        return None
    if _finbert_pipeline is not None:
        return _finbert_pipeline
    with _finbert_lock:
        if _finbert_pipeline is not None:
            return _finbert_pipeline
        if _finbert_disabled:
            return None
        try:
            from transformers import pipeline  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "sentiment_provider_finbert_requested_but_transformers_missing_falling_back_to_vader"
            )
            _finbert_disabled = True
            return None
        try:
            _finbert_pipeline = pipeline(
                "sentiment-analysis",
                model=FINBERT_MODEL_NAME,
                tokenizer=FINBERT_MODEL_NAME,
                truncation=True,
            )
            logger.info("sentiment_provider_finbert_loaded model=%s", FINBERT_MODEL_NAME)
        except Exception:
            logger.exception(
                "sentiment_provider_finbert_load_failed_falling_back_to_vader"
            )
            _finbert_disabled = True
            _finbert_pipeline = None
            return None
    return _finbert_pipeline


def _finbert_score(text: str) -> float | None:
    """Run FinBERT on `text` and return a compound-style score in [-1, 1].

    FinBERT classifies into `positive` / `negative` / `neutral` with a
    softmax confidence; we map that onto a single signed score so the
    downstream consumers can keep the VADER-compatible interface.
    Returns None when the pipeline is unavailable (-> caller falls back
    to VADER).
    """
    pipe = _get_finbert_pipeline()
    if pipe is None:
        return None
    try:
        result = pipe(text[:FINBERT_MAX_CHARS])
    except Exception:
        logger.exception("sentiment_finbert_inference_failed")
        return None
    if not result:
        return 0.0
    first = result[0] if isinstance(result, list) else result
    label = str(first.get("label", "")).lower() if isinstance(first, dict) else ""
    score = float(first.get("score", 0.0)) if isinstance(first, dict) else 0.0
    if label.startswith("positive"):
        return score
    if label.startswith("negative"):
        return -score
    return 0.0


def analyze_sentiment_basic(text: str) -> float:
    """Return a [-1, 1] sentiment score for `text`.

    Uses VADER's `compound` field by default. When
    `SENTIMENT_PROVIDER=finbert` and the optional FinBERT stack is
    installed, swaps in ProsusAI/finbert; otherwise transparently falls
    back to VADER.
    """
    if not text:
        return 0.0
    provider = os.getenv("SENTIMENT_PROVIDER", "vader").lower()
    if provider == "finbert":
        score = _finbert_score(text)
        if score is not None:
            return score
        # Fall through to VADER below
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


def reset_finbert_state_for_tests() -> None:
    """Reset the lazy-loaded FinBERT singleton — only for tests."""
    global _finbert_pipeline, _finbert_disabled
    with _finbert_lock:
        _finbert_pipeline = None
        _finbert_disabled = False
