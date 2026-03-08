"""ML predictor wrapper for trained models."""

from __future__ import annotations

import pickle  # noqa: S403
from collections.abc import Iterable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from .config import get_default_ml_inference_jobs, normalize_ml_inference_jobs
from .inputs import FeatureInput, build_feature_inputs


class ProcedureMLPipeline:
    """Inference pipeline that combines feature extraction and estimator."""

    def __init__(self, model: Any, features: Any):
        """Initialize the pipeline with a fitted estimator and feature extractor.

        Args:
            model: Fitted sklearn-compatible estimator with predict and
                predict_proba methods.
            features: Fitted feature transformer with a transform method.
        """
        self.model = model
        self.features = features
        self.classes_ = getattr(model, "classes_", [])

    @staticmethod
    def _coerce_inputs(procedures: Iterable[Any] | Any) -> list[Any]:
        """Normalize supported single-item or iterable inputs to a list."""
        if isinstance(procedures, (str, Mapping, FeatureInput)):
            return [procedures]
        return list(procedures)

    def predict(self, procedures: Iterable[Any] | Any) -> Any:
        """Predict categories for one or more procedure inputs.

        Args:
            procedures: Single procedure input or iterable of inputs. Each item
                may be a procedure string, a raw mapping with procedure/service
                metadata, or a :class:`FeatureInput`.

        Returns:
            Array of predicted category labels, one per input procedure.
        """
        texts = self._coerce_inputs(procedures)
        feature_matrix = self.features.transform(texts)
        return self.model.predict(feature_matrix)

    def predict_proba(self, procedures: Iterable[Any] | Any) -> Any:
        """Return class probabilities for one or more procedure inputs.

        Args:
            procedures: Single procedure input or iterable of inputs. Each item
                may be a procedure string, a raw mapping with procedure/service
                metadata, or a :class:`FeatureInput`.

        Returns:
            2-D array of shape (n_samples, n_classes) with class probabilities.
        """
        texts = self._coerce_inputs(procedures)
        feature_matrix = self.features.transform(texts)
        return self.model.predict_proba(feature_matrix)


class MLPredictor:
    """Wrapper for trained ML model."""

    def __init__(self, pipeline: Any, metadata: dict, inference_jobs: int):
        """Initialize predictor.

        Args:
            pipeline: Trained sklearn pipeline
            metadata: Model metadata dict
            inference_jobs: Configured sklearn/joblib ``n_jobs`` used at inference
        """
        self.pipeline = pipeline
        self.metadata = metadata
        self.inference_jobs = inference_jobs

    @staticmethod
    def _iter_estimator_children(estimator: Any) -> list[Any]:
        """Return nested estimator-like children for recursive traversal."""
        children: list[Any] = []
        for attr in ("model", "final_estimator", "final_estimator_"):
            child = getattr(estimator, attr, None)
            if child is not None:
                children.append(child)

        for attr in ("estimators", "estimators_", "steps"):
            nested_items = getattr(estimator, attr, None)
            if nested_items is None:
                continue
            for nested_item in nested_items:
                if isinstance(nested_item, tuple):
                    if len(nested_item) < 2:
                        continue
                    nested_child = nested_item[1]
                else:
                    nested_child = nested_item
                children.append(nested_child)

        for attr in ("named_estimators_", "named_steps"):
            nested_mapping = getattr(estimator, attr, None)
            if nested_mapping is None:
                continue
            children.extend(nested_mapping.values())

        return children

    @staticmethod
    def _apply_inference_n_jobs(
        estimator: Any,
        inference_jobs: int,
        visited: set[int] | None = None,
    ) -> None:
        """Recursively normalize estimator ``n_jobs`` for inference."""
        if estimator is None:
            return

        visited = set() if visited is None else visited
        estimator_id = id(estimator)
        if estimator_id in visited:
            return
        visited.add(estimator_id)

        if hasattr(estimator, "n_jobs"):
            with suppress(AttributeError, ValueError):
                estimator.n_jobs = inference_jobs

        for child in MLPredictor._iter_estimator_children(estimator):
            MLPredictor._apply_inference_n_jobs(child, inference_jobs, visited)

    @classmethod
    def load(
        cls,
        model_path: Path,
        inference_jobs: int | None = None,
    ) -> MLPredictor:
        """Load model from pickle file.

        Args:
            model_path: Path to model pickle file
            inference_jobs: Optional sklearn/joblib ``n_jobs`` override applied
                recursively to loaded estimators. Defaults to the runtime config.

        Returns:
            MLPredictor instance

        Raises:
            FileNotFoundError: If model file doesn't exist
            ValueError: If the pickle artifact is missing the expected
                ``pipeline`` key.
        """
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        with model_path.open("rb") as f:
            model_data = pickle.load(f)  # noqa: S301

        if "pipeline" not in model_data:
            raise ValueError(
                "Unsupported model artifact format. Expected key: ['pipeline']."
            )
        pipeline = model_data["pipeline"]
        configured_inference_jobs = (
            get_default_ml_inference_jobs()
            if inference_jobs is None
            else normalize_ml_inference_jobs(
                inference_jobs,
                source_name="inference_jobs",
            )
        )
        cls._apply_inference_n_jobs(pipeline, configured_inference_jobs)

        return cls(
            pipeline=pipeline,
            metadata=model_data.get("metadata", {}),
            inference_jobs=configured_inference_jobs,
        )

    def predict(self, procedure_text: str) -> str:
        """Predict category for procedure text.

        Args:
            procedure_text: Procedure description

        Returns:
            Predicted category string
        """
        return self.predict_many([procedure_text])[0]

    def predict_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
        rule_categories: list[str] | None = None,
        rule_warning_counts: list[int] | None = None,
    ) -> Any:
        """Predict categories for multiple procedures."""
        if not procedure_texts:
            return []
        return self.pipeline.predict(
            build_feature_inputs(
                procedure_texts,
                services_list=services_list,
                rule_categories=rule_categories,
                rule_warning_counts=rule_warning_counts,
            )
        )

    def predict_proba(self, procedure_text: str) -> dict[str, float]:
        """Get prediction probabilities for all categories.

        Args:
            procedure_text: Procedure description

        Returns:
            Dict mapping category to probability
        """
        proba = self.predict_proba_many([procedure_text])[0]
        classes = self.pipeline.classes_

        return dict(zip(classes, proba, strict=False))

    def predict_proba_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
        rule_categories: list[str] | None = None,
        rule_warning_counts: list[int] | None = None,
    ) -> Any:
        """Get prediction probabilities for multiple procedures."""
        if not procedure_texts:
            return []
        return self.pipeline.predict_proba(
            build_feature_inputs(
                procedure_texts,
                services_list=services_list,
                rule_categories=rule_categories,
                rule_warning_counts=rule_warning_counts,
            )
        )

    def get_confidence(self, procedure_text: str) -> float:
        """Get confidence (max probability) for prediction.

        Args:
            procedure_text: Procedure description

        Returns:
            Confidence score (0.0-1.0)
        """
        proba = self.predict_proba_many([procedure_text])[0]
        return float(proba.max())

    def predict_with_confidence(
        self,
        procedure_text: str,
        services: list[str] | None = None,
        rule_category: str | None = None,
        rule_warning_count: int = 0,
    ) -> tuple[str, float]:
        """Predict a single category and confidence in one pass."""
        predictions, confidences = self.predict_with_confidence_many(
            [procedure_text],
            services_list=[services or []],
            rule_categories=[rule_category or ""],
            rule_warning_counts=[rule_warning_count],
        )
        return str(predictions[0]), float(confidences[0])

    def predict_with_confidence_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
        rule_categories: list[str] | None = None,
        rule_warning_counts: list[int] | None = None,
    ) -> tuple[Any, list[float]]:
        """Predict categories and confidences for multiple procedures."""
        if not procedure_texts:
            return [], []
        probabilities = self.predict_proba_many(
            procedure_texts,
            services_list=services_list,
            rule_categories=rule_categories,
            rule_warning_counts=rule_warning_counts,
        )
        predictions = [
            self.pipeline.classes_[int(index)] for index in probabilities.argmax(axis=1)
        ]
        confidences = probabilities.max(axis=1).astype(float).tolist()
        return predictions, confidences
