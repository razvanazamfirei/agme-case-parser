"""Tests for ML auto-train helper logic."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from ml_training.auto_train import (
    PipelineError,
    SplitConfig,
    StageResult,
    _run_evaluate_stage,
    _validate_inputs,
    split_prepared_dataset,
)


def _write_prepared_csv(path: Path, labels: list[str]) -> None:
    pd.DataFrame({
        "procedure": [f"procedure {idx}" for idx in range(len(labels))],
        "rule_category": labels,
    }).to_csv(path, index=False)


def test_split_prepared_dataset_disables_stratify_when_partitions_are_too_small(
    tmp_path: Path,
):
    prepared = tmp_path / "prepared.csv"
    seen = tmp_path / "seen.csv"
    unseen = tmp_path / "unseen.csv"
    _write_prepared_csv(prepared, ["A", "A", "B", "B", "C", "C"])

    seen_count, unseen_count = split_prepared_dataset(
        SplitConfig(
            prepared_data=prepared,
            seen_data=seen,
            unseen_data=unseen,
            label_column="rule_category",
            unseen_ratio=0.2,
            split_seed=42,
        )
    )

    assert seen_count + unseen_count == 6
    assert len(pd.read_csv(seen)) == seen_count
    assert len(pd.read_csv(unseen)) == unseen_count


def test_split_prepared_dataset_rejects_empty_dataset(tmp_path: Path):
    prepared = tmp_path / "prepared.csv"
    seen = tmp_path / "seen.csv"
    unseen = tmp_path / "unseen.csv"
    pd.DataFrame({"procedure": [], "rule_category": []}).to_csv(prepared, index=False)

    with pytest.raises(ValueError, match="contains no rows to split"):
        split_prepared_dataset(
            SplitConfig(
                prepared_data=prepared,
                seen_data=seen,
                unseen_data=unseen,
                label_column="rule_category",
                unseen_ratio=0.2,
                split_seed=42,
            )
        )


def test_validate_inputs_requires_unseen_data_when_evaluating_without_split(
    tmp_path: Path,
):
    prepared = tmp_path / "prepared.csv"
    prepared.write_text("procedure,rule_category\n")
    model = tmp_path / "model.pkl"
    model.write_text("model")

    args = argparse.Namespace(
        case_dir=tmp_path,
        skip_prepare=True,
        prepared_data=prepared,
        skip_train=True,
        skip_evaluate=False,
        skip_split=True,
        unseen_data=tmp_path / "missing-unseen.csv",
        model_output=model,
    )

    with pytest.raises(PipelineError, match="Unseen holdout data not found"):
        _validate_inputs(args)


def test_run_evaluate_stage_runs_when_holdout_exists_even_if_skip_split(
    tmp_path: Path,
):
    unseen = tmp_path / "unseen.csv"
    unseen.write_text("procedure,rule_category\nexample,Other (procedure cat)\n")

    args = argparse.Namespace(
        skip_evaluate=False,
        skip_split=True,
        unseen_data=unseen,
        model_output=tmp_path / "model.pkl",
    )

    with patch(
        "ml_training.auto_train.run_stage",
        return_value=StageResult(
            name="Evaluate On Unseen",
            success=True,
            command="evaluate",
        ),
    ) as run_stage:
        result = _run_evaluate_stage(args)

    assert result is not None
    run_stage.assert_called_once()
