"""Command line interface for the case parser."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
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
from .io import CsvHandler, ExcelHandler, discover_csv_pairs, read_excel
from .logging_config import setup_logging
from .models import ColumnMap
from .processor import CaseProcessor
from .validation import ValidationReport

logger = logging.getLogger(__name__)
console = Console()


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
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

    # Column override options
    for field_name in ColumnMap.__dataclass_fields__:
        arg_name = f"--col-{field_name.replace('_', '-')}"
        help_text = f"Override {field_name} column name"
        if field_name == "emergent":
            help_text += " (optional column)"
        parser.add_argument(arg_name, help=help_text)

    return parser


def columns_from_args(args: argparse.Namespace) -> ColumnMap:
    """Create ColumnMap from command line arguments, applying any --col-* overrides."""
    base = ColumnMap()
    kwargs = {}
    for field_name in ColumnMap.__dataclass_fields__:
        arg_name = f"col_{field_name}"
        if hasattr(args, arg_name) and getattr(args, arg_name) is not None:
            kwargs[field_name] = getattr(args, arg_name)
    return ColumnMap(**{**base.__dict__, **kwargs})


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate command line arguments, raising on any invalid combination."""
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


def find_excel_files(directory: Path) -> list[Path]:
    """Return all .xlsx and .xls files in directory, sorted by name."""
    return sorted(directory.glob("*.xlsx")) + sorted(directory.glob("*.xls"))


def process_single_excel_file(
    file_path: Path,
    processor: CaseProcessor,
    sheet_name: str | int | None,
) -> list[ParsedCase]:
    """Read and process a single Excel file.

    Returns an empty list if the file is empty.
    """
    console.print(f"[cyan]Processing:[/cyan] {file_path.name}")

    df = read_excel(str(file_path), sheet_name=sheet_name or 0)

    if df.empty:
        console.print(
            f"[yellow]  Warning:[/yellow] {file_path.name} is empty, skipping"
        )
        return []

    cases = processor.process_dataframe(df)
    console.print(
        f"[green]  OK[/green] Parsed {len(cases)} cases from {file_path.name}"
    )
    return cases


def process_excel_directory(
    directory: Path,
    processor: CaseProcessor,
    sheet_name: str | int | None,
) -> list[ParsedCase]:
    """Process all Excel files in a directory."""
    excel_files = find_excel_files(directory)
    console.print(
        f"\n[bold cyan]Found {len(excel_files)} Excel file(s) "
        f"in directory[/bold cyan]\n"
    )

    all_cases: list[ParsedCase] = []
    for excel_file in excel_files:
        all_cases.extend(process_single_excel_file(excel_file, processor, sheet_name))

    console.print(
        f"\n[bold green]Processed {len(excel_files)} files, "
        f"total {len(all_cases)} cases[/bold green]\n"
    )
    return all_cases


def process_excel(
    input_path: Path,
    columns: ColumnMap,
    default_year: int,
    sheet_name: str | int | None,
) -> tuple[list[ParsedCase], DataFrame]:
    """Dispatch Excel processing for a single file or a directory."""
    processor = CaseProcessor(columns, default_year)

    if input_path.is_file():
        cases = process_single_excel_file(input_path, processor, sheet_name)
    else:
        cases = process_excel_directory(input_path, processor, sheet_name)

    output_df = CaseProcessor.cases_to_dataframe(cases)
    return cases, output_df


def process_csv(
    input_path: Path,
    output_path: Path,
    columns: ColumnMap,
    default_year: int,
    excel_handler: ExcelHandler,
) -> tuple[list[ParsedCase], DataFrame]:
    """Process a CSV v2 directory (MPOG supervised export).

    Returns (cases, output_df).
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
    processor = CaseProcessor(columns, default_year)
    all_cases = processor.process_dataframe(df)
    output_df = processor.cases_to_dataframe(all_cases)

    if not orphan_df.empty:
        orphan_cases = processor.process_dataframe(orphan_df)
        orphan_output_df = processor.cases_to_dataframe(orphan_cases)
        standalone_path = output_path.with_stem(output_path.stem + "_standalone")
        excel_handler.write_excel(
            orphan_output_df,
            str(standalone_path),
            fixed_widths={"Original Procedure": 12},
        )
        console.print(
            f"[cyan]Standalone procedures:[/cyan] {standalone_path} "
            f"({len(orphan_cases)} procedure(s))"
        )

    return all_cases, output_df


def save_validation_report(cases: list[ParsedCase], report_path: Path) -> None:
    """Generate and save a validation report, then print its summary."""
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
    """Print a validation summary as a rich table."""
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
    """Return aggregate stats for the output DataFrame for terminal display."""
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
    """Print the final output summary panel."""
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
    """Main entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()
    setup_logging(level=args.log_level, verbose=args.verbose)

    try:
        validate_arguments(args)
        columns = columns_from_args(args)
        input_path = Path(args.input_file)
        output_path = Path(args.output_file)
        excel_handler = ExcelHandler()

        if args.v2:
            all_cases, output_df = process_csv(
                input_path,
                output_path,
                columns,
                args.default_year,
                excel_handler,
            )
        else:
            all_cases, output_df = process_excel(
                input_path,
                columns,
                args.default_year,
                args.sheet,
            )

        if not all_cases:
            console.print("[yellow]Warning:[/yellow] No cases to process")
            return

        if args.validation_report:
            save_validation_report(all_cases, Path(args.validation_report))

        excel_handler.write_excel(
            output_df, str(output_path), fixed_widths={"Original Procedure": 12}
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
