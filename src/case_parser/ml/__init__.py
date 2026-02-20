"""Machine learning module for procedure categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .features import FeatureExtractor
from .loader import get_hybrid_classifier

if TYPE_CHECKING:
    from .hybrid import HybridClassifier

__all__ = ["FeatureExtractor", "HybridClassifier", "get_hybrid_classifier"]
