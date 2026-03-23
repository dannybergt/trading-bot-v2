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
        Predict the movement for the next period based on the latest data.
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
            
            return {
                'direction': 'UP' if prediction == 1 else 'DOWN',
                'confidence': float(max(proba)),
                'timestamp': str(latest.index[-1]) if not isinstance(latest.index, pd.RangeIndex) else None
            }
        except Exception:
            logger.exception("model_prediction_failed")
            return None
