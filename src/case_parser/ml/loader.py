"""Loader functions for ML models and hybrid classifiers."""

from __future__ import annotations

from pathlib import Path

from .hybrid import HybridClassifier


def get_hybrid_classifier(
    model_path: Path | None = None,
    ml_threshold: float = 0.7,
) -> HybridClassifier:
    """Get hybrid classifier with optional ML model.

    Args:
        model_path: Path to trained model pickle file.
                   If None, looks for ml_models/procedure_classifier.pkl
        ml_threshold: Minimum confidence to use ML prediction (default: 0.7)

    Returns:
        HybridClassifier instance (rules-only if no model found)
    """
    # Default model path
    if model_path is None:
        model_path = Path("ml_models/procedure_classifier.pkl")

    return HybridClassifier.load(model_path, ml_threshold)
