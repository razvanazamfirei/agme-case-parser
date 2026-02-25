#!/usr/bin/env python3
"""Evaluate ML model predictions on unlabeled data."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from case_parser.ml.predictor import MLPredictor
from case_parser.patterns.categorization import categorize_procedure

try:
    from ml_training.utils import normalize_category_label
except ModuleNotFoundError:
    from utils import normalize_category_label


console = Console()


@dataclass
class EvaluationSummary:
    """Aggregated evaluation outputs."""

    total_cases: int
    high_confidence: int
    medium_confidence: int
    low_confidence: int
    agreement_count: int
    disagreement_cases: list[dict[str, Any]]


def _resolve_procedure_column(df: pd.DataFrame) -> str:
    if "AIMS_Actual_Procedure_Text" in df.columns:
        return "AIMS_Actual_Procedure_Text"
    if "procedure" in df.columns:
        return "procedure"
    raise ValueError("No procedure column found")


def _print_header(model_path: Path, data_path: Path, total_cases: int) -> None:
    console.print(
        Panel(
            f"[bold]Evaluating Model[/bold]\n"
            f"Model: {model_path}\n"
            f"Data: {data_path}\n"
            f"Cases: {total_cases}",
            title="Model Evaluation",
            border_style="cyan",
        )
    )


def _bin_confidence(score: float, bins: dict[str, int]) -> None:
    if score >= 0.85:
        bins["high"] += 1
    elif score >= 0.7:
        bins["medium"] += 1
    else:
        bins["low"] += 1


def evaluate_model(model_path: Path, data_path: Path) -> EvaluationSummary:
    """Evaluate model on a CSV file and return aggregate metrics.

    Args:
        model_path: Path to the trained model file to load for evaluation.
        data_path: Path to the CSV file containing procedures to evaluate.
    Returns:
        EvaluationSummary with confidence distribution and disagreement cases.
    """
    predictor = MLPredictor.load(model_path)
    df = pd.read_csv(data_path)
    procedure_col = _resolve_procedure_column(df)

    procedures = df[procedure_col].fillna("").astype(str).tolist()
    _print_header(model_path, data_path, len(procedures))

    confidence_bins = {"high": 0, "medium": 0, "low": 0}
    disagreement_cases: list[dict[str, Any]] = []
    agreement_count = 0

    ml_pred_batch = predictor.pipeline.predict(procedures)
    ml_proba_batch = predictor.pipeline.predict_proba(procedures)
    ml_conf_batch = ml_proba_batch.max(axis=1)

    for idx, procedure in enumerate(procedures):
        ml_pred = normalize_category_label(str(ml_pred_batch[idx]))
        ml_conf = float(ml_conf_batch[idx])

        rule_cat, _warnings = categorize_procedure(procedure, [])
        rule_pred = normalize_category_label(
            rule_cat.value if rule_cat else "Other (procedure cat)"
        )

        _bin_confidence(ml_conf, confidence_bins)

        if ml_pred == rule_pred:
            agreement_count += 1
            continue

        disagreement_cases.append(
            {
                "case_id": idx,
                "procedure": procedure,
                "ml_prediction": ml_pred,
                "rule_prediction": rule_pred,
                "confidence": ml_conf,
            }
        )

    return EvaluationSummary(
        total_cases=len(procedures),
        high_confidence=confidence_bins["high"],
        medium_confidence=confidence_bins["medium"],
        low_confidence=confidence_bins["low"],
        agreement_count=agreement_count,
        disagreement_cases=disagreement_cases,
    )


def _print_summary(summary: EvaluationSummary) -> None:
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


def _save_disagreements(disagreement_cases: list[dict[str, Any]]) -> None:
    if not disagreement_cases:
        return
    output_dir = Path("ml_training_data")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "flagged_for_review.csv"
    pd.DataFrame(disagreement_cases).to_csv(output_file, index=False)
    console.print(f"\n[yellow]Flagged cases saved to: {output_file}[/yellow]")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser.

    Returns:
        Configured ArgumentParser for the evaluation tool.
    """
    parser = argparse.ArgumentParser(description="Evaluate ML model on unlabeled data")
    parser.add_argument("model", type=Path, help="Path to model file")
    parser.add_argument("data", type=Path, help="Path to input CSV")
    return parser


def main() -> int:
    """Main entry point.

    Returns:
        0 on success, 1 if the model or data file is not found.
    """
    args = build_parser().parse_args()

    if not args.model.exists():
        console.print(f"[red]Error:[/red] Model not found: {args.model}")
        return 1

    if not args.data.exists():
        console.print(f"[red]Error:[/red] Data not found: {args.data}")
        return 1

    summary = evaluate_model(args.model, args.data)
    _print_summary(summary)
    _save_disagreements(summary.disagreement_cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
