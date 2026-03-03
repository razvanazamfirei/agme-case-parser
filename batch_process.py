#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas>=3.0.1",
#   "rich>=14.3.3",
#   "case-parser",
# ]
# ///
"""Batch process all residents from Output-Supervised into individual Excel files."""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
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
from src.case_parser.models import (
    FORMAT_TYPE_CASELOG,
    FORMAT_TYPE_STANDALONE,
    OUTPUT_FORMAT_VERSION,
    STANDALONE_OUTPUT_FORMAT_VERSION,
    ColumnMap,
)
from src.case_parser.processor import CaseProcessor

# Suppress noisy logging from the pipeline
logging.getLogger("case_parser").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
console = Console()


@dataclass(frozen=True)
class ProcessConfig:
    output_dir: Path
    columns: ColumnMap
    excel_handler: ExcelHandler


def find_resident_pairs(case_dir: Path, proc_dir: Path) -> list[tuple[str, Path, Path]]:
    """Find matching case/procedure file pairs.

    Args:
        case_dir: Directory containing ``*.CaseList.csv`` files.
        proc_dir: Directory containing ``*.ProcedureList.csv`` files.

    Returns:
        Sorted list of ``(name, case_path, proc_path)`` tuples for residents
        that have both a CaseList and a ProcedureList file.
    """
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
    """Convert ``LAST_FIRST`` filename stem to ``First Last`` display name.

    Args:
        name: Filename stem in ``LAST_FIRST`` format (underscore-separated).

    Returns:
        Title-cased ``First Last`` string, or the original name title-cased
        if no underscore separator is found.
    """
    parts = name.split("_", 1)
    if len(parts) == 2:
        return f"{parts[1].title()} {parts[0].title()}"
    return name.title()


def process_resident(
    pairs: tuple[str, Path, Path],
    config: ProcessConfig,
) -> tuple[int, tuple[str, int, str] | None]:
    """Process one resident's files and write output Excel.

    Creates its own ``CaseProcessor`` so this function is safe to run in a
    worker process (no shared ML-model state between workers).

    Args:
        pairs: Tuple of (name, case_file, proc_file) where name is the resident
            identifier (``LAST_FIRST`` format), case_file is the path to the
            CaseList CSV, and proc_file is the path to the ProcedureList CSV.
        config: Shared processing configuration (output dir, column map, handlers).

    Returns:
        Tuple of (cases_written, orphan_notice) where orphan_notice is
        ``(name, count, filename)`` when orphan procedures were found, else None.
    """
    name, case_file, proc_file = pairs
    processor = CaseProcessor(config.columns, default_year=2025, use_ml=True)
    formatted_name = format_name(name)
    joined, orphans = join_case_and_procedures(
        pd.read_csv(case_file),
        pd.read_csv(proc_file),
    )

    orphan_notice: tuple[str, int, str] | None = None
    if not orphans.empty:
        orphan_cases = processor.process_dataframe(
            CsvHandler(config.columns).normalize_orphan_columns(orphans)
        )
        config.excel_handler.write_excel(
            processor.procedures_to_dataframe(orphan_cases),
            str(config.output_dir / f"{formatted_name}_standalone.xlsx"),
            format_type=FORMAT_TYPE_STANDALONE,
            version=STANDALONE_OUTPUT_FORMAT_VERSION,
        )
        orphan_notice = (name, len(orphans), f"{formatted_name}_standalone.xlsx")

    if joined.empty:
        return 0, orphan_notice

    parsed_cases = processor.process_dataframe(
        CsvHandler(config.columns).normalize_columns(joined),
        workers=1,
    )
    if not parsed_cases:
        return 0, orphan_notice

    config.excel_handler.write_excel(
        processor.cases_to_dataframe(parsed_cases),
        str(config.output_dir / f"{formatted_name}.xlsx"),
        fixed_widths={"Original Procedure": 12},
        format_type=FORMAT_TYPE_CASELOG,
        version=OUTPUT_FORMAT_VERSION,
    )
    return len(parsed_cases), orphan_notice


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
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers for resident processing (default: 4)",
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
    orphan_notices: list[tuple[str, int, str]] = []

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

        # Parallel: each worker process gets its own Python interpreter and GIL,
        # providing true CPU parallelism that threads cannot achieve.
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_resident, pair, config): pair[0]
                for pair in pairs
            }
            for future in as_completed(futures):
                resident_id = futures[future]
                try:
                    cases_written, orphan_notice = future.result()
                    total_cases += cases_written
                    if orphan_notice is not None:
                        orphan_notices.append(orphan_notice)
                except Exception as e:
                    logger.exception(
                        "Failed processing resident %s: %s", resident_id, e
                    )
                    errors.append((resident_id, str(e)))
                progress.advance(task)

    for resident_id, orphan_count, standalone_name in orphan_notices:
        console.print(
            f"  [yellow]Note:[/yellow] {resident_id}: {orphan_count} orphan "
            f"procedure(s) → {standalone_name}"
        )

    console.print(
        f"\n[green]Done.[/green] Processed [cyan]{len(pairs) - len(errors)}[/cyan] "
        f"residents, [cyan]{total_cases}[/cyan] total cases\n",
        f"Output saved to: [cyan]{output_dir}/[/cyan]",
    )

    if errors:
        console.print(f"\n[yellow]{len(errors)} errors:[/yellow]")
        for name, err in errors[:10]:
            console.print(f"  {name}: {err}")
        if len(errors) > 10:
            console.print(f"  ... and {len(errors) - 10} more")
        sys.exit(1)


if __name__ == "__main__":
    main()
