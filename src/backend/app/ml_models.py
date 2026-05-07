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

    def predict_next_movement(self, current_data_df: pd.DataFrame):
        """
        Predict the movement for the next period based on the latest data,
        with explainability and entry/stop/target zones derived from ATR.
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

            explanation = self._explain_prediction(X_new, feature_cols)
            zones = self._compute_zones(latest, direction=direction, confidence=confidence)

            return {
                'direction': direction,
                'confidence': confidence,
                'timestamp': str(latest.index[-1]) if not isinstance(latest.index, pd.RangeIndex) else None,
                'explanation': explanation,
                'zones': zones,
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
                    "contribution": float(contribution),
                    "value": float(value),
                    "direction": "up" if float(contribution) >= 0 else "down",
                })
            return {
                "baseline": bias,
                "topFeatures": top,
                "method": "xgboost_pred_contribs",
            }
        except Exception:
            logger.exception("model_explanation_failed")
            return None

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
