"""Feature engineering for ML classification."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer

from ..patterns.categorization import categorize_procedure


class FeatureExtractor:
    """Extract features from procedure text for ML classification."""

    def __init__(self):
        """Initialize feature extractors."""
        # Word-level TF-IDF
        self.tfidf_word = TfidfVectorizer(
            max_features=800,
            ngram_range=(1, 4),
            min_df=2,
            stop_words=self._get_medical_stopwords(),
        )

        # Character-level TF-IDF (for abbreviations)
        self.tfidf_char = TfidfVectorizer(
            analyzer="char",
            max_features=200,
            ngram_range=(3, 5),
            min_df=2,
        )

        self._is_fitted = False

    @staticmethod
    def _get_medical_stopwords() -> list[str]:
        """Get medical-specific stopwords."""
        return [
            "procedure",
            "patient",
            "performed",
            "underwent",
            "status",
            "post",
            "pre",
        ]

    def fit(self, procedures: list[str]) -> FeatureExtractor:
        """Fit feature extractors on training data.

        Args:
            procedures: List of procedure texts

        Returns:
            self
        """
        self.tfidf_word.fit(procedures)
        self.tfidf_char.fit(procedures)
        self._is_fitted = True
        return self

    def transform(self, procedures: list[str]) -> Any:
        """Transform procedures to feature matrix.

        Args:
            procedures: List of procedure texts

        Returns:
            Sparse feature matrix
        """
        if not self._is_fitted:
            raise ValueError("FeatureExtractor must be fitted before transform")

        # Text features
        word_features = self.tfidf_word.transform(procedures)
        char_features = self.tfidf_char.transform(procedures)

        # Structured features
        structured_features = self._extract_structured_batch(procedures)

        # Combine all features
        return hstack([word_features, char_features, structured_features])

    def fit_transform(self, procedures: list[str]) -> Any:
        """Fit and transform in one step.

        Args:
            procedures: List of procedure texts

        Returns:
            Sparse feature matrix
        """
        return self.fit(procedures).transform(procedures)

    def _extract_structured_batch(self, procedures: list[str]) -> np.ndarray:
        """Extract structured features for batch of procedures.

        Args:
            procedures: List of procedure texts

        Returns:
            Dense array of structured features
        """
        return np.array([self._extract_structured_single(proc) for proc in procedures])

    @staticmethod
    def _extract_structured_single(procedure_text: str) -> list[float]:
        """Extract structured features for single procedure.

        Args:
            procedure_text: Procedure description

        Returns:
            List of feature values
        """
        proc_upper = procedure_text.upper()

        # Get rule-based categorization for features
        category, warnings = categorize_procedure(procedure_text, services=[])

        return [
            # CPB indicators
            float("CPB" in proc_upper),
            float("CARDIOPULMONARY BYPASS" in proc_upper),
            float("BYPASS" in proc_upper and "CARDIAC" in proc_upper),
            # Approach indicators
            float("ENDOVASCULAR" in proc_upper),
            float("OPEN" in proc_upper),
            float("LAPAROSCOPIC" in proc_upper),
            float("ROBOTIC" in proc_upper),
            # Anatomical locations
            float("CARDIAC" in proc_upper or "HEART" in proc_upper),
            float("CRANIOTOMY" in proc_upper or "INTRACRANIAL" in proc_upper),
            float("THORACIC" in proc_upper or "CHEST" in proc_upper),
            float("VASCULAR" in proc_upper or "VESSEL" in proc_upper),
            float("CESAREAN" in proc_upper or "C-SECTION" in proc_upper),
            # Complexity indicators
            float("VALVE" in proc_upper),
            float("CABG" in proc_upper),
            float("TAVR" in proc_upper or "TAVI" in proc_upper),
            float("AVM" in proc_upper),
            float("ANEURYSM" in proc_upper),
            float("ECMO" in proc_upper),
            # Metadata
            float(len(warnings)),
            float(len(procedure_text) // 100),  # Length bucket
            # Rule-based hints (category features)
            float(
                category is not None and "Cardiac" in str(category.value)
                if category
                else 0
            ),
            float(
                category is not None and "Intracerebral" in str(category.value)
                if category
                else 0
            ),
            float(
                category is not None and "vessel" in str(category.value)
                if category
                else 0
            ),
        ]
