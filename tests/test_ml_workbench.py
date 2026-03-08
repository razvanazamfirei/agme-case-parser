"""Tests for evaluation handoff in the ML workbench."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from case_parser.ml.config import DEFAULT_ML_THRESHOLD
from ml_training import workbench


def test_evaluate_command_uses_defaults_for_optional_eval_args(tmp_path, monkeypatch):
    captured: dict[str, object] = {}
    eval_data = tmp_path / "eval.csv"

    monkeypatch.setattr(
        workbench,
        "_resolve_optional_data_path",
        lambda _data: eval_data,
    )

    def fake_run_script_stage(_name, _script_path, argv):
        """
        Act as a test double for running a script stage: capture the argv list and indicate successful execution.
        
        Parameters:
            _name: Ignored.
            _script_path: Ignored.
            argv: The argument list passed to the script; stored in captured["argv"].
        
        Returns:
            int: Exit code `0` indicating success.
        """
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(workbench, "_run_script_stage", fake_run_script_stage)

    rc = workbench._evaluate_command(
        argparse.Namespace(model="ml_models/procedure_classifier.pkl", data=None)
    )

    assert rc == 0
    assert captured["argv"] == [
        str(Path("ml_models/procedure_classifier.pkl").resolve()),
        str(eval_data),
        "--hybrid-threshold",
        str(DEFAULT_ML_THRESHOLD),
    ]


def test_run_command_chain_builds_complete_eval_args(tmp_path, monkeypatch):
    captured: dict[str, argparse.Namespace] = {}
    eval_data = tmp_path / "run-eval.csv"

    monkeypatch.setattr(workbench, "_train_command", lambda _args: 0)
    monkeypatch.setattr(
        workbench, "_resolve_eval_data_for_run", lambda _args: eval_data
    )
    monkeypatch.setattr(workbench, "_print_next_review_step", lambda *_args: None)

    def fake_evaluate_command(eval_args: argparse.Namespace) -> int:
        """
        Capture evaluation command arguments into the test's captured dictionary.
        
        Parameters:
            eval_args (argparse.Namespace): The evaluation command arguments to capture.
        
        Returns:
            int: `0` to indicate successful capture.
        """
        captured["args"] = eval_args
        return 0

    monkeypatch.setattr(workbench, "_evaluate_command", fake_evaluate_command)

    rc = workbench._run_command_chain(
        argparse.Namespace(
            model="ml_models/procedure_classifier.pkl",
            label_column="rule_category",
            eval_label_column=None,
            skip_evaluate=False,
            eval_data=None,
            prepared_data="prepared.csv",
            unseen_data="unseen.csv",
            skip_split=False,
        )
    )

    assert rc == 0
    assert captured["args"].model == "ml_models/procedure_classifier.pkl"
    assert captured["args"].data == eval_data
    assert captured["args"].label_column is None
    assert captured["args"].hybrid_threshold == DEFAULT_ML_THRESHOLD


def test_retrain_command_builds_complete_eval_args(monkeypatch):
    captured: dict[str, argparse.Namespace] = {}

    monkeypatch.setattr(
        workbench,
        "_prepare_override_retrain_datasets",
        lambda _args: workbench.RetrainMergeSummary(
            override_count=1,
            seen_overrides_applied=1,
            unseen_promoted=1,
            corrected_rows_weighted=1,
            rows_added_by_weighting=0,
            weighting_multiplier=workbench.OVERRIDE_CORRECTION_MULTIPLIER,
            retrain_rows=10,
            remaining_eval_rows=2,
        ),
    )
    monkeypatch.setattr(workbench, "_print_retrain_merge_summary", lambda *_args: None)
    monkeypatch.setattr(workbench, "_run_script_stage", lambda *_args: 0)

    def fake_evaluate_command(eval_args: argparse.Namespace) -> int:
        """
        Capture evaluation command arguments into the test's captured dictionary.
        
        Parameters:
            eval_args (argparse.Namespace): The evaluation command arguments to capture.
        
        Returns:
            int: `0` to indicate successful capture.
        """
        captured["args"] = eval_args
        return 0

    monkeypatch.setattr(workbench, "_evaluate_command", fake_evaluate_command)

    rc = workbench._retrain_command(
        argparse.Namespace(
            retrain_data_output="retrain.csv",
            model="ml_models/procedure_classifier.pkl",
            label_column="human_category",
            eval_label_column=None,
            cross_validate=False,
            skip_evaluate=False,
            eval_data_output="remaining.csv",
        )
    )

    assert rc == 0
    assert captured["args"].model == "ml_models/procedure_classifier.pkl"
    assert captured["args"].data == "remaining.csv"
    assert captured["args"].label_column is None
    assert captured["args"].hybrid_threshold == DEFAULT_ML_THRESHOLD


def test_run_command_chain_forwards_explicit_eval_label_column(
    tmp_path,
    monkeypatch,
):
    captured: dict[str, argparse.Namespace] = {}
    eval_data = tmp_path / "run-eval.csv"

    monkeypatch.setattr(workbench, "_train_command", lambda _args: 0)
    monkeypatch.setattr(
        workbench, "_resolve_eval_data_for_run", lambda _args: eval_data
    )
    monkeypatch.setattr(workbench, "_print_next_review_step", lambda *_args: None)

    def fake_evaluate_command(eval_args: argparse.Namespace) -> int:
        """
        Capture evaluation command arguments into the test's captured dictionary.
        
        Parameters:
            eval_args (argparse.Namespace): The evaluation command arguments to capture.
        
        Returns:
            int: `0` to indicate successful capture.
        """
        captured["args"] = eval_args
        return 0

    monkeypatch.setattr(workbench, "_evaluate_command", fake_evaluate_command)

    rc = workbench._run_command_chain(
        argparse.Namespace(
            model="ml_models/procedure_classifier.pkl",
            label_column="rule_category",
            eval_label_column="human_category",
            skip_evaluate=False,
            eval_data=None,
            prepared_data="prepared.csv",
            unseen_data="unseen.csv",
            skip_split=False,
        )
    )

    assert rc == 0
    assert captured["args"].label_column == "human_category"


def test_run_and_retrain_parsers_accept_hybrid_threshold():
    run_args = workbench.build_parser().parse_args([
        "run",
        "--hybrid-threshold",
        "0.55",
    ])
    retrain_args = workbench.build_parser().parse_args([
        "retrain",
        "--hybrid-threshold",
        "0.65",
    ])

    assert run_args.hybrid_threshold == pytest.approx(0.55)
    assert retrain_args.hybrid_threshold == pytest.approx(0.65)


def test_run_command_chain_forwards_explicit_hybrid_threshold(
    tmp_path,
    monkeypatch,
):
    captured: dict[str, argparse.Namespace] = {}
    eval_data = tmp_path / "run-eval.csv"

    monkeypatch.setattr(workbench, "_train_command", lambda _args: 0)
    monkeypatch.setattr(
        workbench, "_resolve_eval_data_for_run", lambda _args: eval_data
    )
    monkeypatch.setattr(workbench, "_print_next_review_step", lambda *_args: None)

    def fake_evaluate_command(eval_args: argparse.Namespace) -> int:
        """
        Capture evaluation command arguments into the test's captured dictionary.
        
        Parameters:
            eval_args (argparse.Namespace): The evaluation command arguments to capture.
        
        Returns:
            int: `0` to indicate successful capture.
        """
        captured["args"] = eval_args
        return 0

    monkeypatch.setattr(workbench, "_evaluate_command", fake_evaluate_command)

    rc = workbench._run_command_chain(
        argparse.Namespace(
            model="ml_models/procedure_classifier.pkl",
            label_column="rule_category",
            eval_label_column=None,
            hybrid_threshold=0.55,
            skip_evaluate=False,
            eval_data=None,
            prepared_data="prepared.csv",
            unseen_data="unseen.csv",
            skip_split=False,
        )
    )

    assert rc == 0
    assert captured["args"].hybrid_threshold == pytest.approx(0.55)


def test_run_review_interface_mentions_classic_fallback_on_tui_failure(monkeypatch):
    printed: list[str] = []
    expected = workbench.ReviewSessionMetrics(reviewed_this_session=1)
    runtime = workbench.ReviewRuntime(
        paths=workbench.ReviewPaths(
            model_path=Path("model.pkl"),
            data_path=Path("data.csv"),
            output_path=Path("out.csv"),
            progress_path=Path("progress.json"),
        ),
        config=workbench.ReviewConfig(
            focus="priority",
            low_confidence=0.8,
            max_cases=10,
            ui_mode="tui",
            resume=False,
        ),
        reviewed_indices=set(),
    )

    monkeypatch.setattr(workbench, "_resolve_review_ui_mode", lambda _config: "tui")
    monkeypatch.setattr(
        workbench,
        "_run_tui_review_session",
        lambda _queue, _runtime: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        workbench,
        "_run_review_classic",
        lambda _queue, _runtime: expected,
    )
    monkeypatch.setattr(
        workbench.console,
        "print",
        lambda message: printed.append(str(message)),
    )

    result = workbench._run_review_interface([], runtime)

    assert result is expected
    assert any("falling back to classic mode" in message for message in printed)
