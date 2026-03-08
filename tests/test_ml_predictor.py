"""Tests for ML predictor loading and inference-time configuration."""

from __future__ import annotations

import pickle  # noqa: S403
import warnings
from collections import UserDict
from dataclasses import dataclass, field
from pathlib import Path

from case_parser.ml.config import BASE_DEFAULT_ML_INFERENCE_JOBS
from case_parser.ml.predictor import MLPredictor, ProcedureMLPipeline


@dataclass
class _DummyLeafEstimator:
    n_jobs: int


@dataclass
class _DummyModel:
    n_jobs: int = -1
    estimators: list[tuple[str, _DummyLeafEstimator]] = field(
        default_factory=lambda: [("rf", _DummyLeafEstimator(-1))]
    )
    estimators_: list[_DummyLeafEstimator] = field(
        default_factory=lambda: [_DummyLeafEstimator(-1)]
    )
    named_estimators_: dict[str, _DummyLeafEstimator] = field(init=False)

    def __post_init__(self) -> None:
        self.named_estimators_ = {"rf": self.estimators_[0]}


@dataclass
class _DummyPipeline:
    model: _DummyModel = field(default_factory=_DummyModel)


@dataclass
class _EchoFeatures:
    def transform(self, inputs):
        return inputs


@dataclass
class _EchoModel:
    classes_: list[str] = field(default_factory=list)

    def predict(self, inputs):
        return inputs


def _write_model(path: Path) -> None:
    with path.open("wb") as fh:
        pickle.dump({"pipeline": _DummyPipeline(), "metadata": {}}, fh)


def test_load_applies_explicit_inference_jobs_to_nested_estimators(tmp_path):
    model_path = tmp_path / "model.pkl"
    _write_model(model_path)

    predictor = MLPredictor.load(model_path, inference_jobs=1)

    assert predictor.inference_jobs == 1
    assert predictor.pipeline.model.n_jobs == 1
    assert predictor.pipeline.model.estimators[0][1].n_jobs == 1
    assert predictor.pipeline.model.estimators_[0].n_jobs == 1
    assert predictor.pipeline.model.named_estimators_["rf"].n_jobs == 1


def test_load_uses_runtime_env_for_inference_jobs(tmp_path, monkeypatch):
    model_path = tmp_path / "model.pkl"
    _write_model(model_path)
    monkeypatch.setenv("CASE_PARSER_ML_INFERENCE_JOBS", "-1")

    predictor = MLPredictor.load(model_path)

    assert predictor.inference_jobs == -1
    assert predictor.pipeline.model.n_jobs == -1
    assert predictor.pipeline.model.estimators_[0].n_jobs == -1


def test_load_validates_invalid_explicit_inference_jobs(tmp_path):
    model_path = tmp_path / "model.pkl"
    _write_model(model_path)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        predictor = MLPredictor.load(model_path, inference_jobs=0)

    assert predictor.inference_jobs == BASE_DEFAULT_ML_INFERENCE_JOBS
    assert predictor.pipeline.model.n_jobs == BASE_DEFAULT_ML_INFERENCE_JOBS
    assert len(caught) == 1
    assert "inference_jobs" in str(caught[0].message)


def test_coerce_inputs_treats_mapping_as_single_item():
    pipeline = ProcedureMLPipeline(_EchoModel(), _EchoFeatures())
    raw_input = UserDict({"procedure": "CABG"})

    assert pipeline.predict(raw_input) == [raw_input]
