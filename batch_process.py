#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pandas>=3.0.1",
#   "rich>=14.3.3",
#   "case-parser",
# ]
# ///
"""Batch process all residents from Output-Supervised into individual Excel files."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
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
    ExcelWriteOptions,
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

_WORKER_PROCESSORS: dict[tuple[int, bool, ColumnMap], CaseProcessor] = {}
_SKLEARN_DELAYED_WARNING_PATTERN = r".*sklearn\.utils\.parallel\.delayed.*"


@dataclass(frozen=True)
class ProcessConfig:
    output_dir: Path
    columns: ColumnMap
    excel_handler: ExcelHandler
    use_ml: bool


def _suppress_sklearn_parallel_warning() -> None:
    """Suppress noisy sklearn delayed/Parallel warning during batch runs."""
    warnings.filterwarnings(
        "ignore",
        message=_SKLEARN_DELAYED_WARNING_PATTERN,
        category=UserWarning,
    )


def _get_worker_processor(columns: ColumnMap, use_ml: bool) -> CaseProcessor:
    """
    Return a cached CaseProcessor instance scoped to the current OS process, the `use_ml` setting, and the provided `columns`.
    
    Parameters:
        columns (ColumnMap): Column mappings used to construct or identify the processor.
        use_ml (bool): If `True`, returns a processor configured for ML-enhanced categorization.
    
    Returns:
        CaseProcessor: A CaseProcessor instance reused for the current process and settings.
    """
    cache_key = (os.getpid(), use_ml, columns)
    cached = _WORKER_PROCESSORS.get(cache_key)
    if cached is None:
        cached = CaseProcessor(columns, default_year=2025, use_ml=use_ml)
        _WORKER_PROCESSORS[cache_key] = cached
    return cached


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
    """
    Process a single resident's CaseList and ProcedureList and write per-resident Excel outputs.
    
    If procedures have no matching cases, writes a standalone procedures workbook named "<FormattedName>_standalone.xlsx". If any cases are produced, writes a case log workbook named "<FormattedName>.xlsx".
    
    Parameters:
        pairs (tuple[str, Path, Path]): (resident_stem, case_file, proc_file) where resident_stem is the file stem in LAST_FIRST format, case_file is the CaseList CSV path, and proc_file is the ProcedureList CSV path.
        config (ProcessConfig): Processing configuration including output directory, column mapping, and Excel handler.
    
    Returns:
        tuple[int, tuple[str, int, str] | None]: (cases_written, orphan_notice) where `orphan_notice` is `(resident_stem, orphan_count, filename)` if orphan procedures were written, otherwise `None`.
    """
    name, case_file, proc_file = pairs
    _suppress_sklearn_parallel_warning()
    processor = _get_worker_processor(config.columns, config.use_ml)
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
            config.output_dir / f"{formatted_name}_standalone.xlsx",
            options=ExcelWriteOptions(
                format_type=FORMAT_TYPE_STANDALONE,
                version=STANDALONE_OUTPUT_FORMAT_VERSION,
            ),
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
        config.output_dir / f"{formatted_name}.xlsx",
        options=ExcelWriteOptions(
            fixed_widths={"Original Procedure": 12},
            format_type=FORMAT_TYPE_CASELOG,
            version=OUTPUT_FORMAT_VERSION,
        ),
    )
    return len(parsed_cases), orphan_notice


def _parse_args() -> argparse.Namespace:
    """
    Parse and validate command-line options for batch resident processing.
    
    This function parses the following options and returns the resulting namespace:
    - --base-dir: Path to the input directory containing "case-list" and "procedure-list" subdirectories (default: Output-Supervised).
    - --output-dir: Path where individual Excel files will be written (default: Output-Individual).
    - --workers: Number of parallel workers to use; must be at least 1 (default: 4).
    - --use-ml / --no-ml: Enable or disable ML-enhanced procedure categorization (default: enabled).
    
    Returns:
        argparse.Namespace: Parsed arguments with attributes:
            base_dir (Path), output_dir (Path), workers (int), use_ml (bool).
    """
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
    parser.set_defaults(use_ml=True)
    parser.add_argument(
        "--use-ml",
        dest="use_ml",
        action="store_true",
        help="Enable ML-enhanced procedure categorization (default)",
    )
    parser.add_argument(
        "--no-ml",
        dest="use_ml",
        action="store_false",
        help="Disable ML-enhanced procedure categorization and use rules only",
    )
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    return args


def _validate_input_dirs(base_dir: Path) -> tuple[Path, Path]:
    """Validate expected input folder structure and return subdirectories."""
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

    return case_dir, proc_dir


def _sanitize_resident_id(resident_id: str) -> str:
    """Return a non-sensitive resident identifier for logs and error output."""
    return hashlib.sha256(resident_id.encode("utf-8")).hexdigest()[:8]


def _process_in_parallel(
    pairs: list[tuple[str, Path, Path]],
    config: ProcessConfig,
    workers: int,
) -> tuple[int, list[tuple[str, str]], list[tuple[str, int, str]]]:
    """
    Process multiple resident case/procedure file pairs in parallel using an executor chosen by the processing mode.
    
    Parameters:
        pairs (list[tuple[str, Path, Path]]): List of tuples (resident_name, case_file_path, procedure_file_path) to process.
        config (ProcessConfig): Processing configuration; `config.use_ml` selects a process-based executor when true and a thread-based executor when false.
        workers (int): Maximum number of concurrent worker threads or processes.
    
    Returns:
        total_cases (int): Total number of case rows written across all processed residents.
        errors (list[tuple[str, str]]): List of (sanitized_resident_id, error_code) for residents that failed processing.
        orphan_notices (list[tuple[str, int, str]]): List of (resident_name, orphan_count, orphan_filename) for residents that produced standalone orphan outputs.
    """
    total_cases = 0
    errors: list[tuple[str, str]] = []
    orphan_notices: list[tuple[str, int, str]] = []
    executor_cls = ProcessPoolExecutor if config.use_ml else ThreadPoolExecutor

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

        with executor_cls(max_workers=workers) as executor:
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
                except Exception:
                    sanitized_id = _sanitize_resident_id(resident_id)
                    logger.error("Failed processing resident %s", sanitized_id)
                    errors.append((sanitized_id, "processing_failed"))
                progress.advance(task)
    return total_cases, errors, orphan_notices


def main() -> None:
    """
    Orchestrates batch processing of resident case and procedure CSV files and writes per-resident Excel outputs.
    
    Validates input directories, creates the output directory, discovers matching resident file pairs, and processes each pair (potentially in parallel) according to the configured processing options. Prints per-resident orphan-procedure notices and a final summary to the console. Exits with status 0 when no matching pairs are found and with status 1 if any resident processing errors occur.
    """
    _suppress_sklearn_parallel_warning()
    args = _parse_args()
    output_dir: Path = args.output_dir
    case_dir, proc_dir = _validate_input_dirs(args.base_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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
        use_ml=args.use_ml,
    )
    total_cases, errors, orphan_notices = _process_in_parallel(
        pairs, config, args.workers
    )

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
