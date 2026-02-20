"""Hybrid classifier combining rule-based and ML approaches."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from ..domain import ProcedureCategory
from ..patterns.categorization import categorize_procedure
from .predictor import MLPredictor


class ClassificationResult(TypedDict):
    """Result from hybrid classification."""

    category: ProcedureCategory
    method: str
    confidence: float
    alternative: ProcedureCategory | None
    warnings: list[str]


class HybridClassifier:
    """Hybrid classifier using both rule-based and ML approaches.

    Decision logic:
    - If ML confidence >= 0.85: use ML (high confidence override)
    - If ML confidence >= threshold (default 0.7): use rules, flag if disagreement
    - Otherwise: use rules only

    This provides automatic fallback to rules when ML is uncertain.
    """

    def __init__(
        self,
        ml_predictor: MLPredictor | None,
        ml_threshold: float = 0.7,
    ):
        """Initialize hybrid classifier.

        Args:
            ml_predictor: ML predictor instance (None for rules-only mode)
            ml_threshold: Min confidence for ML to influence result (0.0-1.0)
        """
        self.ml_predictor = ml_predictor
        self.ml_threshold = ml_threshold

    @classmethod
    def load(
        cls,
        model_path: Path | None = None,
        ml_threshold: float = 0.7,
    ) -> HybridClassifier:
        """Load hybrid classifier with optional ML model.

        Args:
            model_path: Path to ML model pickle (None for rules-only)
            ml_threshold: Min confidence for ML to influence result

        Returns:
            HybridClassifier instance
        """
        ml_predictor = None
        if model_path is not None and model_path.exists():
            ml_predictor = MLPredictor.load(model_path)

        return cls(ml_predictor=ml_predictor, ml_threshold=ml_threshold)

    def classify(
        self, procedure_text: str, services: list[str] | None = None
    ) -> ClassificationResult:
        """Classify procedure using hybrid approach.

        Args:
            procedure_text: Procedure description
            services: Optional list of services (for rule-based categorization)

        Returns:
            ClassificationResult with category, method, confidence, etc.
        """
        # Always get rule-based category first
        rule_category, rule_warnings = categorize_procedure(
            procedure=procedure_text,
            services=services or [],
        )

        # If no ML model, return rules with appropriate confidence
        if self.ml_predictor is None:
            return ClassificationResult(
                category=rule_category,
                method="rules",
                confidence=0.8 if rule_warnings else 1.0,
                alternative=None,
                warnings=rule_warnings,
            )

        # Get ML prediction and confidence
        ml_category_str = self.ml_predictor.predict(procedure_text).strip()
        ml_confidence = self.ml_predictor.get_confidence(procedure_text)

        # Convert ML string to ProcedureCategory enum
        try:
            ml_category = ProcedureCategory(ml_category_str)
        except ValueError:
            # If ML returns invalid category, fall back to rules
            return ClassificationResult(
                category=rule_category,
                method="rules",
                confidence=0.8 if rule_warnings else 1.0,
                alternative=None,
                warnings=[
                    *rule_warnings,
                    f"ML returned invalid category: {ml_category_str}",
                ],
            )

        # High confidence ML override
        if ml_confidence >= 0.85:
            warnings = rule_warnings.copy()
            if ml_category != rule_category:
                warnings.append(
                    f"ML override (conf={ml_confidence:.2f}): "
                    f"rules suggested {rule_category.value}"
                )

            return ClassificationResult(
                category=ml_category,
                method="ml_override",
                confidence=ml_confidence,
                alternative=rule_category if ml_category != rule_category else None,
                warnings=warnings,
            )

        # Medium confidence ML - use rules but flag disagreement
        if ml_confidence >= self.ml_threshold:
            warnings = rule_warnings.copy()

            if ml_category != rule_category:
                warnings.append(
                    f"ML suggests {ml_category.value} (conf={ml_confidence:.2f})"
                )

                return ClassificationResult(
                    category=rule_category,
                    method="rules_flagged",
                    confidence=0.8 if rule_warnings else 1.0,
                    alternative=ml_category,
                    warnings=warnings,
                )

            # ML and rules agree
            return ClassificationResult(
                category=rule_category,
                method="rules_ml_agree",
                confidence=0.9,  # Higher confidence when both agree
                alternative=None,
                warnings=warnings,
            )

        # Low confidence ML - use rules only
        return ClassificationResult(
            category=rule_category,
            method="rules",
            confidence=0.8 if rule_warnings else 1.0,
            alternative=None,
            warnings=rule_warnings,
        )
