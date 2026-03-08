"""Tests for labeled evaluation workflow."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from case_parser.domain import ProcedureCategory
from ml_training import evaluate


class _StubPredictor:
    def __init__(self) -> None:
        self.services_list = None

    def predict_with_confidence_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
        rule_categories: list[str] | None = None,
        rule_warning_counts: list[int] | None = None,
    ) -> tuple[list[str], list[float]]:
        del procedure_texts, rule_categories, rule_warning_counts
        self.services_list = services_list
        return (
            [
                ProcedureCategory.CARDIAC_WITH_CPB.value,
                ProcedureCategory.OTHER.value,
            ],
            [0.95, 0.62],
        )


class _StubHybridClassifier:
    def __init__(self) -> None:
        self.services_list = None

    def classify_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
    ) -> list[dict[str, object]]:
        del procedure_texts
        self.services_list = services_list
        return [
            {"category": ProcedureCategory.CARDIAC_WITH_CPB},
            {"category": ProcedureCategory.INTRATHORACIC_NON_CARDIAC},
        ]


def test_evaluate_model_reports_labeled_rule_ml_and_hybrid_accuracy(
    tmp_path,
    monkeypatch,
):
    csv_path = tmp_path / "review.csv"
    pd.DataFrame([
        {
            "procedure": "CABG",
            "service_text": "CARDIAC",
            "human_category": ProcedureCategory.CARDIAC_WITH_CPB.value,
        },
        {
            "procedure": "THORACOTOMY",
            "service_text": "THOR",
            "human_category": ProcedureCategory.INTRATHORACIC_NON_CARDIAC.value,
        },
    ]).to_csv(csv_path, index=False)

    predictor = _StubPredictor()
    hybrid = _StubHybridClassifier()

    monkeypatch.setattr(evaluate.MLPredictor, "load", lambda _path: predictor)
    monkeypatch.setattr(
        evaluate.HybridClassifier,
        "load",
        lambda _path, ml_threshold: hybrid,
    )

    summary = evaluate.evaluate_model(
        Path("ml_models/procedure_classifier.pkl"),
        csv_path,
        label_column="human_category",
        hybrid_threshold=0.6,
    )

    assert summary.labeled_accuracy is not None
    assert summary.labeled_accuracy.label_column == "human_category"
    assert summary.labeled_accuracy.labeled_cases == 2
    assert summary.labeled_accuracy.rule_accuracy == pytest.approx(1.0)
    assert summary.labeled_accuracy.ml_accuracy == pytest.approx(0.5)
    assert summary.labeled_accuracy.hybrid_accuracy == pytest.approx(1.0)
    assert predictor.services_list == [["CARDIAC"], ["THOR"]]
    assert hybrid.services_list == [["CARDIAC"], ["THOR"]]
    assert len(summary.disagreement_cases) == 1
