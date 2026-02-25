#!/usr/bin/env python3
"""Batch preparation of training data from multiple case files."""

from __future__ import annotations

import argparse
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from case_parser.patterns.categorization import categorize_procedure

console = Console()


def process_single_file(
    file_path: Path, sample_size: int | None = None
) -> dict[str, Any]:
    """Process a single CSV file and extract cases with rule-based categorization.

    Args:
        file_path: Path to the CSV file to process.
        sample_size: Optional maximum number of rows to sample from the file.

    Returns:
        Dict with keys "file", "total_rows", "valid_cases", and "cases" on
        success, or "file" and "error" on failure.
    """
    try:
        df = pd.read_csv(file_path)
        if sample_size and len(df) > sample_size:
            df = df.sample(n=sample_size, random_state=42)

        cases: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            procedure = str(row.get("AIMS_Actual_Procedure_Text", ""))
            if not procedure or procedure == "nan":
                continue

            category, warnings = categorize_procedure(procedure, [])
            cases.append(
                {
                    "file": file_path.name,
                    "procedure": procedure,
                    "rule_category": category,
                    "warnings": "; ".join(warnings) if warnings else "",
                    "age": row.get("AIMS_Patient_Age_Years"),
                    "asa": row.get("ASA_Status"),
                    "emergency": row.get("Emergency"),
                }
            )

        return {
            "file": file_path.name,
            "total_rows": len(df),
            "valid_cases": len(cases),
            "cases": cases,
        }
    except Exception as exc:
        return {"file": file_path.name, "error": str(exc), "cases": []}


def smart_sample_cases(
    all_cases: list[dict[str, Any]], target_size: int
) -> list[dict[str, Any]]:
    """Smart sampling to maximize training value.

    Args:
        all_cases: Full list of case dicts to sample from.
        target_size: Maximum number of cases to include in the sample.

    Returns:
        Shuffled list of up to target_size cases, weighted toward high-value
        and medium-value examples.
    """
    high_value: list[dict[str, Any]] = []
    medium_value: list[dict[str, Any]] = []
    low_value: list[dict[str, Any]] = []

    high_value_keywords = {
        "CARDIAC",
        "CABG",
        "VALVE",
        "BYPASS",
        "CRANIOTOMY",
        "INTRACRANIAL",
        "ENDOVASCULAR",
        "TAVR",
        "ECMO",
        "VASCULAR",
    }

    for case in all_cases:
        score = 0
        if case["warnings"]:
            score += 5
        if case["rule_category"] != "Other (procedure cat)":
            score += 3

        proc_upper = str(case["procedure"]).upper()
        if any(keyword in proc_upper for keyword in high_value_keywords):
            score += 2

        if score >= 7:
            high_value.append(case)
        elif score >= 3:
            medium_value.append(case)
        else:
            low_value.append(case)

    n_high = min(len(high_value), int(target_size * 0.5))
    n_medium = min(len(medium_value), int(target_size * 0.3))
    n_low = min(len(low_value), target_size - n_high - n_medium)

    random.seed(42)
    sampled = (
        random.sample(high_value, n_high)
        + random.sample(medium_value, n_medium)
        + random.sample(low_value, n_low)
    )
    random.shuffle(sampled)
    return sampled


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser.

    Returns:
        Configured ArgumentParser for the batch preparation tool.
    """
    parser = argparse.ArgumentParser(
        description="Batch prepare training data from multiple case files"
    )
    parser.add_argument(
        "input_dir", type=Path, help="Directory containing case CSV files"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ml_training_data/batch_prepared.csv"),
        help="Output CSV file",
    )
    parser.add_argument(
        "--sample-per-file",
        type=int,
        help="Max cases to sample from each file (default: all)",
    )
    parser.add_argument(
        "--total-sample",
        type=int,
        default=50000,
        help="Total cases to include in final dataset (default: 50000)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers (default: 8)",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show statistics without generating output",
    )
    return parser


def _print_header(input_dir: Path, workers: int) -> None:
    console.print(
        Panel.fit(
            "[cyan]Batch Training Data Preparation[/cyan]\n"
            f"Input: {input_dir}\n"
            f"Workers: {workers}",
            border_style="cyan",
        )
    )


def _collect_cases(
    csv_files: list[Path], workers: int, sample_per_file: int | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_cases: list[dict[str, Any]] = []
    file_stats: list[dict[str, Any]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            f"Processing {len(csv_files)} files...", total=len(csv_files)
        )

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(process_single_file, file_path, sample_per_file)
                for file_path in csv_files
            ]

            for future in as_completed(futures):
                result = future.result()
                file_stats.append(result)
                all_cases.extend(result.get("cases", []))
                progress.advance(task_id)

    return all_cases, file_stats


def _print_processing_stats(
    csv_files: list[Path],
    file_stats: list[dict[str, Any]],
    all_cases: list[dict[str, Any]],
) -> None:
    total_cases = sum(int(item.get("valid_cases", 0)) for item in file_stats)
    files_with_errors = sum(1 for item in file_stats if "error" in item)

    stats_table = Table(title="Processing Statistics", border_style="cyan")
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="white")
    stats_table.add_row("Files Processed", str(len(csv_files)))
    stats_table.add_row("Files with Errors", str(files_with_errors))
    stats_table.add_row("Total Cases Extracted", str(total_cases))
    stats_table.add_row("Cases in Memory", str(len(all_cases)))
    console.print(stats_table)


def _print_category_distribution(cases: list[dict[str, Any]]) -> None:
    category_counts: dict[str, int] = {}
    for case in cases:
        category = str(case["rule_category"])
        category_counts[category] = category_counts.get(category, 0) + 1

    dist_table = Table(title="Category Distribution", border_style="yellow")
    dist_table.add_column("Category", style="yellow")
    dist_table.add_column("Count", justify="right")
    dist_table.add_column("Percentage", justify="right")

    total_count = len(cases)
    for category, count in sorted(category_counts.items(), key=lambda item: -item[1]):
        percentage = (count / total_count) * 100 if total_count else 0.0
        dist_table.add_row(category, str(count), f"{percentage:.1f}%")

    console.print(dist_table)


def _save_sampled_dataset(
    sampled_cases: list[dict[str, Any]], output_path: Path
) -> None:
    sampled_df = pd.DataFrame(sampled_cases)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sampled_df.to_csv(output_path, index=False)

    console.print(f"\n[green]Saved {len(sampled_cases)} cases to {output_path}[/green]")

    sample_dist = sampled_df["rule_category"].value_counts()
    sample_table = Table(title="Sampled Dataset Distribution", border_style="green")
    sample_table.add_column("Category", style="green")
    sample_table.add_column("Count", justify="right")
    sample_table.add_column("Percentage", justify="right")

    for category, count in sample_dist.items():
        percentage = (count / len(sampled_cases)) * 100
        sample_table.add_row(str(category), str(count), f"{percentage:.1f}%")

    console.print(sample_table)


def _print_next_steps(output_path: Path) -> None:
    run_cmd = (
        "python ml_training/workbench.py run --skip-prepare "
        f"--prepared-data {output_path} --force"
    )
    review_cmd = (
        "python ml_training/workbench.py review "
        "--data ml_training_data/unseen_eval.csv --resume"
    )
    console.print(
        f"\n[cyan]Next steps:[/cyan]\n"
        "1. Train/evaluate with seen/unseen split:\n"
        f"   {run_cmd}\n"
        "2. Review corrections in TUI:\n"
        f"   {review_cmd}"
    )


def main() -> int:
    """Process all case files and prepare training dataset.

    Returns:
        0 on success, 1 if no CSV files are found in the input directory.
    """
    args = build_parser().parse_args()
    _print_header(args.input_dir, args.workers)

    csv_files = list(args.input_dir.glob("*.csv"))
    if not csv_files:
        console.print("[red]No CSV files found in input directory[/red]")
        return 1

    all_cases, file_stats = _collect_cases(
        csv_files=csv_files,
        workers=args.workers,
        sample_per_file=args.sample_per_file,
    )
    _print_processing_stats(csv_files, file_stats, all_cases)
    _print_category_distribution(all_cases)

    if args.stats_only:
        return 0

    console.print(
        f"\n[cyan]Applying smart sampling to select {args.total_sample} cases...[/cyan]"
    )
    sampled_cases = smart_sample_cases(all_cases, args.total_sample)
    _save_sampled_dataset(sampled_cases, args.output)
    _print_next_steps(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
