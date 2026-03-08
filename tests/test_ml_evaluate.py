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
        """
        Initialize the stub predictor and prepare storage for recorded service lists.
        
        Attributes:
            services_list (list | None): The services_list provided to predict_with_confidence_many; initially None.
        """
        self.services_list = None

    def predict_with_confidence_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
        rule_categories: list[str] | None = None,
        rule_warning_counts: list[int] | None = None,
    ) -> tuple[list[str], list[float]]:
        """
        Stubbed prediction method used by tests; records the provided service inputs and returns two fixed category predictions with corresponding confidence scores.
        
        Parameters:
            procedure_texts (list[str]): Ignored by this stub; present for API compatibility.
            services_list (list[list[str]] | None): Service token lists for each procedure; stored on the instance as `services_list`.
            rule_categories (list[str] | None): Ignored by this stub; present for API compatibility.
            rule_warning_counts (list[int] | None): Ignored by this stub; present for API compatibility.
        
        Returns:
            tuple[list[str], list[float]]: A tuple where the first element is the list of category values
            ["CARDIAC_WITH_CPB", "OTHER"] and the second element is the list of confidence scores [0.95, 0.62].
        """
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
        """
        Create a hybrid-classifier test stub instance and register it.
        
        Parameters:
            ml_predictor: The mock or real ML predictor used by the hybrid classifier.
            ml_threshold: Threshold score at which the ML predictor's decision is accepted.
        
        Notes:
            - Initializes `services_list` to None.
            - Appends the created instance to the class-level `created` list.
        """
        self.ml_predictor = ml_predictor
        self.ml_threshold = ml_threshold
        self.services_list = None
        type(self).created.append(self)

    def classify_many(
        self,
        procedure_texts: list[str],
        services_list: list[list[str]] | None = None,
    ) -> list[dict[str, object]]:
        """
        Record the provided services list and return two fixed classification entries for testing.
        
        Parameters:
            procedure_texts (list[str]): Ignored; present to match the classifier interface.
            services_list (list[list[str]] | None): Services extracted per case; stored on the instance as `self.services_list`.
        
        Returns:
            list[dict[str, object]]: Two dictionaries with a "category" key containing ProcedureCategory.CARDIAC_WITH_CPB and ProcedureCategory.INTRATHORACIC_NON_CARDIAC, respectively.
        """
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


def test_evaluate_model_handles_unclassified_hybrid_results(
    tmp_path,
    monkeypatch,
):
    """
    Verify evaluate.evaluate_model handles hybrid classifier entries with a None category by treating them as unclassified and including them in accuracy calculations.
    
    Creates a CSV with two cases, stubs an ML predictor and a hybrid classifier that returns `None` for the second case, runs `evaluate_model`, and asserts that `labeled_accuracy.hybrid_accuracy` equals 0.5 and the hybrid prediction for the unclassified case is "UNCLASSIFIED".
    """
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

    class _HybridWithMissingCategory(_StubHybridClassifier):
        def classify_many(
            self,
            procedure_texts: list[str],
            services_list: list[list[str]] | None = None,
        ) -> list[dict[str, object]]:
            """
            Classify a batch of procedure texts and store the supplied services_list on the instance (test stub).
            
            Parameters:
                procedure_texts (list[str]): Ignored in this stub implementation; present for API compatibility.
                services_list (list[list[str]] | None): Per-case service token lists; stored on the instance as `self.services_list`.
            
            Returns:
                list[dict[str, object]]: A list of classification result dicts with a "category" key. For this stub the first entry has
                `ProcedureCategory.CARDIAC_WITH_CPB` and the second entry has `None`.
            """
            del procedure_texts
            self.services_list = services_list
            return [
                {"category": ProcedureCategory.CARDIAC_WITH_CPB},
                {"category": None},
            ]

    monkeypatch.setattr(evaluate.MLPredictor, "load", lambda _path: predictor)
    monkeypatch.setattr(evaluate, "HybridClassifier", _HybridWithMissingCategory)

    summary = evaluate.evaluate_model(
        Path("ml_models/procedure_classifier.pkl"),
        csv_path,
        label_column="human_category",
    )

    assert summary.labeled_accuracy is not None
    assert summary.labeled_accuracy.hybrid_accuracy == pytest.approx(0.5)
    assert summary.disagreement_cases[0]["hybrid_prediction"] == "UNCLASSIFIED"


def test_evaluate_model_reports_labeled_rule_ml_and_hybrid_accuracy(
    tmp_path,
    monkeypatch,
):
    """
    Validates that evaluate.evaluate_model reports labeled, rule, ML, and hybrid accuracies correctly using stubbed predictor and hybrid classifier.
    
    Creates a CSV with two procedure records and human labels, patches the MLPredictor loader to return a stub predictor and replaces HybridClassifier with a stub implementation, runs evaluate.evaluate_model with a hybrid threshold of 0.6, and asserts that:
    - the labeled accuracy summary exists and references the correct label column and case count,
    - rule, ML, and hybrid accuracies match expected values (approximately 1.0, 0.5, and 1.0 respectively),
    - the model loader was called exactly once,
    - a single HybridClassifier instance was created with the stub predictor and provided threshold,
    - both predictor and hybrid classifier received normalized service inputs [["CARDIAC"], ["THOR"]],
    - there is exactly one disagreement case recorded.
    """
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
        """
        Increment the test load counter and return the stub predictor.
        
        Parameters:
            _path: Ignored path argument provided by the loader; not used.
        
        Returns:
            The `predictor` stub instance.
        """
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
