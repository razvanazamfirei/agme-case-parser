"""Command line interface for the case parser."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from pandas import DataFrame

    from .domain import ParsedCase

from .exceptions import CaseParserError
from .io import (
    CsvHandler,
    ExcelHandler,
    ExcelWriteOptions,
    discover_csv_pairs,
    read_excel,
)
from .logging_config import setup_logging
from .ml.config import DEFAULT_ML_THRESHOLD
from .models import (
    FORMAT_TYPE_CASELOG,
    FORMAT_TYPE_STANDALONE,
    OUTPUT_FORMAT_VERSION,
    STANDALONE_OUTPUT_FORMAT_VERSION,
    ColumnMap,
)
from .patterns.block_site_patterns import (
    NEURAXIAL_BLOCK_SITE_TERMS,
    PERIPHERAL_BLOCK_SITE_TERMS,
)
from .processor import CaseProcessor
from .validation import ValidationReport

logger = logging.getLogger(__name__)
console = Console()
_NEURAXIAL_STANDALONE_HINTS = (
    "EPIDURAL",
    "SPINAL",
    "CSE",
    "CAUDAL",
    "CERVICAL",
    "INTRATHECAL",
    "LUMBAR",
    "SUBARACHNOID",
    "T 1-7",
    "T 8-12",
)
_BLOCK_STANDALONE_HINTS = (
    "PERIPHERAL NERVE BLOCK",
    "NERVE BLOCK",
    "BLOCK",
)


@dataclass(frozen=True)
class _ProcessingOptions:
    """Runtime options used across processing entry points."""

    default_year: int
    sheet_name: str | int | None
    use_ml: bool
    ml_threshold: float
    workers: int


@dataclass(frozen=True)
class _StandaloneOutputSpec:
    """Metadata describing one standalone orphan output."""

    suffix: str
    label: str


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command line argument parser.

    Returns:
        Configured ArgumentParser with all supported flags and column overrides.
    """
    parser = argparse.ArgumentParser(
        description="Convert anesthesia Excel file to case log format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic conversion
  %(prog)s input.xlsx output.xlsx

  # Process all Excel files in a directory
  %(prog)s /path/to/excel/files/ combined_output.xlsx

  # With custom sheet and year
  %(prog)s input.xlsx output.xlsx --sheet "Data" --default-year 2024

  # With column overrides
  %(prog)s input.xlsx output.xlsx --col-date "Date of Service" --col-age "Patient Age"

  # With validation report
  %(prog)s input.xlsx output.xlsx --validation-report validation.txt
        """,
    )

    # Required arguments
    parser.add_argument(
        "input_file",
        help="Input Excel file path or directory containing Excel files",
    )
    parser.add_argument("output_file", help="Output Excel file path (.xlsx)")

    # Optional arguments
    parser.add_argument("--sheet", help="Sheet name to read (default: first sheet)")
    parser.add_argument(
        "--default-year",
        type=int,
        default=2025,
        help="Fallback year if a date cannot be parsed (default: 2025)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )
    parser.add_argument(
        "--validation-report",
        help="Generate validation report (text, json, or excel format)",
        metavar="FILE",
    )
    parser.add_argument(
        "--v2",
        action="store_true",
        help="Use CSV v2 format (separate CaseList and ProcedureList files). "
        "Input must be a directory containing matching CSV pairs.",
    )
    parser.add_argument(
        "--no-ml",
        action="store_true",
        help="Disable ML-assisted categorization and use rules only.",
    )
    parser.add_argument(
        "--ml-threshold",
        type=float,
        default=DEFAULT_ML_THRESHOLD,
        help=(
            "Minimum ML confidence used for hybrid categorization "
            f"(default: {DEFAULT_ML_THRESHOLD:.2f})"
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Number of worker slots for parsing "
            "(default: 1; large ML-heavy batches may use process chunks, "
            "but higher values often do not improve smaller runs)"
        ),
    )

    # Column override options
    for field_name in ColumnMap.__dataclass_fields__:
        arg_name = f"--col-{field_name.replace('_', '-')}"
        help_text = f"Override {field_name} column name"
        if field_name == "emergent":
            help_text += " (optional column)"
        parser.add_argument(arg_name, help=help_text)

    return parser


def columns_from_args(args: argparse.Namespace) -> ColumnMap:
    """Create ColumnMap from command line arguments, applying any --col-* overrides.

    Args:
        args: Parsed argument namespace containing optional col_* attributes.

    Returns:
        ColumnMap with default values overridden by any provided --col-* flags.
    """
    base = ColumnMap()
    kwargs = {}
    for field_name in ColumnMap.__dataclass_fields__:
        arg_name = f"col_{field_name}"
        if hasattr(args, arg_name) and getattr(args, arg_name) is not None:
            kwargs[field_name] = getattr(args, arg_name)
    return ColumnMap(**{**base.__dict__, **kwargs})


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate command line arguments, raising on any invalid combination.

    Args:
        args: Parsed argument namespace to validate.

    Raises:
        FileNotFoundError: If the input path does not exist.
        ValueError: If the input/output formats are unsupported, no Excel files
            are found in a directory, or the year is out of range.
    """
    input_path = Path(args.input_file)
    output_path = Path(args.output_file)

    if not input_path.exists():
        raise FileNotFoundError(f"Input path not found: {input_path}")

    if args.v2:
        if not input_path.is_dir():
            raise ValueError(
                "--v2 requires input to be a directory containing "
                "CaseList and ProcedureList CSV files"
            )
        try:
            discover_csv_pairs(input_path)
        except ValueError as e:
            raise ValueError(f"CSV v2 validation failed: {e}") from e
    elif input_path.is_file() and input_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(f"Unsupported input file format: {input_path.suffix}")
    elif input_path.is_dir():
        excel_files = list(input_path.glob("*.xlsx")) + list(input_path.glob("*.xls"))
        if not excel_files:
            raise ValueError(f"No Excel files found in directory: {input_path}")

    if output_path.suffix.lower() != ".xlsx":
        raise ValueError("Output file must have .xlsx extension")

    if args.default_year < 1900 or args.default_year > 2100:
        raise ValueError("Default year must be between 1900 and 2100")
    if not 0.0 <= args.ml_threshold <= 1.0:
        raise ValueError("ML threshold must be between 0.0 and 1.0")
    if args.workers < 1:
        raise ValueError("workers must be at least 1")


def find_excel_files(directory: Path) -> list[Path]:
    """Return all .xlsx and .xls files in directory, sorted by name.

    Args:
        directory: Directory to search for Excel files.

    Returns:
        Sorted list of matching file paths sorted alphabetically (.xlsx before .xls).
    """
    return sorted(directory.glob("*.xlsx")) + sorted(directory.glob("*.xls"))


def process_single_excel_file(
    file_path: Path,
    processor: CaseProcessor,
    options: _ProcessingOptions,
) -> list[ParsedCase]:
    """Read and process a single Excel file.

    Args:
        file_path: Path to the Excel file to process.
        processor: Initialized CaseProcessor to use for parsing.
        options: Shared runtime options, including sheet selection and worker
            count.

    Returns:
        List of ParsedCase objects. Empty if the file contains no data rows.
    """
    console.print(f"[cyan]Processing:[/cyan] {file_path.name}")

    df = read_excel(str(file_path), sheet_name=options.sheet_name or 0)

    if df.empty:
        console.print(
            f"[yellow]  Warning:[/yellow] {file_path.name} is empty, skipping"
        )
        return []

    cases = processor.process_dataframe(df, workers=options.workers)
    console.print(
        f"[green]  OK[/green] Parsed {len(cases)} cases from {file_path.name}"
    )
    return cases


def process_excel_directory(
    directory: Path,
    processor: CaseProcessor,
    options: _ProcessingOptions,
) -> list[ParsedCase]:
    """Process all Excel files in a directory.

    Args:
        directory: Directory containing Excel files to process.
        processor: Initialized CaseProcessor to use for parsing.
        options: Shared runtime options applied to every file in the directory.

    Returns:
        Combined list of ParsedCase objects from all files in the directory.
    """
    excel_files = find_excel_files(directory)
    console.print(
        f"\n[bold cyan]Found {len(excel_files)} Excel file(s) "
        f"in directory[/bold cyan]\n"
    )

    all_cases: list[ParsedCase] = []
    for excel_file in excel_files:
        all_cases.extend(
            process_single_excel_file(
                excel_file,
                processor,
                options,
            )
        )

    console.print(
        f"\n[bold green]Processed {len(excel_files)} files, "
        f"total {len(all_cases)} cases[/bold green]\n"
    )
    return all_cases


def _build_processor(columns: ColumnMap, options: _ProcessingOptions) -> CaseProcessor:
    """Create a processor instance from shared runtime options."""
    return CaseProcessor(
        columns,
        options.default_year,
        use_ml=options.use_ml,
        ml_threshold=options.ml_threshold,
    )


def process_excel(
    input_path: Path,
    columns: ColumnMap,
    options: _ProcessingOptions,
) -> tuple[list[ParsedCase], DataFrame]:
    """Dispatch Excel processing for a single file or a directory.

    Args:
        input_path: Path to an Excel file or directory of Excel files.
        columns: Column mapping configuration.
        options: Shared runtime options, including default year, optional sheet
            selection, ML usage, and worker count.

    Returns:
        Tuple of (cases, output_df) where cases is the list of ParsedCase objects
        and output_df is the corresponding output-formatted DataFrame.
    """
    processor = _build_processor(columns, options)

    if input_path.is_file():
        cases = process_single_excel_file(input_path, processor, options)
    else:
        cases = process_excel_directory(input_path, processor, options)

    output_df = CaseProcessor.cases_to_dataframe(cases)
    return cases, output_df


def process_csv(
    input_path: Path,
    output_path: Path,
    columns: ColumnMap,
    excel_handler: ExcelHandler,
    options: _ProcessingOptions,
) -> tuple[list[ParsedCase], DataFrame, int]:
    """Process a CSV v2 directory (MPOG supervised export).

    Reads matched CaseList/ProcedureList CSV pairs, processes all cases, and
    writes separate standalone files for orphan blocks and neuraxial
    procedures derived from unmatched ProcedureList rows.

    Args:
        input_path: Directory containing CSV v2 file pairs.
        output_path: Desired path for the primary output Excel file (used to
            derive standalone orphan output filenames).
        columns: Column mapping configuration.
        excel_handler: ExcelHandler instance used to write standalone output.
        options: Shared runtime options, including default year, ML usage, and
            worker count.

    Returns:
        Tuple of (cases, output_df, standalone_case_count) for the main
        matched cases plus the number of standalone orphan procedures written
        to separate outputs.
    """
    console.print(
        Panel(
            f"[cyan]Processing CSV v2 format from:[/cyan] {input_path}\n"
            f"[cyan]Output file:[/cyan] {output_path}",
            title="CSV v2 Mode",
            border_style="cyan",
        )
    )

    df, orphan_df = CsvHandler(columns).read(input_path)
    processor = _build_processor(columns, options)
    all_cases = processor.process_dataframe(df, workers=options.workers)
    output_df = processor.cases_to_dataframe(all_cases)

    standalone_case_count = 0
    if not orphan_df.empty:
        orphan_cases = processor.process_dataframe(orphan_df, workers=options.workers)
        block_cases, neuraxial_cases = split_standalone_cases(orphan_cases)
        standalone_case_count = len(block_cases) + len(neuraxial_cases)

        _write_standalone_output(
            processor=processor,
            excel_handler=excel_handler,
            output_path=output_path,
            cases=block_cases,
            spec=_StandaloneOutputSpec(
                suffix="standalone_blocks",
                label="Standalone blocks",
            ),
        )
        _write_standalone_output(
            processor=processor,
            excel_handler=excel_handler,
            output_path=output_path,
            cases=neuraxial_cases,
            spec=_StandaloneOutputSpec(
                suffix="standalone_neuraxial",
                label="Standalone neuraxial",
            ),
        )

    return all_cases, output_df, standalone_case_count


def _write_standalone_output(
    *,
    processor: CaseProcessor,
    excel_handler: ExcelHandler,
    output_path: Path,
    cases: list[ParsedCase],
    spec: _StandaloneOutputSpec,
) -> None:
    """Write one standalone orphan-procedure workbook when rows are present."""
    if not cases:
        return

    standalone_output = processor.procedures_to_dataframe(cases)
    standalone_path = output_path.with_stem(f"{output_path.stem}_{spec.suffix}")
    excel_handler.write_excel(
        standalone_output,
        standalone_path,
        options=ExcelWriteOptions(
            format_type=FORMAT_TYPE_STANDALONE,
            version=STANDALONE_OUTPUT_FORMAT_VERSION,
        ),
    )
    console.print(
        f"[cyan]{spec.label}:[/cyan] {standalone_path} ({len(cases)} procedure(s))"
    )


def _standalone_case_search_text(case: ParsedCase) -> str:
    """Build a single uppercase search string for standalone-case routing."""
    return " ".join(
        value
        for value in (
            case.raw_anesthesia_type,
            case.raw_nerve_block_type,
            case.unmatched_block_source,
            case.procedure,
            case.procedure_notes,
            case.nerve_block_type,
        )
        if value
    ).upper()


def is_neuraxial_standalone_case(case: ParsedCase) -> bool:
    """Return True when standalone procedure text indicates neuraxial technique."""
    search_text = _standalone_case_search_text(case)
    return any(hint in search_text for hint in _NEURAXIAL_STANDALONE_HINTS)


def is_block_standalone_case(case: ParsedCase) -> bool:
    """Return True when standalone procedure text indicates a block technique."""
    search_text = _standalone_case_search_text(case)
    return any(hint in search_text for hint in _BLOCK_STANDALONE_HINTS)


def _normalized_block_terms(case: ParsedCase) -> set[str]:
    """Split normalized standalone block-site text into canonical terms."""
    if not case.nerve_block_type:
        return set()
    return {
        term.strip()
        for term in case.nerve_block_type.split(";")
        if term and term.strip()
    }


def _has_normalized_peripheral_block(case: ParsedCase) -> bool:
    """Return True when normalized standalone block text is peripheral."""
    return bool(_normalized_block_terms(case) & set(PERIPHERAL_BLOCK_SITE_TERMS))


def _has_normalized_neuraxial_block(case: ParsedCase) -> bool:
    """Return True when normalized standalone block text is neuraxial."""
    return bool(_normalized_block_terms(case) & set(NEURAXIAL_BLOCK_SITE_TERMS))


def split_standalone_cases(
    cases: list[ParsedCase],
) -> tuple[list[ParsedCase], list[ParsedCase]]:
    """Split standalone orphan procedures into block and neuraxial buckets.

    Cases with explicit neuraxial hints route to the neuraxial output. Cases
    with block hints or a normalized block site route to the block output.
    Remaining unmatched procedures intentionally fall back to the neuraxial
    bucket.
    """
    block_cases: list[ParsedCase] = []
    neuraxial_cases: list[ParsedCase] = []

    for case in cases:
        if _has_normalized_peripheral_block(case) or is_block_standalone_case(case):
            block_cases.append(case)
            continue
        if _has_normalized_neuraxial_block(case) or is_neuraxial_standalone_case(case):
            neuraxial_cases.append(case)
            continue
        # Intentional fallback for unmatched procedures; see
        # test_split_standalone_cases_defaults_unknown_to_neuraxial_bucket.
        neuraxial_cases.append(case)

    return block_cases, neuraxial_cases


def save_validation_report(cases: list[ParsedCase], report_path: Path) -> None:
    """Generate and save a validation report, then print its summary.

    The output format is inferred from the file extension: .json produces a JSON
    report, .xlsx/.xls produces an Excel report, and anything else produces a
    plain-text report.

    Args:
        cases: List of parsed cases to validate.
        report_path: File path where the report will be written.
    """
    suffix = report_path.suffix.lower()
    if suffix == ".json":
        format_type = "json"
    elif suffix in {".xlsx", ".xls"}:
        format_type = "excel"
    else:
        format_type = "text"

    report = ValidationReport(cases)
    report.save_report(report_path, output_format=format_type)

    console.print(f"\n[green]Validation report saved to:[/green] {report_path}")
    console.print(Panel("[bold]Validation Summary[/bold]", border_style="cyan"))
    print_validation_summary(report.get_summary())


def print_validation_summary(summary: dict[str, Any]) -> None:
    """Print a validation summary as a rich table.

    Args:
        summary: Summary dict as returned by ValidationReport.get_summary().
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(style="white")

    table.add_row("Total Cases:", str(summary["total_cases"]))
    table.add_row(
        "Cases with Warnings:",
        f"[yellow]{summary['cases_with_warnings']}[/yellow]"
        if summary["cases_with_warnings"] > 0
        else str(summary["cases_with_warnings"]),
    )
    table.add_row(
        "Low Confidence Cases:",
        f"[red]{summary['low_confidence_cases']}[/red]"
        if summary["low_confidence_cases"] > 0
        else str(summary["low_confidence_cases"]),
    )
    table.add_row("Average Confidence:", f"{summary['average_confidence']:.3f}")
    console.print(table)


def get_output_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Return aggregate stats for the output DataFrame for terminal display.

    Args:
        df: Output DataFrame produced by CaseProcessor.cases_to_dataframe().

    Returns:
        Dict with keys: total_cases, date_range, columns, empty_cases,
        missing_dates. Falls back to a minimal dict on any error.
    """
    try:
        dates = pd.to_datetime(df["Case Date"], format="%m/%d/%Y", errors="coerce")
        date_range = "Unavailable"
        if dates.notna().any():
            min_date = dates.min().strftime("%m/%d/%Y")
            max_date = dates.max().strftime("%m/%d/%Y")
            date_range = f"{min_date} to {max_date}"

        return {
            "total_cases": len(df),
            "date_range": date_range,
            "columns": list(df.columns),
            "empty_cases": (
                df["Case ID"].fillna("").astype(str).str.strip().eq("").sum()
            ),
            "missing_dates": df["Case Date"].isna().sum(),
        }
    except Exception as e:
        logger.warning("Could not generate output summary: %s", e)
        return {"total_cases": len(df), "date_range": "Unavailable"}


def print_summary(output_file: Path, summary: dict[str, Any]) -> None:
    """Print the final output summary panel.

    Args:
        output_file: Path to the written output file (displayed in the panel).
        summary: Summary dict as returned by get_output_summary().
    """
    console.print()
    console.print(Panel("[bold]Output Summary[/bold]", border_style="green"))

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(style="white")
    table.add_row("Cases:", str(summary["total_cases"]))
    table.add_row("Date range:", summary["date_range"])
    console.print(table)

    empty_cases = summary.get("empty_cases", 0)
    if empty_cases > 0:
        console.print(
            f"  [yellow]Warning:[/yellow] {empty_cases} cases have empty Case IDs"
        )

    console.print()
    console.print(f"[green]Output saved to:[/green] {output_file}")
    console.print("[bold green]Done.[/bold green]")


def main() -> None:
    """Main entry point for the case-parser CLI.

    Parses arguments, validates inputs, dispatches to the appropriate processing
    path (Excel workbook input or CSV v2 directory input), optionally writes a
    validation report, writes the primary output workbook, and prints a
    summary. In CSV v2 mode, standalone orphan procedures may also be written
    to separate block and neuraxial workbooks. Exits with a non-zero status
    code on any error.
    """
    parser = build_arg_parser()
    args = parser.parse_args()
    setup_logging(level=args.log_level, verbose=args.verbose)

    try:
        validate_arguments(args)
        columns = columns_from_args(args)
        input_path = Path(args.input_file)
        output_path = Path(args.output_file)
        excel_handler = ExcelHandler()
        options = _ProcessingOptions(
            default_year=args.default_year,
            sheet_name=args.sheet,
            use_ml=not args.no_ml,
            ml_threshold=args.ml_threshold,
            workers=args.workers,
        )

        standalone_case_count = 0
        if args.v2:
            all_cases, output_df, standalone_case_count = process_csv(
                input_path,
                output_path,
                columns,
                excel_handler,
                options,
            )
        else:
            all_cases, output_df = process_excel(
                input_path,
                columns,
                options,
            )

        if not all_cases:
            if standalone_case_count:
                console.print(
                    "[yellow]Warning:[/yellow] "
                    "No main cases to process; standalone orphan outputs were "
                    f"written for {standalone_case_count} procedure(s)"
                )
            else:
                console.print("[yellow]Warning:[/yellow] No cases to process")
            return

        if args.validation_report:
            save_validation_report(all_cases, Path(args.validation_report))

        excel_handler.write_excel(
            output_df,
            output_path,
            options=ExcelWriteOptions(
                fixed_widths={"Original Procedure": 12},
                format_type=FORMAT_TYPE_CASELOG,
                version=OUTPUT_FORMAT_VERSION,
            ),
        )
        print_summary(output_path, get_output_summary(output_df))

    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except PermissionError as e:
        console.print(f"[red]Permission error:[/red] {e}")
        sys.exit(1)
    except CaseParserError as e:
        console.print(f"[red]Processing error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
