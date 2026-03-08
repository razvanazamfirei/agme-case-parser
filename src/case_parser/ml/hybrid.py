"""Hybrid classifier combining rule-based and ML approaches."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypedDict

from ..domain import ProcedureCategory
from ..patterns.categorization import categorize_procedure, categorize_procedures
from .config import DEFAULT_ML_THRESHOLD
from .predictor import MLPredictor


class MLPredictorLike(Protocol):
    """Structural contract used by the hybrid classifier at inference time."""

    def predict_with_confidence(
        self,
        procedure_text: str,
        services: list[str] | None = None,
        rule_category: str | None = None,
        rule_warning_count: int = 0,
    ) -> tuple[str, float]: ...

    def predict_with_confidence_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
        rule_categories: list[str] | None = None,
        rule_warning_counts: list[int] | None = None,
    ) -> tuple[Sequence[str], list[float]]: ...


class ClassificationResult(TypedDict):
    """Result from hybrid classification."""

    category: ProcedureCategory
    method: str
    confidence: float
    alternative: ProcedureCategory | None
    warnings: list[str]


@dataclass(frozen=True)
class _RuleContext:
    """Rule-based context gathered before ML is consulted."""

    procedure_text: str
    services: list[str]
    category: ProcedureCategory
    warnings: list[str]


class HybridClassifier:
    """Hybrid classifier using both rule-based and ML approaches.

    Decision logic:
    - If ML confidence >= 0.85: use ML (high confidence override)
    - If ML confidence >= threshold (default runtime threshold): prefer ML
      and keep rules
      as fallback metadata
    - Otherwise: use rules only

    This provides automatic fallback to rules when ML is uncertain while still
    letting medium-confidence ML improve recall on cases the rule engine misses.
    """

    def __init__(
        self,
        ml_predictor: MLPredictorLike | None,
        ml_threshold: float = DEFAULT_ML_THRESHOLD,
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
        ml_threshold: float = DEFAULT_ML_THRESHOLD,
        inference_jobs: int | None = None,
    ) -> HybridClassifier:
        """Load hybrid classifier with optional ML model.

        Args:
            model_path: Path to ML model pickle (None for rules-only)
            ml_threshold: Min confidence for ML to influence result
            inference_jobs: Optional sklearn/joblib ``n_jobs`` override used
                when loading the ML predictor

        Returns:
            HybridClassifier instance
        """
        ml_predictor = None
        if model_path is not None and model_path.exists():
            ml_predictor = MLPredictor.load(
                model_path,
                inference_jobs=inference_jobs,
            )

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
        rule_category, rule_warnings = categorize_procedure(
            procedure=procedure_text,
            services=services or [],
        )
        return self._classify_with_rule_context(
            _RuleContext(
                procedure_text=procedure_text,
                services=services or [],
                category=rule_category,
                warnings=rule_warnings,
            )
        )

    def classify_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
    ) -> list[ClassificationResult]:
        """Classify multiple procedures in one batch."""
        if not procedure_texts:
            return []
        if services_list is None:
            service_rows = [[] for _ in procedure_texts]
        else:
            if len(services_list) != len(procedure_texts):
                raise ValueError(
                    "services_list must match procedure_texts length in classify_many"
                )
            service_rows = services_list
        rule_results = categorize_procedures(procedure_texts, service_rows)

        if self.ml_predictor is None:
            return [
                ClassificationResult(
                    category=rule_category,
                    method="rules",
                    confidence=0.8 if rule_warnings else 1.0,
                    alternative=None,
                    warnings=rule_warnings,
                )
                for rule_category, rule_warnings in rule_results
            ]

        ml_predictions, ml_confidences = self.ml_predictor.predict_with_confidence_many(
            procedure_texts,
            services_list=service_rows,
            rule_categories=[category.value for category, _ in rule_results],
            rule_warning_counts=[len(warnings) for _, warnings in rule_results],
        )
        procedure_count = len(procedure_texts)
        if (
            len(ml_predictions) != procedure_count
            or len(ml_confidences) != procedure_count
            or len(ml_predictions) != len(ml_confidences)
        ):
            raise ValueError(
                "Batch ML predictor length mismatch: "
                f"predictions={len(ml_predictions)}, "
                f"confidences={len(ml_confidences)}, "
                f"procedures={procedure_count}"
            )

        results: list[ClassificationResult] = []
        for (
            procedure_text,
            services,
            (rule_category, rule_warnings),
            ml_prediction,
            ml_confidence,
        ) in zip(
            procedure_texts,
            service_rows,
            rule_results,
            ml_predictions,
            ml_confidences,
            strict=True,
        ):
            results.append(
                self._classify_with_rule_context(
                    _RuleContext(
                        procedure_text=procedure_text,
                        services=services,
                        category=rule_category,
                        warnings=rule_warnings,
                    ),
                    ml_category_str=str(ml_prediction),
                    ml_confidence=float(ml_confidence),
                )
            )

        return results

    def _classify_with_rule_context(  # noqa: PLR0911
        self,
        rule_context: _RuleContext,
        ml_category_str: str | None = None,
        ml_confidence: float | None = None,
    ) -> ClassificationResult:
        """Combine rule context with optional ML outputs."""
        rule_category = rule_context.category
        rule_warnings = rule_context.warnings

        # If no ML model, return rules with appropriate confidence
        if self.ml_predictor is None:
            return ClassificationResult(
                category=rule_category,
                method="rules",
                confidence=0.8 if rule_warnings else 1.0,
                alternative=None,
                warnings=rule_warnings,
            )

        if ml_category_str is None or ml_confidence is None:
            ml_category_str, ml_confidence = self.ml_predictor.predict_with_confidence(
                rule_context.procedure_text,
                services=rule_context.services,
                rule_category=rule_category.value,
                rule_warning_count=len(rule_warnings),
            )
        ml_category_str = ml_category_str.strip()

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

        if (
            ml_confidence >= self.ml_threshold
            and rule_category == ProcedureCategory.OTHER
            and ml_category != ProcedureCategory.OTHER
        ):
            warnings = rule_warnings.copy()
            warnings.append(
                f"ML filled uncategorized rule result (conf={ml_confidence:.2f})"
            )
            return ClassificationResult(
                category=ml_category,
                method="ml_fill_other",
                confidence=ml_confidence,
                alternative=rule_category,
                warnings=warnings,
            )

        # Medium confidence ML - prefer ML while keeping the rule output as
        # fallback metadata.
        if ml_confidence >= self.ml_threshold:
            warnings = rule_warnings.copy()

            if ml_category != rule_category:
                warnings.append(
                    f"ML preferred over rules: {ml_category.value} over "
                    f"{rule_category.value} "
                    f"(conf={ml_confidence:.2f})"
                )

                return ClassificationResult(
                    category=ml_category,
                    method="ml_preferred",
                    confidence=ml_confidence,
                    alternative=rule_category,
                    warnings=warnings,
                )

            # ML and rules agree
            return ClassificationResult(
                category=rule_category,
                method="ml_rules_agree",
                confidence=ml_confidence,
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
