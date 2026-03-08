#!/usr/bin/env python3
"""Evaluate rule, ML, and hybrid predictions on CSV datasets."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from case_parser.ml.config import DEFAULT_ML_THRESHOLD
from case_parser.ml.hybrid import ClassificationResult, HybridClassifier
from case_parser.ml.inputs import resolve_service_column
from case_parser.ml.predictor import MLPredictor
from case_parser.patterns.categorization import categorize_procedure

try:
    from ml_training.utils import normalize_category_label
except ImportError:
    from utils import normalize_category_label  # type: ignore[import-not-found]

console = Console()
LABEL_COLUMN_CANDIDATES = (
    "human_category",
    "category",
    "label",
    "review_label",
    "correct_category",
)
_OPTIONAL_VALUE_SENTINELS = {"<na>", "nan", "none"}
_HYBRID_UNCLASSIFIED = "UNCLASSIFIED"


@dataclass
class LabeledAccuracySummary:
    """Accuracy metrics when ground-truth labels are available."""

    label_column: str
    labeled_cases: int
    rule_accuracy: float
    ml_accuracy: float
    hybrid_accuracy: float


@dataclass
class EvaluationSummary:
    """Aggregated evaluation outputs."""

    total_cases: int
    high_confidence: int
    medium_confidence: int
    low_confidence: int
    agreement_count: int
    disagreement_cases: list[dict[str, Any]]
    labeled_accuracy: LabeledAccuracySummary | None = None


def _resolve_procedure_column(df: pd.DataFrame) -> str:
    """
    Selects which column in the DataFrame contains the procedure text.
    
    Parameters:
        df (pandas.DataFrame): DataFrame to inspect for known procedure text columns.
    
    Returns:
        str: The name of the procedure text column found ("AIMS_Actual_Procedure_Text" or "procedure").
    
    Raises:
        ValueError: If neither "AIMS_Actual_Procedure_Text" nor "procedure" is present in df.columns.
    """
    if "AIMS_Actual_Procedure_Text" in df.columns:
        return "AIMS_Actual_Procedure_Text"
    if "procedure" in df.columns:
        return "procedure"
    raise ValueError("No procedure column found")


def _resolve_label_column(
    df: pd.DataFrame,
    requested_column: str | None,
) -> str | None:
    """
    Selects which DataFrame column should be used as the ground-truth label.
    
    If a requested column name is provided, it must exist in the DataFrame; otherwise the function searches for the first known candidate column name and returns it.
    
    Parameters:
        requested_column (str | None): Optional explicit label column name to use. If provided and not found in `df`, a ValueError is raised.
    
    Returns:
        str | None: The chosen label column name, or `None` if no known candidate column exists.
    """
    if requested_column:
        if requested_column not in df.columns:
            raise ValueError(f"Label column not found: {requested_column}")
        return requested_column

    for candidate in LABEL_COLUMN_CANDIDATES:
        if candidate in df.columns:
            return candidate
    return None


def _split_services(value: str) -> list[str]:
    """
    Produce a list of service entries parsed from a newline-delimited string.
    
    Parameters:
    	value (str): Newline-delimited service text; entries may contain surrounding whitespace.
    
    Returns:
    	services (list[str]): Trimmed, non-empty service items in the original order; empty lines are discarded.
    """
    return [item.strip() for item in value.split("\n") if item.strip()]


def _build_service_inputs(
    df: pd.DataFrame,
    service_col: str | None,
    total_cases: int,
) -> tuple[list[list[str]] | None, list[list[str]]]:
    """
    Produce ML service inputs and per-case service rows for rule/hybrid processing.
    
    Parameters:
        df (pd.DataFrame): Source dataframe containing service column values.
        service_col (str | None): Name of the column with newline-delimited service strings, or `None` when no service information is available.
        total_cases (int): Number of cases (rows) in `df`; used to create empty placeholders when `service_col` is `None`.
    
    Returns:
        tuple:
            - ml_inputs (list[list[str]] | None): Per-case lists of service tokens for the ML path, or `None` if `service_col` is `None`.
            - service_rows (list[list[str]]): Per-case lists of individual services for rule/hybrid processing; contains an empty list for cases with no service information.
    """
    if service_col is None:
        return None, [[] for _ in range(total_cases)]

    normalized_services = [
        _normalize_optional_label(value)
        for value in df[service_col].tolist()
    ]
    service_rows = [
        _split_services(value) if value else []
        for value in normalized_services
    ]
    return service_rows, service_rows


def _normalize_optional_label(value: Any) -> str:
    """
    Normalize a ground-truth label value into a canonical label while preserving blank/missing semantics.
    
    Parameters:
        value (Any): Label value to normalize; may be NaN, an empty string, or an optional-value sentinel (e.g., "n/a", "none").
    
    Returns:
        str: The normalized category label, or an empty string when the input is missing, blank, or represents an optional/missing value.
    """
    if pd.isna(value):
        return ""

    text = str(value).strip()
    if not text:
        return ""
    if text.casefold() in _OPTIONAL_VALUE_SENTINELS:
        return ""
    return normalize_category_label(text)


def _normalize_hybrid_prediction(result: Any) -> str:
    """
    Normalize a hybrid-classifier output into a stable comparison token.
    
    Parameters:
        result (Any): The hybrid classifier output (may be a dict, an object with a `category` attribute, or `None`).
    
    Returns:
        str: A normalized category label suitable for comparison, or the sentinel `_HYBRID_UNCLASSIFIED` when the result or its category is missing.
    """
    if result is None:
        return _HYBRID_UNCLASSIFIED

    category = (
        result.get("category")
        if isinstance(result, dict)
        else getattr(result, "category", None)
    )
    if category is None:
        return _HYBRID_UNCLASSIFIED

    category_value = getattr(category, "value", category)
    return normalize_category_label(str(category_value))


def _print_header(
    model_path: Path,
    data_path: Path,
    total_cases: int,
    *,
    label_column: str | None,
    hybrid_threshold: float,
) -> None:
    """
    Prints a formatted evaluation header panel showing model and dataset metadata.
    
    Parameters:
        model_path (Path): Filesystem path to the trained model being evaluated.
        data_path (Path): Filesystem path to the input CSV dataset.
        total_cases (int): Number of cases (rows) included in the evaluation.
        label_column (str | None): Ground-truth label column used for labeled evaluation, or `None` if not provided.
        hybrid_threshold (float): Confidence threshold used by the hybrid classifier (0.0–1.0).
    """
    console.print(
        Panel(
            f"[bold]Evaluating Model[/bold]\n"
            f"Model: {model_path}\n"
            f"Data: {data_path}\n"
            f"Cases: {total_cases}\n"
            f"Label column: {label_column or 'None'}\n"
            f"Hybrid threshold: {hybrid_threshold:.2f}",
            title="Model Evaluation",
            border_style="cyan",
        )
    )


def _bin_confidence(score: float, bins: dict[str, int]) -> None:
    """
    Increment the appropriate confidence bin counter for a numerical score.
    
    Parameters:
        score (float): Confidence score between 0.0 and 1.0 used to determine the bin.
        bins (dict[str, int]): Mutable mapping with keys "high", "medium", and "low"; the function increments the matching bin's integer count in place.
    """
    if score >= 0.85:
        bins["high"] += 1
    elif score >= 0.7:
        bins["medium"] += 1
    else:
        bins["low"] += 1


def evaluate_model(  # noqa: PLR0914
    model_path: Path,
    data_path: Path,
    *,
    label_column: str | None = None,
    hybrid_threshold: float = DEFAULT_ML_THRESHOLD,
) -> EvaluationSummary:
    """
    Evaluate a trained model against procedures in a CSV and compute aggregated agreement, confidence, disagreement, and optional labeled accuracies.
    
    Parameters:
        model_path (Path): Path to the trained model file to load for evaluation.
        data_path (Path): Path to the CSV file containing procedure text and optional service/label columns.
        label_column (str | None): Optional explicit ground-truth label column name; when omitted the function will attempt to auto-detect a label column from known candidates.
        hybrid_threshold (float): Confidence threshold used by the hybrid classifier to decide when to prefer ML predictions.
    
    Returns:
        EvaluationSummary: Aggregated results including total case count, counts per confidence bin (high/medium/low), agreement count between ML and rule predictions, a list of disagreement case records, and an optional LabeledAccuracySummary when ground-truth labels are present.
    """
    predictor = MLPredictor.load(model_path)
    df = pd.read_csv(data_path)
    procedure_col = _resolve_procedure_column(df)
    service_col = resolve_service_column(df)
    resolved_label_column = _resolve_label_column(df, label_column)

    procedures = df[procedure_col].fillna("").astype(str).tolist()
    ml_service_inputs, service_rows = _build_service_inputs(
        df,
        service_col,
        len(procedures),
    )
    _print_header(
        model_path,
        data_path,
        len(procedures),
        label_column=resolved_label_column,
        hybrid_threshold=hybrid_threshold,
    )

    confidence_bins = {"high": 0, "medium": 0, "low": 0}
    disagreement_cases: list[dict[str, Any]] = []
    agreement_count = 0
    labeled_accuracy: LabeledAccuracySummary | None = None

    ml_pred_batch, ml_conf_batch = predictor.predict_with_confidence_many(
        procedures,
        services_list=ml_service_inputs,
    )
    hybrid_results: list[ClassificationResult] = []
    if resolved_label_column is not None:
        hybrid_results = HybridClassifier(
            predictor,
            ml_threshold=hybrid_threshold,
        ).classify_many(procedures, service_rows)
        normalized_labels = [
            _normalize_optional_label(value)
            for value in df[resolved_label_column].tolist()
        ]
        labeled_cases = 0
        rule_correct = 0
        ml_correct = 0
        hybrid_correct = 0
    else:
        normalized_labels = []

    for idx, procedure in enumerate(procedures):
        ml_pred = normalize_category_label(str(ml_pred_batch[idx]))
        ml_conf = float(ml_conf_batch[idx])

        rule_cat, _warnings = categorize_procedure(procedure, service_rows[idx])
        rule_pred = normalize_category_label(
            rule_cat.value if rule_cat else "Other (procedure cat)"
        )
        hybrid_pred = ""
        label = ""
        if resolved_label_column is not None:
            label = normalized_labels[idx]
            hybrid_result = hybrid_results[idx] if idx < len(hybrid_results) else None
            hybrid_pred = _normalize_hybrid_prediction(hybrid_result)
            if label:
                labeled_cases += 1
                rule_correct += int(rule_pred == label)
                ml_correct += int(ml_pred == label)
                hybrid_correct += int(hybrid_pred == label)

        _bin_confidence(ml_conf, confidence_bins)

        if ml_pred == rule_pred:
            agreement_count += 1
            continue

        disagreement_case = {
            "case_id": idx,
            "procedure": procedure,
            "ml_prediction": ml_pred,
            "rule_prediction": rule_pred,
            "confidence": ml_conf,
        }
        if resolved_label_column is not None:
            disagreement_case["hybrid_prediction"] = hybrid_pred
            disagreement_case["label"] = label

        disagreement_cases.append(disagreement_case)

    if resolved_label_column is not None:
        labeled_accuracy = LabeledAccuracySummary(
            label_column=resolved_label_column,
            labeled_cases=labeled_cases,
            rule_accuracy=(rule_correct / labeled_cases) if labeled_cases else 0.0,
            ml_accuracy=(ml_correct / labeled_cases) if labeled_cases else 0.0,
            hybrid_accuracy=(hybrid_correct / labeled_cases) if labeled_cases else 0.0,
        )

    return EvaluationSummary(
        total_cases=len(procedures),
        high_confidence=confidence_bins["high"],
        medium_confidence=confidence_bins["medium"],
        low_confidence=confidence_bins["low"],
        agreement_count=agreement_count,
        disagreement_cases=disagreement_cases,
        labeled_accuracy=labeled_accuracy,
    )


def _print_summary(summary: EvaluationSummary) -> None:
    """
    Render and print evaluation summaries (confidence distribution, agreement statistics, and optional labeled-ground-truth accuracies) to the console.
    
    Parameters:
        summary (EvaluationSummary): Aggregated evaluation results including total case count, confidence-bin counts (high/medium/low), agreement_count, disagreement_cases, and an optional labeled_accuracy summary. This function formats those fields into console tables and prints them; it does not return a value.
    """
    table = Table(title="Confidence Distribution", show_header=True)
    table.add_column("Confidence Level", style="cyan")
    table.add_column("Count", justify="right", style="yellow")
    table.add_column("Percentage", justify="right", style="green")

    levels = [
        ("High (>0.85)", summary.high_confidence),
        ("Medium (0.7-0.85)", summary.medium_confidence),
        ("Low (<0.7)", summary.low_confidence),
    ]
    for level, count in levels:
        percentage = (count / summary.total_cases) * 100
        table.add_row(level, str(count), f"{percentage:.1f}%")

    console.print("\n[bold]Evaluation Results:[/bold]\n")
    console.print(table)

    agreement_pct = (summary.agreement_count / summary.total_cases) * 100
    disagreement_count = len(summary.disagreement_cases)
    disagreement_pct = 100 - agreement_pct
    console.print(
        "\n[bold]Agreement with Rules:[/bold]"
        f"  Agrees: {summary.agreement_count} ({agreement_pct:.1f}%)"
        f"  Disagrees: {disagreement_count} ({disagreement_pct:.1f}%)"
    )

    if summary.labeled_accuracy is not None:
        accuracy = summary.labeled_accuracy
        accuracy_table = Table(title="Accuracy vs Ground Truth", show_header=True)
        accuracy_table.add_column("Signal", style="cyan")
        accuracy_table.add_column("Accuracy", justify="right", style="green")
        accuracy_table.add_row("Rules", f"{accuracy.rule_accuracy:.4f}")
        accuracy_table.add_row("ML", f"{accuracy.ml_accuracy:.4f}")
        accuracy_table.add_row("Hybrid", f"{accuracy.hybrid_accuracy:.4f}")
        console.print()
        console.print(accuracy_table)
        console.print(
            f"[bold]Labeled cases:[/bold] {accuracy.labeled_cases} "
            f"(column: {accuracy.label_column})"
        )


def _save_disagreements(disagreement_cases: list[dict[str, Any]]) -> None:
    """
    Write disagreement case records to ml_training_data/flagged_for_review.csv for human review.
    
    Parameters:
        disagreement_cases (list[dict[str, Any]]): Sequence of disagreement records (one dict per case). If empty, nothing is written.
    """
    if not disagreement_cases:
        return
    output_dir = Path("ml_training_data")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "flagged_for_review.csv"
    pd.DataFrame(disagreement_cases).to_csv(output_file, index=False)
    console.print(f"\n[yellow]Flagged cases saved to: {output_file}[/yellow]")


def build_parser() -> argparse.ArgumentParser:
    """
    Create and configure the command-line argument parser for the evaluation tool.
    
    Returns:
        argparse.ArgumentParser: Parser with positional arguments `model` and `data`,
        and optional `--label-column` and `--hybrid-threshold` options.
    """
    parser = argparse.ArgumentParser(description="Evaluate ML and hybrid models on CSV")
    parser.add_argument("model", type=Path, help="Path to model file")
    parser.add_argument("data", type=Path, help="Path to input CSV")
    parser.add_argument(
        "--label-column",
        help="Optional ground-truth label column (auto-detected when omitted)",
    )
    parser.add_argument(
        "--hybrid-threshold",
        type=float,
        default=DEFAULT_ML_THRESHOLD,
        help=(
            "Hybrid confidence threshold used for labeled accuracy "
            f"(default: {DEFAULT_ML_THRESHOLD:.2f})"
        ),
    )
    return parser


def main() -> int:
    """
    Run the CLI flow: validate inputs, evaluate the model on the CSV, print the summary, and save disagreements.
    
    Returns:
        int: 0 on success, 1 on validation error (missing model or data file, or invalid hybrid-threshold).
    """
    args = build_parser().parse_args()

    if not args.model.exists():
        console.print(f"[red]Error:[/red] Model not found: {args.model}")
        return 1

    if not args.data.exists():
        console.print(f"[red]Error:[/red] Data not found: {args.data}")
        return 1

    if not 0.0 <= args.hybrid_threshold <= 1.0:
        console.print(
            "[red]Error:[/red] --hybrid-threshold must be between 0.0 and 1.0"
        )
        return 1

    summary = evaluate_model(
        args.model,
        args.data,
        label_column=args.label_column,
        hybrid_threshold=args.hybrid_threshold,
    )
    _print_summary(summary)
    _save_disagreements(summary.disagreement_cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
