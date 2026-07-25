import copy
import logging
from time import monotonic

import pandas as pd
import yfinance as yf
from app.analysis import calculate_indicators, detect_patterns
from app.alpha_vantage_service import AlphaVantageService
from app.composite_score import compute_composite
from app import composite_weights
from app import composite_snapshots
from app.asset_metadata import build_asset_profile, canonicalize_symbol, to_yfinance_symbol
from app.fmp_service import FmpService
from app.net_timeout import call_with_timeout
from app.rate_limit import acquire as acquire_rate_limit
from app.sentiment import analyze_news
from app.ml_models import PricePredictor
from app import ml_persistence
from app.twelve_data_service import TwelveDataService

logger = logging.getLogger(__name__)

TICKER_INFO_TTL_SECONDS = 5 * 60
NEWS_CACHE_TTL_SECONDS = 60
PREDICTOR_MEMORY_TTL_SECONDS = 60 * 60


def fundamentals_detail_from_ticker_info(info: dict) -> dict:
    """Map a yfinance ``.info`` dict onto the ``fundamentalsDetail`` contract
    the AnalysisPage KPI grid consumes — a free (no-key) fallback for when FMP
    is not configured, so KGV/EPS/Umsatz/Gewinn etc. still fill in.

    Unit normalisation is the delicate part; the frontend renders the ratio
    fields raw and the percentage fields via ``*100``:
    - yfinance reports ``debtToEquity`` as a percentage (e.g. 154.5 == 1.545x),
      so we divide by 100 to match FMP's ratio convention.
    - ``dividendYield``'s unit has flipped between yfinance releases, so rather
      than trust it we derive the yield from the unambiguous ``dividendRate``
      (annual currency/share) over the current price — always a clean fraction.
    ISIN/WKN/CUSIP stay FMP-only; yfinance does not expose them reliably.
    """
    if not isinstance(info, dict) or not info:
        return {}

    def _num(*keys):
        for key in keys:
            value = info.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        return None

    price = _num("currentPrice", "regularMarketPrice", "previousClose")
    dividend_rate = _num("dividendRate")
    dividend_yield = (
        dividend_rate / price
        if dividend_rate is not None and price and price > 0
        else None
    )
    debt_to_equity = _num("debtToEquity")
    if debt_to_equity is not None:
        debt_to_equity = debt_to_equity / 100.0
    market_cap = _num("marketCap")

    detail = {
        "exchange": info.get("exchange"),
        "currency": info.get("currency"),
        "beta": _num("beta"),
        "marketCap": int(market_cap) if market_cap is not None else None,
        "peRatioTtm": _num("trailingPE"),
        "forwardPe": _num("forwardPE"),
        "priceToBookTtm": _num("priceToBook"),
        "priceToSalesTtm": _num("priceToSalesTrailing12Months"),
        "epsTtm": _num("trailingEps"),
        "revenue": _num("totalRevenue"),
        "netIncome": _num("netIncomeToCommon"),
        "returnOnEquityTtm": _num("returnOnEquity"),
        "debtToEquityTtm": debt_to_equity,
        "dividendYieldTtm": dividend_yield,
        "annualDividend": dividend_rate,
        "payoutRatioTtm": _num("payoutRatio"),
        "source": "yfinance",
    }
    return {key: value for key, value in detail.items() if value is not None}


def analyst_consensus_from_ticker_info(info: dict) -> dict:
    """Extract the free analyst consensus (recommendation + price target) from a
    yfinance ``.info`` dict.

    Surfaced as a standalone decision criterion beside the technical ML verdict,
    deliberately NOT folded into the model's confidence — so the user sees
    analyst agreement or divergence transparently instead of a blended black box.
    yfinance provides this without an account; FMP can enrich it later.
    """
    if not isinstance(info, dict) or not info:
        return {}

    def _num(*keys):
        for key in keys:
            value = info.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        return None

    key_raw = info.get("recommendationKey")
    recommendation = (
        key_raw.strip().lower()
        if isinstance(key_raw, str) and key_raw.strip()
        else None
    )
    if recommendation in {"none", "n/a"}:
        recommendation = None
    mean = _num("recommendationMean")
    analyst_count = _num("numberOfAnalystOpinions")
    target_mean = _num("targetMeanPrice")
    target_high = _num("targetHighPrice")
    target_low = _num("targetLowPrice")
    price = _num("currentPrice", "regularMarketPrice", "previousClose")

    # Stance prefers the discrete recommendation; falls back to the 1..5 mean
    # (1 = strong buy ... 5 = strong sell) when only that is present.
    stance = None
    if recommendation in {"strong_buy", "buy", "outperform"}:
        stance = "bullish"
    elif recommendation == "hold":
        stance = "neutral"
    elif recommendation in {"sell", "strong_sell", "underperform"}:
        stance = "bearish"
    elif mean is not None:
        stance = "bullish" if mean <= 2.5 else "neutral" if mean <= 3.5 else "bearish"

    if stance is None and target_mean is None:
        return {}

    upside_pct = None
    if target_mean is not None and price and price > 0:
        upside_pct = round((target_mean - price) / price * 100.0, 2)

    consensus = {
        "recommendation": recommendation,
        "recommendationMean": mean,
        "stance": stance,
        "analystCount": int(analyst_count) if analyst_count is not None else None,
        "targetMean": target_mean,
        "targetHigh": target_high,
        "targetLow": target_low,
        "targetUpsidePct": upside_pct,
        "source": "yfinance",
    }
    return {key: value for key, value in consensus.items() if value is not None}


class MarketDataService:
    def __init__(
        self,
        alpaca_service=None,
        alpha_vantage_service=None,
        fmp_service=None,
        twelve_data_service=None,
    ):
        # Kept as a backwards-compatible default predictor for consumers /
        # tests that still patch `service.predictor` directly. The hot path
        # in `get_stock_data` now goes through `_get_or_train_predictor`,
        # which returns a per-symbol persisted instance.
        self.predictor = PricePredictor()
        self.alpaca = alpaca_service
        self.alpha_vantage = alpha_vantage_service or AlphaVantageService()
        self.fmp = fmp_service or FmpService()
        self.twelve_data = twelve_data_service or TwelveDataService()
        self._ticker_info_cache: dict[str, dict] = {}
        self._news_cache: dict[str, dict] = {}
        # Per-symbol predictor cache: symbol -> {predictor, metadata, expires_at}.
        # Filled on demand so a request never blocks on disk I/O for symbols
        # that are already warm in memory.
        self._predictor_cache: dict[str, dict] = {}

    def _get_cached_payload(self, cache: dict[str, dict], key: str):
        entry = cache.get(key)
        if not entry:
            return None
        if entry["expires_at"] <= monotonic():
            cache.pop(key, None)
            return None
        return copy.deepcopy(entry["value"])

    def _set_cached_payload(self, cache: dict[str, dict], key: str, value, ttl_seconds: int):
        cache[key] = {
            "expires_at": monotonic() + ttl_seconds,
            "value": copy.deepcopy(value),
        }
        return copy.deepcopy(value)

    def get_asset_reference(self, symbol: str):
        if not self.alpaca:
            return None

        target_symbol = canonicalize_symbol(symbol)
        for asset in self.alpaca.get_all_assets():
            if canonicalize_symbol(asset.get("symbol")) == target_symbol:
                return asset
        return None

    def get_asset_profile(
        self,
        symbol: str,
        ticker_info: dict | None = None,
        fallback_name: str | None = None,
    ) -> dict:
        asset = self.get_asset_reference(symbol)
        return build_asset_profile(
            symbol,
            asset=asset,
            ticker_info=ticker_info,
            fallback_name=fallback_name,
        )

    def get_provider_snapshot(
        self,
        symbol: str,
        *,
        asset_profile: dict | None = None,
    ) -> dict | None:
        profile = asset_profile or self.get_asset_profile(symbol)
        asset_class = profile.get("assetClass")
        if asset_class not in {"etf", "crypto"}:
            return None
        return self.alpha_vantage.get_provider_snapshot(profile["symbol"], asset_class)

    def get_provider_history_df(
        self,
        symbol: str,
        *,
        asset_profile: dict | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        profile = asset_profile or self.get_asset_profile(symbol)
        asset_class = profile.get("assetClass")
        if asset_class not in {"etf", "crypto"}:
            return pd.DataFrame()
        return self.alpha_vantage.get_history_df(profile["symbol"], asset_class, limit=limit)

    def get_yfinance_history_df(
        self, symbol: str, *, period: str = "6mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """Free (no-key) stock OHLCV history via yfinance, used as a fallback
        when no Alpaca key is configured. Best-effort: yfinance is unofficial
        and rate-limited, so an empty frame just means the caller falls through
        to the synthetic placeholder. Daily/weekly only — intraday needs Alpaca.
        """
        if not acquire_rate_limit("yfinance", timeout=4.0):
            logger.warning("stock_history_yfinance_rate_limit_skip symbol=%s", symbol)
            return pd.DataFrame()
        yf_period = {
            "1d": "5d", "5d": "5d", "1mo": "1mo", "3mo": "3mo",
            "6mo": "6mo", "1y": "1y", "max": "max",
        }.get(period, "6mo")
        hist = call_with_timeout(
            lambda: yf.Ticker(to_yfinance_symbol(symbol)).history(
                period=yf_period, interval=interval
            ),
            default=None,
            label=f"stock_history:{symbol}",
            provider="yfinance",
        )
        if hist is None or hist.empty:
            return pd.DataFrame()
        columns = ["Open", "High", "Low", "Close", "Volume"]
        available = [c for c in columns if c in hist.columns]
        return hist[available].dropna()

    def _get_or_train_predictor(
        self, symbol: str, df: pd.DataFrame
    ) -> tuple[PricePredictor, dict | None]:
        """Return a (predictor, metadata) pair for `symbol`, persisted on disk.

        Memory cache (1h TTL) → on-disk cache (24h TTL via `ml_persistence`)
        → train fresh + persist. The 1h memory cache exists to keep
        repeated `/api/stock/{symbol}` calls within a session from going
        to disk every time, while the 24h on-disk TTL keeps the model
        roughly aligned with daily-bar updates.
        """
        cached = self._predictor_cache.get(symbol)
        if cached and cached["expires_at"] > monotonic():
            return cached["predictor"], cached.get("metadata")

        loaded = ml_persistence.load_predictor(symbol, PricePredictor)
        if loaded is not None:
            predictor, metadata = loaded
            if not ml_persistence.is_stale(metadata) and ml_persistence.features_compatible(
                metadata, PricePredictor.EXPECTED_FEATURES
            ):
                self._predictor_cache[symbol] = {
                    "predictor": predictor,
                    "metadata": metadata,
                    "expires_at": monotonic() + PREDICTOR_MEMORY_TTL_SECONDS,
                }
                return predictor, metadata

        predictor = PricePredictor()
        metrics = predictor.train(df)
        metadata = None
        if predictor.is_trained:
            metadata = ml_persistence.save_predictor(
                symbol,
                predictor,
                accuracy=metrics.get("accuracy", 0.0),
                features=metrics.get("features", []),
                n_samples=len(df.index) if df is not None else 0,
            )
            self._predictor_cache[symbol] = {
                "predictor": predictor,
                "metadata": metadata,
                "expires_at": monotonic() + PREDICTOR_MEMORY_TTL_SECONDS,
            }
        return predictor, metadata

    def get_avg_daily_volume(self, symbol: str, *, lookback_days: int = 20) -> float | None:
        """Best-effort 20-day average daily volume for liquidity-aware sims.

        Tries Alpaca bars first (covers stocks + crypto), then yfinance
        history as a fallback. Returns None when no source produces a
        usable series so callers can fall back to static slippage.
        """
        target_symbol = canonicalize_symbol(symbol)
        asset_profile = self.get_asset_profile(symbol)

        if self.alpaca and asset_profile.get("assetClass") in {"stock", "crypto"}:
            try:
                df = self.alpaca.get_bars_df(
                    target_symbol, timeframe="1Day", limit=lookback_days
                )
                if not df.empty and "Volume" in df.columns:
                    series = df["Volume"].dropna()
                    if not series.empty:
                        return float(series.mean())
            except Exception:
                logger.exception("avg_volume_alpaca_failed symbol=%s", symbol)

        if not asset_profile.get("isCrypto") and acquire_rate_limit("yfinance", timeout=2.0):
            try:
                hist = call_with_timeout(
                    lambda: yf.Ticker(to_yfinance_symbol(symbol)).history(period=f"{lookback_days * 2}d"),
                    default=None,
                    label=f"avg_volume:{symbol}",
                    provider="yfinance",
                )
                if hist is not None and not hist.empty and "Volume" in hist.columns:
                    series = hist["Volume"].dropna().tail(lookback_days)
                    if not series.empty:
                        return float(series.mean())
            except Exception:
                logger.exception("avg_volume_yfinance_failed symbol=%s", symbol)

        return None

    def get_latest_close(self, symbol: str) -> float | None:
        """Best-effort latest close used by the paper-trading fill simulator.

        Tries Alpaca bars (stocks) and Alpha Vantage history (etf/crypto)
        first; falls back to yfinance for stocks. Returns None when no
        source produces a usable price so callers can leave the order
        pending instead of fabricating a fill.
        """
        target_symbol = canonicalize_symbol(symbol)
        asset_profile = self.get_asset_profile(symbol)

        if self.alpaca and asset_profile.get("assetClass") == "stock":
            try:
                df = self.alpaca.get_bars_df(target_symbol, timeframe="1Day", limit=1)
                if not df.empty and "Close" in df.columns:
                    return float(df.iloc[-1]["Close"])
            except Exception:
                logger.exception("latest_close_alpaca_failed symbol=%s", symbol)

        if asset_profile.get("assetClass") in {"etf", "crypto"}:
            try:
                df = self.alpha_vantage.get_history_df(
                    asset_profile["symbol"], asset_profile["assetClass"], limit=1
                )
                if not df.empty and "Close" in df.columns:
                    return float(df.iloc[-1]["Close"])
            except Exception:
                logger.exception("latest_close_alpha_vantage_failed symbol=%s", symbol)

        if not asset_profile.get("isCrypto") and acquire_rate_limit("yfinance", timeout=2.0):
            try:
                hist = call_with_timeout(
                    lambda: yf.Ticker(to_yfinance_symbol(symbol)).history(period="5d"),
                    default=None,
                    label=f"latest_close:{symbol}",
                    provider="yfinance",
                )
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    return float(hist["Close"].iloc[-1])
            except Exception:
                logger.exception("latest_close_yfinance_failed symbol=%s", symbol)

        return None

    def get_ticker_info(
        self,
        symbol: str,
        *,
        asset_profile: dict | None = None,
    ) -> dict:
        target_symbol = canonicalize_symbol(symbol)
        cached = self._get_cached_payload(self._ticker_info_cache, target_symbol)
        if cached is not None:
            return cached

        profile = asset_profile or self.get_asset_profile(symbol)
        if profile.get("isCrypto"):
            logger.debug("fundamentals_skipped_crypto symbol=%s", symbol)
            return self._set_cached_payload(self._ticker_info_cache, target_symbol, {}, TICKER_INFO_TTL_SECONDS)

        ticker_info: dict = {}
        if acquire_rate_limit("yfinance", timeout=4.0):
            ticker_info = call_with_timeout(
                lambda: yf.Ticker(to_yfinance_symbol(symbol)).info or {},
                default={},
                label=f"ticker_info:{symbol}",
                provider="yfinance",
            )
        else:
            logger.warning("fundamentals_yfinance_rate_limit_skip symbol=%s", symbol)

        if not isinstance(ticker_info, dict):
            ticker_info = {}

        # FMP fallback: yfinance returned nothing useful (rate-limited, empty
        # quoteSummary, or symbol not covered). Only chain when the result is
        # genuinely empty so we don't waste FMP quota when yfinance is healthy.
        meaningful_keys = {"sector", "industry", "marketCap", "trailingPE"}

        def _has_meaningful(info: dict) -> bool:
            return bool(info) and any(info.get(k) for k in meaningful_keys)

        if not _has_meaningful(ticker_info) and self.fmp.configured:
            fmp_info = self.fmp.normalized_ticker_info(symbol)
            if fmp_info:
                logger.info("fundamentals_fmp_fallback symbol=%s", symbol)
                ticker_info = {**ticker_info, **fmp_info}

        # Twelve Data closes the non-US gap (`SAP.DE`, `LVMH.PA`, `7203.T`).
        # Only chain when both yfinance and FMP came back empty so we don't
        # burn the 8 req/min budget on tickers the earlier providers covered.
        if not _has_meaningful(ticker_info) and self.twelve_data.configured:
            twelve_info = self.twelve_data.normalized_ticker_info(symbol)
            if twelve_info:
                logger.info("fundamentals_twelve_data_fallback symbol=%s", symbol)
                ticker_info = {**ticker_info, **twelve_info}

        return self._set_cached_payload(
            self._ticker_info_cache,
            target_symbol,
            ticker_info,
            TICKER_INFO_TTL_SECONDS,
        )
        
    def get_stock_data(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
        user=None,
        *,
        include_news: bool = True,
        include_fundamentals: bool = True,
    ):
        """
        Fetch historical data and calculate indicators.
        """
        df = pd.DataFrame()
        used_synthetic = False
        market_symbol = canonicalize_symbol(symbol)
        asset_profile = self.get_asset_profile(symbol)
        provider_snapshot = self.get_provider_snapshot(symbol, asset_profile=asset_profile)
        days_map = {"1d": 1, "5d": 5, "1mo": 22, "3mo": 66, "6mo": 260, "1y": 500, "max": 1000}
        limit = days_map.get(period, 130)
        if self.alpaca:
            # map period/interval to alpaca args
            tf_map = {"1d": "1Day", "1h": "1Hour", "15m": "15Min", "5m": "5Min", "1wk": "1Week"}
            timeframe = tf_map.get(interval, "1Day")
            
            if timeframe == "1Hour": limit = limit * 7
            elif timeframe == "15Min": limit = limit * 28
            elif timeframe == "5Min": limit = limit * 84
            
            df = self.alpaca.get_bars_df(market_symbol, timeframe=timeframe, limit=limit)
        
        if df.empty and asset_profile.get("assetClass") == "stock":
            refined_ticker_info = self.get_ticker_info(symbol, asset_profile=asset_profile)
            if refined_ticker_info:
                refined_profile = self.get_asset_profile(symbol, ticker_info=refined_ticker_info)
                if refined_profile.get("assetClass") != asset_profile.get("assetClass"):
                    asset_profile = refined_profile
                    provider_snapshot = self.get_provider_snapshot(symbol, asset_profile=asset_profile)

        if df.empty:
            df = self.get_provider_history_df(symbol, asset_profile=asset_profile, limit=limit)

        # Free stock-history fallback: without an Alpaca key, stock bars would
        # otherwise go straight to the synthetic placeholder. yfinance covers
        # daily/weekly stock OHLCV for free (no account); intraday still needs
        # Alpaca and falls through to the placeholder.
        if df.empty and asset_profile.get("assetClass") == "stock" and interval in ("1d", "1wk"):
            df = self.get_yfinance_history_df(symbol, period=period, interval=interval)

        if df.empty:
            logger.warning("market_data_empty_using_mock symbol=%s period=%s interval=%s", symbol, period, interval)
            df = self._generate_mock_data(symbol, period, interval)
            used_synthetic = True
            
        # Calculate Indicators
        df_analyzed = calculate_indicators(df)
        
        # Detect Patterns
        patterns = detect_patterns(df_analyzed)
        
        # Fetch News Sentiment
        if include_news:
            news_data = self.get_market_news(symbol, asset_profile=asset_profile)
        else:
            news_data = {
                "items": [],
                "aggregate_score": 0.0,
                "aggregate_label": "neutral",
                "provider": None,
            }
        sentiment_score = news_data['aggregate_score'] if news_data else 0.0

        # Fetch Fundamentals from YFinance
        tickerInfo = {}
        if include_fundamentals:
            tickerInfo = self.get_ticker_info(symbol, asset_profile=asset_profile)
            if tickerInfo:
                asset_profile = self.get_asset_profile(symbol, ticker_info=tickerInfo)
                provider_snapshot = self.get_provider_snapshot(symbol, asset_profile=asset_profile)
        pe_ratio = tickerInfo.get('trailingPE', 0.0)
        forward_pe = tickerInfo.get('forwardPE', 0.0)
        price_to_book = tickerInfo.get('priceToBook', 0.0)

        # Analyst consensus is a standalone criterion (not an ML feature) —
        # captured here so the API can show it beside the technical verdict.
        analyst = (
            analyst_consensus_from_ticker_info(tickerInfo)
            if include_fundamentals and not asset_profile.get("isCrypto")
            else {}
        )

        # News sentiment and fundamentals are intentionally NOT broadcast into
        # the ML feature frame anymore. As constant per-request columns they
        # contributed ~0 signal to the sequence model and only muddied
        # explainability; they now count as first-class weighted axes in the
        # composite decision score below (compute_composite: news_sentiment=...,
        # fundamentals_info=tickerInfo). The extracted scalars are still used
        # there and in the API payload's `info` block.

        # Generate Prediction. The predictor is now persisted per symbol
        # under `state/runtime/ml_models/<SYMBOL>.json` and only refreshed
        # when the on-disk model is older than ML_MODEL_TTL_HOURS — the
        # request path no longer pays the cost of an XGBoost retrain on
        # every call, and identical inputs now produce identical outputs.
        prediction = None
        try:
            predictor, predictor_metadata = self._get_or_train_predictor(symbol, df_analyzed)
            # Predict next move (user passed through so the zone yield model
            # can apply broker fees + tax rates per individual user)
            prediction = predictor.predict_next_movement(df_analyzed, user=user)
            if prediction is not None and predictor_metadata:
                prediction["modelTrainedAt"] = predictor_metadata.get("trainedAt")
                prediction["modelAccuracy"] = predictor_metadata.get("accuracy")
            
            # Apply user-defined Target Yield threshold constraints
            if prediction and prediction.get('direction') == 'UP' and user:
                # Get the last row's Close and ATR for volatility-based upside estimation
                latest = df_analyzed.iloc[-1]
                close_price = float(latest['Close'])
                atr = float(latest.get('ATR', 0))
                
                # Estimate a reasonable upside potential using 1.5 * ATR
                expected_gain_abs = atr * 1.5
                expected_gain_pct = (expected_gain_abs / close_price) * 100
                
                # Calculate required yield from user settings
                min_yield_pct = float(user.min_target_yield)
                fee_pct = float(user.trade_fee_percent)
                fee_abs_as_pct = (float(user.trade_fee_absolute) / close_price) * 100 if close_price > 0 else 0
                
                total_required_pct = min_yield_pct + fee_pct + fee_abs_as_pct
                
                # Attach expected yield context to the prediction dict
                prediction['expected_yield_pct'] = round(expected_gain_pct, 2)
                prediction['required_yield_pct'] = round(total_required_pct, 2)
                
                if expected_gain_pct < total_required_pct:
                    prediction['direction'] = 'HOLD'
                    prediction['reason'] = f'HOLD: Expected upside ({expected_gain_pct:.2f}%) is below your target + fees ({total_required_pct:.2f}%).'
                    logger.info("prediction_buy_suppressed symbol=%s reason=%s", symbol, prediction['reason'])
                else:
                    prediction['reason'] = f'BUY: Passed target yield filter ({expected_gain_pct:.2f}% >= {total_required_pct:.2f}%).'
                    
        except Exception:
            logger.exception("market_prediction_failed symbol=%s", symbol)

        if used_synthetic:
            # No provider returned real bars — the chart rests on a synthetic
            # random-walk placeholder (see _generate_mock_data). Any ML output
            # would be a recommendation on fabricated prices, so we suppress the
            # actionable verdict and mark the payload synthetic. This keeps the
            # rest of the pipeline honest by construction: auto_execution
            # rejects any non-UP/DOWN direction and confidence < 0.6, the push
            # notification path needs confidence >= 0.80, and the frontend
            # renders a "placeholder data" banner instead of a buy/sell signal.
            prediction = {
                "direction": "HOLD",
                "confidence": 0.0,
                "synthetic": True,
                "reason": (
                    "Keine echten Marktdaten verfuegbar — kein Provider hat "
                    "Kursdaten geliefert. Angezeigt werden Platzhalterwerte; "
                    "es wird keine Handelsempfehlung gegeben."
                ),
            }

        # Composite decision score: combine ML (technical) + analyst +
        # fundamentals + news into one transparent weighted verdict. Computed
        # after the prediction is finalised; suppressed on synthetic data (no
        # real technical signal). Augments the ML prediction, does not replace
        # it, and is not yet wired into auto-execution.
        composite = None
        if not used_synthetic:
            composite = compute_composite(
                prediction=prediction,
                analyst=analyst,
                fundamentals_info=tickerInfo,
                news_sentiment=sentiment_score,
                weights=composite_weights.get_weights(),
            )
            # Forward-collection for calibration (2d-3): record the verdict +
            # per-axis values now so the realised outcome can be joined later.
            # Best-effort — never breaks the recommendation.
            if composite is not None:
                try:
                    last_close = float(df_analyzed["Close"].iloc[-1])
                except (KeyError, IndexError, ValueError, TypeError):
                    last_close = None
                if last_close:
                    composite_snapshots.record_snapshot(symbol, last_close, composite)

        # Get Info (Enriched with YFinance)
        info = {
            'symbol': symbol,
            'shortName': asset_profile['name'],
            'sector': tickerInfo.get('sector', 'N/A'),
            'industry': tickerInfo.get('industry', 'N/A'),
            'currency': tickerInfo.get('currency') or 'USD',
            'marketCap': tickerInfo.get('marketCap', 0),
            'dividendYield': tickerInfo.get('dividendYield', 0),
            '52WeekHigh': tickerInfo.get('fiftyTwoWeekHigh', 0),
            '52WeekLow': tickerInfo.get('fiftyTwoWeekLow', 0),
            'trailingPE': pe_ratio,
            'forwardPE': forward_pe,
            'priceToBook': price_to_book,
            'assetClass': asset_profile['assetClass'],
            'assetLabel': asset_profile['assetLabel'],
            'market': asset_profile['market'],
            'exchange': asset_profile['exchange'],
            'type': asset_profile['type'],
            'isCrypto': asset_profile['isCrypto'],
            'provider': provider_snapshot,
        }

        return {
            'data': df_analyzed,
            'patterns': patterns,
            'prediction': prediction,
            'info': info,
            'asset': asset_profile,
            'provider': provider_snapshot,
            'synthetic': used_synthetic,
            'analyst': analyst,
            'composite': composite,
        }

    def _generate_mock_data(self, symbol, period, interval):
        import numpy as np
        from datetime import datetime, timedelta
        
        # Determine number of points based on period/interval
        days_map = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "max": 1000}
        days = days_map.get(period, 180)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # interval map to frequency
        freq_map = {"1d": "D", "1h": "H", "15m": "15T", "5m": "5T", "1wk": "W"}
        freq = freq_map.get(interval, "D")
        
        dates = pd.date_range(start=start_date, end=end_date, freq=freq)
        n = len(dates)
        
        if n == 0:
            dates = pd.date_range(start=start_date, periods=100, freq=freq)
            n = 100
            
        # Random walk
        base_price = 150.0
        if symbol == "NVDA": base_price = 450.0
        elif symbol == "GOOGL": base_price = 140.0
        elif symbol == "MSFT": base_price = 350.0
        
        np.random.seed(42)
        returns = np.random.normal(0, 0.02, n)
        price_curve = base_price * (1 + returns).cumprod()
        
        data = {
            "Open": price_curve,
            "High": price_curve * (1 + np.abs(np.random.normal(0, 0.01, n))),
            "Low": price_curve * (1 - np.abs(np.random.normal(0, 0.01, n))),
            "Close": price_curve,
            "Volume": np.random.randint(100000, 5000000, n).astype(float)
        }
        
        df = pd.DataFrame(data, index=dates)
        return df

    def get_market_news(
        self,
        symbol: str,
        limit: int = 15,
        *,
        asset_profile: dict | None = None,
    ):
        """
        Fetch news for the symbol from Alpaca and analyze sentiment.
        """
        target_symbol = canonicalize_symbol(symbol)
        profile = asset_profile or self.get_asset_profile(symbol)
        cache_key = f"{profile.get('assetClass') or 'stock'}|{target_symbol}|{int(limit)}"
        cached = self._get_cached_payload(self._news_cache, cache_key)
        if cached is not None:
            return cached

        if profile.get("assetClass") in {"etf", "crypto"}:
            provider_payload = self.alpha_vantage.get_news_payload(
                target_symbol,
                profile["assetClass"],
                limit=limit,
            )
            if provider_payload and provider_payload.get("items"):
                return self._set_cached_payload(
                    self._news_cache,
                    cache_key,
                    provider_payload,
                    NEWS_CACHE_TTL_SECONDS,
                )

        raw_news = []
        if self.alpaca:
            try:
                raw_news = self.alpaca.get_news(target_symbol, limit=limit)
            except Exception:
                logger.exception("market_news_fetch_failed symbol=%s", symbol)

        # Normalize news items to expected format for analyze_news
        normalized = []
        for item in raw_news:
             normalized.append({
                 'title': item.get('headline', ''),
                 'summary': item.get('summary', ''),
                 'providerPublishTime': item.get('created_at', ''),
                 'url': item.get('url', ''),
                 'source': item.get('source', ''),
             })

        # FMP fallback for news when Alpaca returned nothing — same surface for
        # downstream sentiment scoring.
        if not normalized and self.fmp.configured:
            fmp_items = self.fmp.normalized_news_items(target_symbol, limit=limit)
            for item in fmp_items:
                normalized.append({
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "providerPublishTime": item.get("timestamp", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", "FMP"),
                })
            if normalized:
                logger.info("market_news_fmp_fallback symbol=%s items=%d", symbol, len(normalized))

        analyzed_news = analyze_news(normalized)

        # Calculate aggregate sentiment
        avg_score = 0
        if analyzed_news:
            avg_score = sum(item['score'] for item in analyzed_news) / len(analyzed_news)

        # If we ended up using FMP, report it as the source so downstream UIs
        # can show provenance accurately.
        sources = {item.get("source") for item in normalized if item.get("source")}
        primary_source = "Alpaca" if "Alpaca" in sources or any(
            s in sources for s in ("alpaca",)
        ) else next(iter(sources), None)
        if primary_source is None and analyzed_news:
            primary_source = "FMP"

        payload = {
            'items': analyzed_news,
            'aggregate_score': avg_score,
            'aggregate_label': 'bullish' if avg_score > 0.1 else 'bearish' if avg_score < -0.1 else 'neutral',
            'provider': {
                'status': 'live' if analyzed_news else 'unavailable',
                'source': primary_source if analyzed_news else None,
                'assetClass': profile.get("assetClass"),
                'lastUpdated': analyzed_news[0].get('timestamp') if analyzed_news else None,
            },
        }
        return self._set_cached_payload(self._news_cache, cache_key, payload, NEWS_CACHE_TTL_SECONDS)
