"""
SHADOW — Local ML Dark Pattern Detector.
Loads the trained scikit-learn TF-IDF + Logistic Regression model.
Provides fast (<2ms) local inference for dark-pattern text classification.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import joblib
except ImportError:
    joblib = None

MODEL_PATH = Path(__file__).resolve().parent / "models" / "dark_pattern_classifier.joblib"


class MLDetector:
    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_PATH
        self._binary_model = None
        self._category_model = None
        self._is_loaded = False
        self._load_model()

    def _load_model(self):
        if joblib is None:
            return
        if not self.model_path.exists():
            return
        try:
            artifact = joblib.load(self.model_path)
            self._binary_model = artifact.get("binary_model")
            self._category_model = artifact.get("category_model")
            self._is_loaded = self._binary_model is not None
        except Exception as e:
            self._is_loaded = False

    @property
    def is_available(self) -> bool:
        return self._is_loaded

    def predict(self, text: str) -> Dict[str, Any]:
        """
        Predict whether a text contains dark pattern indicators.
        Returns:
            {
                "is_dark_pattern": bool,
                "confidence": float (0.0 to 1.0),
                "category": str,
                "method": "ml_classifier"
            }
        """
        if not text or not self._is_loaded:
            return {
                "is_dark_pattern": False,
                "confidence": 0.0,
                "category": "none",
                "method": "ml_classifier_unavailable" if not self._is_loaded else "empty_input",
            }

        cleaned = " ".join(text.split()).strip()
        if len(cleaned) < 3:
            return {
                "is_dark_pattern": False,
                "confidence": 0.0,
                "category": "none",
                "method": "ml_classifier",
            }

        try:
            # Predict probability of being a dark pattern (class 1)
            probs = self._binary_model.predict_proba([cleaned])[0]
            confidence_dp = float(probs[1])
            is_dp = confidence_dp >= 0.50

            category = "general_dark_pattern"
            if is_dp and self._category_model is not None:
                try:
                    category = str(self._category_model.predict([cleaned])[0]).lower().replace(" ", "_")
                except Exception:
                    category = "general_dark_pattern"

            return {
                "is_dark_pattern": is_dp,
                "confidence": round(confidence_dp, 3),
                "category": category,
                "method": "ml_classifier",
            }
        except Exception as exc:
            return {
                "is_dark_pattern": False,
                "confidence": 0.0,
                "category": "error",
                "error": str(exc),
                "method": "ml_classifier_error",
            }
