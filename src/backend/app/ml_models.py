import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)
try:
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier
    from sklearn.metrics import accuracy_score
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logger.warning("ml_dependencies_missing prediction_disabled=true")

FEATURE_CATEGORIES: dict[str, str] = {
    # Trend (moving averages)
    "SMA_20": "trend",
    "SMA_50": "trend",
    "EMA_12": "trend",
    "EMA_26": "trend",
    # Technical (oscillators, bands, volatility)
    "RSI": "technical",
    "MACD_12_26_9": "technical",
    "MACDh_12_26_9": "technical",
    "MACDs_12_26_9": "technical",
    "BBL_20_2.0": "technical",
    "BBM_20_2.0": "technical",
    "BBU_20_2.0": "technical",
    "ATR": "technical",
    "STOCH_K": "technical",
    "STOCH_D": "technical",
    # Volume
    "Volume": "volume",
    # News sentiment
    "News_Sentiment": "news",
    # Fundamentals
    "PE_Ratio": "fundamentals",
    "Forward_PE": "fundamentals",
    "Price_To_Book": "fundamentals",
}

CATEGORY_LABELS = {
    "trend": "Trend",
    "technical": "Technical",
    "volume": "Volume",
    "news": "News",
    "fundamentals": "Fundamentals",
}


class PricePredictor:
    def __init__(self):
        self.is_trained = False
        if ML_AVAILABLE:
            self.model = XGBClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=42
            )
        else:
            self.model = None
        
    def prepare_features(self, df: pd.DataFrame):
        df = df.copy()
        
        # Create Target: 1 if Close next day > Close today, else 0
        df['Target'] = (df['Close'].shift(-1) > df['Close']).astype(int)
        
        # Drop NaN values created by indicators and shift
        df = df.dropna()
        
        feature_cols = [
            'RSI', 'SMA_20', 'SMA_50', 'EMA_12', 'EMA_26', 
            'BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0', # Bollinger Bands
            'MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9', # MACD
            'Volume', 'ATR', 'STOCH_K', 'STOCH_D', # Momentum & Volatility
            'News_Sentiment', 'PE_Ratio', 'Forward_PE', 'Price_To_Book' # Fundamentals & Sentiment
        ]
        
        # Filter only existing columns
        feature_cols = [c for c in feature_cols if c in df.columns]
        
        return df, feature_cols

    def train(self, df: pd.DataFrame):
        if not ML_AVAILABLE or self.model is None:
            return {'accuracy': 0, 'features': []}
            
        try:
            data, feature_cols = self.prepare_features(df)
            
            if data.empty:
                return {'accuracy': 0, 'features': []}
    
            X = data[feature_cols]
            y = data['Target']
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
            
            self.model.fit(X_train, y_train)
            self.is_trained = True
            
            preds = self.model.predict(X_test)
            acc = accuracy_score(y_test, preds)
            
            return {
                'accuracy': acc,
                'features': feature_cols
            }
        except Exception:
            logger.exception("model_training_failed")
            return {'accuracy': 0, 'features': []}

    def predict_next_movement(self, current_data_df: pd.DataFrame, *, user=None):
        """
        Predict the movement for the next period based on the latest data,
        with explainability, entry/stop/target zones derived from ATR, and
        broker-cost + capital-gains-tax aware net-yield projection.
        """
        if not ML_AVAILABLE or not self.is_trained or self.model is None:
            return None

        try:
            # We need the latest row with all indicators calculated
            latest = current_data_df.iloc[[-1]].copy()

            feature_cols = [
                'RSI', 'SMA_20', 'SMA_50', 'EMA_12', 'EMA_26',
                'BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0',
                'MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9',
                'Volume', 'ATR', 'STOCH_K', 'STOCH_D',
                'News_Sentiment', 'PE_Ratio', 'Forward_PE', 'Price_To_Book'
            ]
            feature_cols = [c for c in feature_cols if c in latest.columns]

            if not feature_cols:
                return None

            X_new = latest[feature_cols]
            prediction = self.model.predict(X_new)[0]
            proba = self.model.predict_proba(X_new)[0]
            direction = "UP" if prediction == 1 else "DOWN"
            confidence = float(max(proba))
            # XGBoost sklearn-API exposes class labels in `classes_`. The
            # convention is class 0 = DOWN (close <= prev), class 1 = UP.
            probability_up = float(proba[1]) if len(proba) > 1 else float(proba[0])
            probability_down = float(proba[0]) if len(proba) > 1 else 1.0 - probability_up

            explanation = self._explain_prediction(X_new, feature_cols)
            zones = self._compute_zones(latest, direction=direction, confidence=confidence)
            zones = self._enrich_with_yield_model(zones, user)
            reasoning = self._build_reasoning(direction, explanation)

            return {
                'direction': direction,
                'confidence': confidence,
                'probabilityUp': probability_up,
                'probabilityDown': probability_down,
                'timestamp': str(latest.index[-1]) if not isinstance(latest.index, pd.RangeIndex) else None,
                'explanation': explanation,
                'zones': zones,
                'reasoning': reasoning,
            }
        except Exception:
            logger.exception("model_prediction_failed")
            return None

    def _explain_prediction(self, X_new: pd.DataFrame, feature_cols: list[str]) -> dict | None:
        """Return per-feature SHAP-style contributions for the latest row.

        Uses XGBoost's native `pred_contribs=True` path which yields one
        SHAP-equivalent value per feature plus a bias column. We rank by
        absolute contribution and return the top few so the UI can render
        a compact "why" panel without overloading the user.
        """
        try:
            import xgboost as xgb

            booster = self.model.get_booster()
            dmatrix = xgb.DMatrix(X_new.values, feature_names=feature_cols)
            contribs = booster.predict(dmatrix, pred_contribs=True)
            # Shape is (n_rows, n_features + 1); last column is the bias term.
            row = contribs[0]
            bias = float(row[-1])
            feature_values = row[:-1]
            ranked = sorted(
                zip(feature_cols, feature_values, X_new.iloc[0].tolist()),
                key=lambda item: abs(float(item[1])),
                reverse=True,
            )
            top = []
            for name, contribution, value in ranked[:6]:
                top.append({
                    "feature": name,
                    "category": FEATURE_CATEGORIES.get(name, "other"),
                    "contribution": float(contribution),
                    "value": float(value),
                    "direction": "up" if float(contribution) >= 0 else "down",
                })

            # Category-level contributions: sum SHAP values per category so the
            # UI can show "Trend +0.42, News -0.05" without overwhelming the
            # user with the full feature list.
            category_totals: dict[str, float] = {}
            for name, contribution, _value in zip(feature_cols, feature_values, X_new.iloc[0].tolist()):
                category = FEATURE_CATEGORIES.get(name, "other")
                category_totals[category] = category_totals.get(category, 0.0) + float(contribution)

            categories = sorted(
                (
                    {
                        "category": cat,
                        "label": CATEGORY_LABELS.get(cat, cat.title()),
                        "contribution": float(value),
                        "direction": "up" if value >= 0 else "down",
                    }
                    for cat, value in category_totals.items()
                ),
                key=lambda item: abs(item["contribution"]),
                reverse=True,
            )

            return {
                "baseline": bias,
                "topFeatures": top,
                "categories": categories,
                "method": "xgboost_pred_contribs",
            }
        except Exception:
            logger.exception("model_explanation_failed")
            return None

    @staticmethod
    def _enrich_with_yield_model(zones: dict | None, user) -> dict | None:
        """Attach broker-cost + tax-aware net yield to the zone payload.

        Why this exists: the user has set a `min_target_yield` (in percent
        net) — the system must only flag a buy/sell candidate as actionable
        if the projected NET return clears that bar. Net = gross target
        return - round-trip broker fees - capital-gains tax on profit.

        `meetsMinimum` is the boolean the recommendation/auto-trading layer
        will gate on. When the user has no min set or no zones exist, we
        leave the field absent so consumers can detect "no constraint".
        """
        if not zones:
            return zones

        current_price = float(zones.get("currentPrice") or 0.0)
        target = float(zones.get("target") or 0.0)
        if current_price <= 0 or target <= 0:
            return zones

        gross_pct = (target - current_price) / current_price * 100.0
        if zones.get("direction") == "DOWN":
            gross_pct = -gross_pct  # absolute target distance for shorts

        # Broker fee model: percent applied per leg (entry + exit) plus an
        # absolute fee per leg expressed as percent of current price.
        fee_pct_per_leg = 0.0
        fee_absolute_pct_per_leg = 0.0
        cap_gains_rate_pct = 0.0
        income_tax_rate_pct = 0.0
        min_target_yield_pct: float | None = None

        if user is not None:
            try:
                fee_pct_per_leg = float(getattr(user, "trade_fee_percent", 0) or 0)
                fee_absolute = float(getattr(user, "trade_fee_absolute", 0) or 0)
                if current_price > 0:
                    fee_absolute_pct_per_leg = (fee_absolute / current_price) * 100.0
                cap_gains_bps = float(getattr(user, "capital_gains_tax_bps", 0) or 0)
                income_tax_bps = float(getattr(user, "income_tax_bps", 0) or 0)
                cap_gains_rate_pct = cap_gains_bps / 100.0
                income_tax_rate_pct = income_tax_bps / 100.0
                min_target_yield_pct = float(getattr(user, "min_target_yield", 0) or 0) or None
            except Exception:
                logger.exception("yield_model_user_settings_failed")

        round_trip_fee_pct = 2.0 * (fee_pct_per_leg + fee_absolute_pct_per_leg)
        gross_after_fees_pct = gross_pct - round_trip_fee_pct

        # Apply tax only to a positive profit. Cap-gains rate dominates when
        # set; income-tax rate is a fallback for jurisdictions/brokers that
        # treat short-term gains as ordinary income.
        effective_tax_rate_pct = cap_gains_rate_pct or income_tax_rate_pct
        tax_drag_pct = 0.0
        if gross_after_fees_pct > 0 and effective_tax_rate_pct > 0:
            tax_drag_pct = gross_after_fees_pct * (effective_tax_rate_pct / 100.0)

        net_pct = gross_after_fees_pct - tax_drag_pct

        enriched = dict(zones)
        enriched.update(
            {
                "grossTargetPct": round(gross_pct, 4),
                "feeRoundTripPct": round(round_trip_fee_pct, 4),
                "taxDragPct": round(tax_drag_pct, 4),
                "netTargetPct": round(net_pct, 4),
                "effectiveTaxRatePct": round(effective_tax_rate_pct, 4),
                "minTargetYieldPct": min_target_yield_pct,
                "meetsMinimum": (
                    None
                    if min_target_yield_pct is None
                    else net_pct >= float(min_target_yield_pct)
                ),
            }
        )
        return enriched

    @staticmethod
    def _build_reasoning(direction: str, explanation: dict | None) -> str | None:
        """Compose a one-sentence narrative from the top two SHAP categories.

        Intentionally short — the cards already show the numbers; this gives
        the user a "what's driving this signal" hook in plain English.
        """
        if not explanation or not explanation.get("categories"):
            return None
        cats = explanation["categories"][:2]
        if not cats:
            return None
        leader = cats[0]
        leader_label = leader["label"]
        leader_contrib = leader["contribution"]
        sign_word = "supports" if leader_contrib >= 0 else "weighs against"
        narrative = f"{leader_label} {sign_word} the {direction} signal ({leader_contrib:+.2f})"
        if len(cats) > 1:
            secondary = cats[1]
            sec_word = "reinforced by" if (secondary["contribution"] >= 0) == (leader_contrib >= 0) else "offset by"
            narrative += f", {sec_word} {secondary['label']} ({secondary['contribution']:+.2f})"
        narrative += "."
        return narrative

    @staticmethod
    def _compute_zones(latest_row_df: pd.DataFrame, *, direction: str, confidence: float) -> dict | None:
        """Derive entry/stop/target zones from the latest close and ATR.

        Volatility-anchored: a higher ATR widens both the entry band and the
        target distance. Confidence scales the target multiplier so a
        70%-confident UP signal projects a smaller move than an 90%-confident
        one without ever exceeding 3x ATR.
        """
        try:
            row = latest_row_df.iloc[0]
            close = float(row.get("Close") or 0.0)
            atr = float(row.get("ATR") or 0.0)
            if close <= 0 or atr <= 0:
                return None

            # Confidence in [0.5, 1.0] -> scale target between 1.5x and 3x ATR.
            clamped = max(0.5, min(1.0, confidence))
            target_mult = 1.5 + (clamped - 0.5) * 3.0  # 0.5 -> 1.5, 1.0 -> 3.0

            if direction == "UP":
                entry_low = close - 0.5 * atr
                entry_high = close
                stop_loss = close - 1.5 * atr
                target = close + target_mult * atr
            else:
                entry_low = close
                entry_high = close + 0.5 * atr
                stop_loss = close + 1.5 * atr
                target = close - target_mult * atr

            risk = abs(close - stop_loss)
            reward = abs(target - close)
            risk_reward = reward / risk if risk > 0 else None

            return {
                "direction": direction,
                "currentPrice": round(close, 4),
                "atr": round(atr, 4),
                "entryLow": round(entry_low, 4),
                "entryHigh": round(entry_high, 4),
                "stopLoss": round(stop_loss, 4),
                "target": round(target, 4),
                "riskReward": round(risk_reward, 2) if risk_reward is not None else None,
            }
        except Exception:
            logger.exception("model_zones_failed")
            return None
