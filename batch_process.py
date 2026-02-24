"""Batch process all residents from Output-Supervised into individual Excel files."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from src.case_parser.io import (
    CsvHandler,
    ExcelHandler,
    join_case_and_procedures,
)
from src.case_parser.models import ColumnMap
from src.case_parser.processor import CaseProcessor

# Suppress noisy logging from the pipeline
logging.getLogger("case_parser").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ProcessConfig:
    output_dir: Path
    columns: ColumnMap
    excel_handler: ExcelHandler


def find_resident_pairs(case_dir: Path, proc_dir: Path) -> list[tuple[str, Path, Path]]:
    """Find matching case/procedure file pairs."""
    case_files = {
        f.name.replace(".Supervised.CaseList.csv", ""): f
        for f in case_dir.glob("*.CaseList.csv")
    }
    proc_files = {
        f.name.replace(".Supervised.ProcedureList.csv", ""): f
        for f in proc_dir.glob("*.ProcedureList.csv")
    }
    common = sorted(set(case_files) & set(proc_files))
    return [(name, case_files[name], proc_files[name]) for name in common]


def format_name(name: str) -> str:
    """LAST_FIRST -> First Last."""
    parts = name.split("_", 1)
    if len(parts) == 2:
        return f"{parts[1].title()} {parts[0].title()}"
    return name.title()


def process_resident(
    name: str,
    case_file: Path,
    proc_file: Path,
    config: ProcessConfig,
) -> int:
    """Process one resident's files and write output Excel. Returns case count."""
    case_df = pd.read_csv(case_file)
    proc_df = pd.read_csv(proc_file)

    joined, orphans = join_case_and_procedures(case_df, proc_df)
    if not orphans.empty:
        logger.info("%s: %d orphan procedure(s) skipped", name, len(orphans))
    if joined.empty:
        return 0

    df = CsvHandler(config.columns).normalize_columns(joined)

    processor = CaseProcessor(config.columns, default_year=2025, use_ml=True)
    parsed_cases = processor.process_dataframe(df)
    if not parsed_cases:
        return 0

    output_df = processor.cases_to_dataframe(parsed_cases)
    output_path = config.output_dir / f"{format_name(name)}.xlsx"
    config.excel_handler.write_excel(
        output_df, str(output_path), fixed_widths={"Original Procedure": 12}
    )
    return len(parsed_cases)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch process resident case files")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("Output-Supervised"),
        help="Base directory containing case-list and procedure-list subdirectories "
        "(default: Output-Supervised)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("Output-Individual"),
        help="Directory to write individual Excel files (default: Output-Individual)",
    )
    args = parser.parse_args()

    base_dir: Path = args.base_dir
    output_dir: Path = args.output_dir

    case_dir = base_dir / "case-list"
    proc_dir = base_dir / "procedure-list"

    if not base_dir.exists():
        console.print(f"[red]Error:[/red] Base directory not found: {base_dir}")
        sys.exit(1)

    if not case_dir.exists() or not proc_dir.exists():
        console.print(
            f"[red]Error:[/red] Expected subdirectories not found in {base_dir}.\n"
            "  Looking for: case-list/ and procedure-list/"
        )
        sys.exit(1)

    output_dir.mkdir(exist_ok=True)

    pairs = find_resident_pairs(case_dir, proc_dir)
    if not pairs:
        console.print("[yellow]Warning:[/yellow] No matching resident file pairs found")
        sys.exit(0)

    console.print(
        f"Found [cyan]{len(pairs)}[/cyan] residents with both case and procedure files"
    )

    config = ProcessConfig(
        output_dir=output_dir,
        columns=ColumnMap(),
        excel_handler=ExcelHandler(),
    )
    total_cases = 0
    errors: list[tuple[str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing residents", total=len(pairs))

        for name, case_file, proc_file in pairs:
            try:
                count = process_resident(name, case_file, proc_file, config)
                total_cases += count
            except Exception as e:
                errors.append((name, str(e)))
            progress.advance(task)

    console.print(
        f"\n[green]Done.[/green] Processed [cyan]{len(pairs) - len(errors)}[/cyan] "
        f"residents, [cyan]{total_cases}[/cyan] total cases"
    )
    console.print(f"Output saved to: [cyan]{output_dir}/[/cyan]")

    if errors:
        console.print(f"\n[yellow]{len(errors)} errors:[/yellow]")
        for name, err in errors[:10]:
            console.print(f"  {name}: {err}")
        if len(errors) > 10:
            console.print(f"  ... and {len(errors) - 10} more")
        sys.exit(1)


if __name__ == "__main__":
    main()
