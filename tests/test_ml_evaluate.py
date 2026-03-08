"""Tests for labeled evaluation workflow."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

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
    created: ClassVar[list[_StubHybridClassifier]] = []

    def __init__(self, ml_predictor, ml_threshold) -> None:
        self.ml_predictor = ml_predictor
        self.ml_threshold = ml_threshold
        self.services_list = None
        type(self).created.append(self)

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


@pytest.mark.parametrize("value", ["None", " none ", "<NA>", "NaN", "nan"])
def test_normalize_optional_label_treats_sentinels_as_missing(value):
    assert evaluate._normalize_optional_label(value) == ""


def test_build_service_inputs_normalizes_sentinel_service_values():
    df = pd.DataFrame({
        "service_text": [
            "CARDIAC\nTHOR",
            "None",
            pd.NA,
            "  <NA>  ",
            "nan",
        ]
    })

    ml_inputs, service_rows = evaluate._build_service_inputs(
        df,
        "service_text",
        total_cases=len(df),
    )

    assert ml_inputs == [["CARDIAC", "THOR"], [], [], [], []]
    assert service_rows == ml_inputs


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
    _StubHybridClassifier.created.clear()

    load_calls = {"count": 0}

    def fake_load(_path):
        load_calls["count"] += 1
        return predictor

    monkeypatch.setattr(evaluate.MLPredictor, "load", fake_load)
    monkeypatch.setattr(evaluate, "HybridClassifier", _StubHybridClassifier)

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
    assert load_calls["count"] == 1
    assert len(_StubHybridClassifier.created) == 1
    assert _StubHybridClassifier.created[0].ml_predictor is predictor
    assert _StubHybridClassifier.created[0].ml_threshold == pytest.approx(0.6)
    assert predictor.services_list == [["CARDIAC"], ["THOR"]]
    assert _StubHybridClassifier.created[0].services_list == [["CARDIAC"], ["THOR"]]
    assert len(summary.disagreement_cases) == 1
