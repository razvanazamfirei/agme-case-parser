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
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class ProcessConfig:
    output_dir: Path
    columns: ColumnMap
    excel_handler: ExcelHandler
    workers: int = field(default=os.cpu_count() or 1)


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
    processor: CaseProcessor,
    orphan_notices: list[tuple[str, int, str]],
    orphan_notices_lock: threading.Lock,
) -> int:
    """Process one resident's files and write output Excel.

    Args:
        pairs: Tuple of (name, case_file, proc_file) where name is the resident
            identifier (``LAST_FIRST`` format), case_file is the path to the
            CaseList CSV, and proc_file is the path to the ProcedureList CSV.
        config: Shared processing configuration (output dir, column map, handlers).
        processor: Configured ``CaseProcessor`` instance for transforming rows.
        orphan_notices: Shared list to which orphan-file notices are appended.
        orphan_notices_lock: Lock protecting concurrent access to orphan_notices.

    Returns:
        Number of cases written to the output Excel file, or 0 if there were
        no joined cases to process.
    """
    name: str
    case_file: Path
    proc_file: Path
    name, case_file, proc_file = pairs
    case_df = pd.read_csv(case_file)
    proc_df = pd.read_csv(proc_file)

    joined, orphans = join_case_and_procedures(case_df, proc_df)
    formatted_name = format_name(name)

    if not orphans.empty:
        standalone_path = config.output_dir / f"{formatted_name}_standalone.xlsx"
        config.excel_handler.write_excel(orphans, str(standalone_path))
        with orphan_notices_lock:
            orphan_notices.append((name, len(orphans), standalone_path.name))

    if joined.empty:
        return 0

    df = CsvHandler(config.columns).normalize_columns(joined)

    # Avoid nested thread pools: when processing multiple residents in parallel
    # (config.workers > 1), keep row-level processing single-threaded. When
    # processing residents sequentially, allow row-level parallelism up to CPU count.
    if config.workers and config.workers > 1:
        row_workers = 1
    else:
        row_workers = os.cpu_count() or 1

    parsed_cases = processor.process_dataframe(df, row_workers)
    if not parsed_cases:
        return 0

    output_df = processor.cases_to_dataframe(parsed_cases)
    output_path = config.output_dir / f"{formatted_name}.xlsx"
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
        workers=args.workers,
    )
    processor = CaseProcessor(config.columns, default_year=2025, use_ml=True)
    total_cases = 0
    errors: list[tuple[str, str]] = []
    orphan_notices: list[tuple[str, int, str]] = []
    orphan_notices_lock = threading.Lock()
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

        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            futures = {
                executor.submit(
                    process_resident,
                    pair,
                    config,
                    processor,
                    orphan_notices,
                    orphan_notices_lock,
                ): pair[0]
                for pair in pairs
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    total_cases += future.result()
                except Exception as e:
                    errors.append((name, str(e)))
                progress.advance(task)

    for name, orphan_count, standalone_name in orphan_notices:
        console.print(
            f"  [yellow]Note:[/yellow] {name}: {orphan_count} orphan procedure(s) "
            f"→ {standalone_name}"
        )

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
