#!/usr/bin/env python3
"""Deterministic end-to-end ML training entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sklearn.model_selection import train_test_split
from utils import run_python_script

from case_parser.ml.predictor import MLPredictor

try:
    from ml_training.utils import normalize_category_label
except ModuleNotFoundError:
    from utils import normalize_category_label


console = Console()

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CASE_DIR = PROJECT_ROOT / "Output-Supervised" / "case-list"
DEFAULT_PREPARED_DATA = PROJECT_ROOT / "ml_training_data" / "batch_prepared.csv"
DEFAULT_SEEN_DATA = PROJECT_ROOT / "ml_training_data" / "seen_train.csv"
DEFAULT_UNSEEN_DATA = PROJECT_ROOT / "ml_training_data" / "unseen_eval.csv"
DEFAULT_MODEL_OUTPUT = PROJECT_ROOT / "ml_models" / "procedure_classifier.pkl"


@dataclass
class StageResult:
    """Execution result for a pipeline stage."""

    name: str
    success: bool
    command: str


@dataclass
class SplitConfig:
    """Configuration for seen/unseen split generation."""

    prepared_data: Path
    seen_data: Path
    unseen_data: Path
    label_column: str
    unseen_ratio: float
    split_seed: int


class PipelineError(RuntimeError):
    """Raised when a pipeline stage fails."""


def run_stage(name: str, command: str, action: Callable[[], int]) -> StageResult:
    """Run one stage and return a normalized result.

    Args:
        name: Human-readable name of the pipeline stage.
        command: Command string to display when running the stage.
        action: Callable that runs the stage and returns an integer exit code.
    Returns:
        StageResult with name, success flag, and command string.
    """
    console.print(f"\n[cyan]{name}[/cyan]")
    console.print(f"[dim]$ {command}[/dim]")
    exit_code = action()
    return StageResult(name=name, success=exit_code == 0, command=command)


def validate_model_artifact(model_path: Path) -> None:
    """Validate that runtime loader can open and use the trained model."""
    predictor = MLPredictor.load(model_path)
    predictor.predict("CABG WITH CARDIOPULMONARY BYPASS")
    predictor.get_confidence("ENDOVASCULAR REPAIR OF AORTA")


def split_prepared_dataset(config: SplitConfig) -> tuple[int, int]:
    """Split prepared data into seen (train) and unseen (holdout) sets.

    Args:
        config: Split configuration specifying paths, ratios, and the label column.

    Returns:
        Tuple of (seen_count, unseen_count) rows written to each split file.

    Raises:
        ValueError: If unseen_ratio is not between 0 and 1, or if the label
            column is not found in the prepared dataset.
    """
    if not 0.0 < config.unseen_ratio < 1.0:
        raise ValueError(
            f"unseen-ratio must be between 0 and 1, got {config.unseen_ratio}"
        )

    df = pd.read_csv(config.prepared_data)
    if config.label_column not in df.columns:
        raise ValueError(
            f"Label column '{config.label_column}' not found in {config.prepared_data}"
        )

    normalized_labels = (
        df[config.label_column]
        .fillna("Other (procedure cat)")
        .astype(str)
        .map(normalize_category_label)
    )
    df = df.copy()
    df[config.label_column] = normalized_labels

    counts = normalized_labels.value_counts()
    stratify_labels = normalized_labels if int(counts.min()) >= 2 else None
    if stratify_labels is None:
        console.print(
            "[yellow]Split warning:[/yellow] "
            f"least-populated class has {int(counts.min())} sample(s), "
            "falling back to non-stratified split."
        )

    seen_df, unseen_df = train_test_split(
        df,
        test_size=config.unseen_ratio,
        random_state=config.split_seed,
        stratify=stratify_labels,
    )

    config.seen_data.parent.mkdir(parents=True, exist_ok=True)
    config.unseen_data.parent.mkdir(parents=True, exist_ok=True)
    seen_df.to_csv(config.seen_data, index=False)
    unseen_df.to_csv(config.unseen_data, index=False)

    return len(seen_df), len(unseen_df)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for auto-training pipeline.

    Returns:
        Configured ArgumentParser for the auto-training pipeline.
    """
    parser = argparse.ArgumentParser(
        description="Run the full ML training pipeline with explicit stages."
    )
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=DEFAULT_CASE_DIR,
        help=f"Input case-list directory (default: {DEFAULT_CASE_DIR})",
    )
    parser.add_argument(
        "--prepared-data",
        type=Path,
        default=DEFAULT_PREPARED_DATA,
        help=f"Prepared dataset output path (default: {DEFAULT_PREPARED_DATA})",
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=DEFAULT_MODEL_OUTPUT,
        help=f"Model output path (default: {DEFAULT_MODEL_OUTPUT})",
    )
    parser.add_argument(
        "--total-sample",
        type=int,
        default=50000,
        help="Target sample size for prepared dataset (default: 50000)",
    )
    parser.add_argument(
        "--sample-per-file",
        type=int,
        default=None,
        help="Optional per-file cap during preparation",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel workers for data prep (default: 8)",
    )
    parser.add_argument(
        "--label-column",
        default="rule_category",
        help="Label column used by trainer (default: rule_category)",
    )
    parser.add_argument(
        "--seen-data",
        type=Path,
        default=DEFAULT_SEEN_DATA,
        help=f"Seen/training split output path (default: {DEFAULT_SEEN_DATA})",
    )
    parser.add_argument(
        "--unseen-data",
        type=Path,
        default=DEFAULT_UNSEEN_DATA,
        help=f"Unseen/holdout split output path (default: {DEFAULT_UNSEEN_DATA})",
    )
    parser.add_argument(
        "--unseen-ratio",
        type=float,
        default=0.2,
        help="Fraction of prepared data reserved for unseen holdout (default: 0.2)",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=42,
        help="Random seed for seen/unseen split (default: 42)",
    )
    parser.add_argument(
        "--skip-prepare",
        action="store_true",
        help="Skip data preparation stage",
    )
    parser.add_argument(
        "--skip-split",
        action="store_true",
        help="Skip seen/unseen split stage (train directly on prepared data)",
    )
    parser.add_argument(
        "--skip-train",
        action="store_true",
        help="Skip model training stage",
    )
    parser.add_argument(
        "--skip-evaluate",
        action="store_true",
        help="Skip unseen holdout evaluation stage",
    )
    parser.add_argument(
        "--cross-validate",
        action="store_true",
        help="Enable 5-fold cross-validation during training",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing prepared/model files",
    )
    return parser


def _print_header(args: argparse.Namespace) -> None:
    console.print(
        Panel.fit(
            "[bold cyan]ML Auto Training[/bold cyan]\n"
            f"Case dir: {args.case_dir}\n"
            f"Prepared data: {args.prepared_data}\n"
            f"Seen data: {args.seen_data}\n"
            f"Unseen data: {args.unseen_data}\n"
            f"Model output: {args.model_output}",
            border_style="cyan",
        )
    )


def _validate_inputs(args: argparse.Namespace) -> None:
    if not args.skip_prepare and not args.case_dir.exists():
        raise PipelineError(f"Case directory not found: {args.case_dir}")

    if args.skip_prepare and not args.prepared_data.exists():
        raise PipelineError(
            f"Prepared data not found for --skip-prepare: {args.prepared_data}"
        )

    if args.skip_train and not args.skip_evaluate and not args.model_output.exists():
        raise PipelineError(
            f"Model output not found for evaluation: {args.model_output}"
        )


def _prepare_output_dirs(args: argparse.Namespace) -> None:
    args.prepared_data.parent.mkdir(parents=True, exist_ok=True)
    args.seen_data.parent.mkdir(parents=True, exist_ok=True)
    args.unseen_data.parent.mkdir(parents=True, exist_ok=True)
    args.model_output.parent.mkdir(parents=True, exist_ok=True)


def _validate_overwrite_behavior(args: argparse.Namespace) -> None:
    if args.force:
        return

    if not args.skip_prepare and args.prepared_data.exists():
        raise PipelineError(
            f"Prepared data exists, use --force to regenerate: {args.prepared_data}"
        )

    if not args.skip_train and args.model_output.exists():
        raise PipelineError(
            f"Model output exists, use --force to overwrite: {args.model_output}"
        )

    if not args.skip_split and (args.seen_data.exists() or args.unseen_data.exists()):
        raise PipelineError(
            "Seen/unseen split files exist, use --force to overwrite: "
            f"{args.seen_data}, {args.unseen_data}"
        )


def _run_prepare_stage(args: argparse.Namespace) -> StageResult | None:
    if args.skip_prepare:
        return None

    script = PROJECT_ROOT / "ml_training" / "batch_prepare.py"
    argv = [
        str(args.case_dir),
        "--output",
        str(args.prepared_data),
        "--total-sample",
        str(args.total_sample),
        "--workers",
        str(args.workers),
    ]
    if args.sample_per_file is not None:
        argv.extend(["--sample-per-file", str(args.sample_per_file)])

    command = " ".join([sys.executable, str(script), *argv])
    result = run_stage(
        name="Prepare Data",
        command=command,
        action=lambda: run_python_script(script, argv),
    )
    if not result.success:
        raise PipelineError("Prepare data stage failed")
    return result


def _run_split_stage(args: argparse.Namespace) -> StageResult | None:
    if args.skip_split:
        return None

    split_config = SplitConfig(
        prepared_data=args.prepared_data,
        seen_data=args.seen_data,
        unseen_data=args.unseen_data,
        label_column=args.label_column,
        unseen_ratio=args.unseen_ratio,
        split_seed=args.split_seed,
    )

    try:
        seen_count, unseen_count = split_prepared_dataset(split_config)
    except Exception as exc:
        raise PipelineError(f"Seen/unseen split failed: {exc}") from exc

    split_command = (
        f"split {args.prepared_data} -> {args.seen_data} ({seen_count}), "
        f"{args.unseen_data} ({unseen_count})"
    )
    return StageResult(name="Split Seen/Unseen", success=True, command=split_command)


def _run_train_stage(args: argparse.Namespace) -> list[StageResult]:
    if args.skip_train:
        return []

    train_input = args.seen_data if not args.skip_split else args.prepared_data
    train_script = PROJECT_ROOT / "ml_training" / "train_optimized.py"
    train_argv = [
        str(train_input),
        "--output",
        str(args.model_output),
        "--label-column",
        args.label_column,
    ]
    if args.cross_validate:
        train_argv.append("--cross-validate")

    train_command = " ".join([sys.executable, str(train_script), *train_argv])
    train_result = run_stage(
        name="Train Model",
        command=train_command,
        action=lambda: run_python_script(train_script, train_argv),
    )
    if not train_result.success:
        raise PipelineError("Train model stage failed")

    try:
        validate_model_artifact(args.model_output)
    except Exception as exc:
        raise PipelineError(f"Model artifact validation failed: {exc}") from exc

    validate_result = StageResult(
        name="Validate Artifact",
        success=True,
        command=f"load {args.model_output}",
    )
    return [train_result, validate_result]


def _run_evaluate_stage(args: argparse.Namespace) -> StageResult | None:
    should_evaluate = (
        not args.skip_evaluate and not args.skip_split and args.unseen_data.exists()
    )
    if not should_evaluate:
        return None

    eval_script = PROJECT_ROOT / "ml_training" / "evaluate.py"
    eval_argv = [str(args.model_output), str(args.unseen_data)]
    eval_command = " ".join([sys.executable, str(eval_script), *eval_argv])
    eval_result = run_stage(
        name="Evaluate On Unseen",
        command=eval_command,
        action=lambda: run_python_script(eval_script, eval_argv),
    )
    if not eval_result.success:
        raise PipelineError("Evaluate stage failed")
    return eval_result


def _print_summary(results: list[StageResult], model_output: Path) -> None:
    summary = Table(title="Pipeline Summary", border_style="cyan")
    summary.add_column("Stage", style="cyan")
    summary.add_column("Status")
    summary.add_column("Command", overflow="fold")

    for result in results:
        status = "[green]OK[/green]" if result.success else "[red]FAILED[/red]"
        summary.add_row(result.name, status, result.command)

    console.print()
    console.print(summary)
    console.print(f"\n[green]Pipeline complete.[/green] Model ready at: {model_output}")


def main() -> int:
    """Run configured pipeline stages.

    Returns:
        0 on success, 1 if any pipeline stage fails.
    """
    args = build_parser().parse_args()
    _print_header(args)

    try:
        _validate_inputs(args)
        _prepare_output_dirs(args)
        _validate_overwrite_behavior(args)

        results: list[StageResult] = []
        prepare_result = _run_prepare_stage(args)
        if prepare_result is not None:
            results.append(prepare_result)

        split_result = _run_split_stage(args)
        if split_result is not None:
            results.append(split_result)

        results.extend(_run_train_stage(args))

        eval_result = _run_evaluate_stage(args)
        if eval_result is not None:
            results.append(eval_result)

        _print_summary(results, args.model_output)
        return 0
    except PipelineError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
