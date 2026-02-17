"""Command line interface for the case parser."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .exceptions import CaseParserError
from .io import ExcelHandler, read_excel
from .logging_config import setup_logging
from .models import ColumnMap
from .processor import CaseProcessor
from .validation import ValidationReport

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

  # Process directory with source file tracking
  %(prog)s /path/to/excel/files/ combined_output.xlsx --add-source-column

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
        "--add-source-column",
        action="store_true",
        help="Add a 'Source File' column to track which file each case came from (useful with directory input)",
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
    """Create ColumnMap from command line arguments."""
    base = ColumnMap()

    # Build kwargs for ColumnMap constructor
    kwargs = {}
    for field_name in ColumnMap.__dataclass_fields__:
        arg_name = f"col_{field_name}"
        if hasattr(args, arg_name) and getattr(args, arg_name) is not None:
            kwargs[field_name] = getattr(args, arg_name)

    # Create new ColumnMap with overrides
    return ColumnMap(**{**base.__dict__, **kwargs})


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate command line arguments."""
    input_path = Path(args.input_file)
    output_path = Path(args.output_file)

    if not input_path.exists():
        raise FileNotFoundError(f"Input path not found: {input_path}")

    # V2 format requires directory input
    if hasattr(args, "v2") and args.v2:
        if not input_path.is_dir():
            raise ValueError(
                "--v2 requires input to be a directory containing "
                "CaseList and ProcedureList CSV files"
            )

        # Import here to avoid circular dependency
        from .csv_io import discover_csv_pairs

        try:
            discover_csv_pairs(input_path)
        except ValueError as e:
            raise ValueError(f"CSV v2 validation failed: {e}") from e

    # If it's a file (non-v2), check the extension
    elif input_path.is_file() and input_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(f"Unsupported input file format: {input_path.suffix}")

    # If it's a directory (non-v2), check that it contains Excel files
    elif input_path.is_dir():
        excel_files = list(input_path.glob("*.xlsx")) + list(input_path.glob("*.xls"))
        if not excel_files:
            raise ValueError(f"No Excel files found in directory: {input_path}")

    if not output_path.suffix.lower() == ".xlsx":
        raise ValueError("Output file must have .xlsx extension")

    if args.default_year < 1900 or args.default_year > 2100:
        raise ValueError("Default year must be between 1900 and 2100")


def find_excel_files(directory: Path) -> list[Path]:
    """Find all Excel files in a directory."""
    excel_files = []

    # Find .xlsx files
    excel_files.extend(sorted(directory.glob("*.xlsx")))

    # Find .xls files
    excel_files.extend(sorted(directory.glob("*.xls")))

    return excel_files


def process_single_file(
    file_path: Path,
    columns: ColumnMap,
    default_year: int,
    sheet_name: str | int | None,
    add_source: bool = False,
) -> tuple[list, str]:
    """Process a single Excel file and return parsed cases and source filename.

    Args:
        file_path: Path to the Excel file
        columns: Column mapping configuration
        default_year: Default year for date parsing
        sheet_name: Sheet name or index to read
        add_source: Whether to track the source filename

    Returns:
        Tuple of (parsed_cases, source_filename)
    """
    console.print(f"[cyan]Processing:[/cyan] {file_path.name}")

    # Read input file
    df = read_excel(str(file_path), sheet_name=sheet_name or 0)

    if df.empty:
        console.print(f"[yellow]  Warning:[/yellow] {file_path.name} is empty, skipping")
        return [], ""

    # Process data
    processor = CaseProcessor(columns, default_year)
    parsed_cases = processor.process_dataframe(df)

    console.print(f"[green]  ✓[/green] Parsed {len(parsed_cases)} cases from {file_path.name}")

    return parsed_cases, file_path.name if add_source else ""


def main() -> None:  # noqa: PLR0915
    """Main entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()
    output_file = Path(args.output_file)
    # Set up logging
    setup_logging(level=args.log_level, verbose=args.verbose)

    try:
        # Validate arguments
        validate_arguments(args)

        # Create column mapping
        columns = columns_from_args(args)

        # Initialize handlers
        excel_handler = ExcelHandler()
        input_path = Path(args.input_file)

        # Handle CSV v2 format
        if hasattr(args, "v2") and args.v2:
            console.print(
                Panel(
                    f"[cyan]Processing CSV v2 format from:[/cyan] {input_path}\n"
                    f"[cyan]Output file:[/cyan] {args.output_file}",
                    title="CSV v2 Mode",
                    border_style="cyan",
                )
            )

            from .csv_io import read_csv_v2

            # Read CSV v2 format
            import pandas as pd

            df = read_csv_v2(
                input_path, add_source=args.add_source_column, column_map=columns
            )

            # Process data
            processor = CaseProcessor(columns, args.default_year)
            all_parsed_cases = processor.process_dataframe(df)

            # Convert to DataFrame for output
            output_df = processor.cases_to_dataframe(all_parsed_cases)

            # Preserve Source File column if added
            if args.add_source_column and "Source File" in df.columns:
                output_df.insert(0, "Source File", df["Source File"])

        # Excel format (original logic)
        else:
            # Determine if input is a file or directory
            all_parsed_cases = []
            source_filenames = []

            if input_path.is_file():
                # Process single file
                parsed_cases, source_name = process_single_file(
                    input_path,
                    columns,
                    args.default_year,
                    args.sheet,
                    args.add_source_column,
                )
                all_parsed_cases.extend(parsed_cases)
                if args.add_source_column:
                    source_filenames.extend([source_name] * len(parsed_cases))

            elif input_path.is_dir():
                # Process all Excel files in directory
                excel_files = find_excel_files(input_path)

                if not excel_files:
                    console.print("[yellow]Warning:[/yellow] No Excel files found in directory")
                    return

                console.print(
                    f"\n[bold cyan]Found {len(excel_files)} Excel file(s) in directory[/bold cyan]\n"
                )

                for excel_file in excel_files:
                    parsed_cases, source_name = process_single_file(
                        excel_file,
                        columns,
                        args.default_year,
                        args.sheet,
                        args.add_source_column,
                    )
                    all_parsed_cases.extend(parsed_cases)
                    if args.add_source_column:
                        source_filenames.extend([source_name] * len(parsed_cases))

                console.print(
                    f"\n[bold green]Processed {len(excel_files)} files, "
                    f"total {len(all_parsed_cases)} cases[/bold green]\n"
                )

            if not all_parsed_cases:
                console.print("[yellow]Warning:[/yellow] No cases to process")
                return

            # Convert to DataFrame
            processor = CaseProcessor(columns, args.default_year)
            output_df = processor.cases_to_dataframe(all_parsed_cases)

            # Add source file column if requested
            if args.add_source_column and source_filenames:
                output_df.insert(0, "Source File", source_filenames)

        # Generate validation report if requested
        if args.validation_report:
            report_path = Path(args.validation_report)
            report = ValidationReport(all_parsed_cases)

            # Determine format from extension
            if report_path.suffix.lower() == ".json":
                format_type = "json"
            elif report_path.suffix.lower() in {".xlsx", ".xls"}:
                format_type = "excel"
            else:
                format_type = "text"

            report.save_report(report_path, output_format=format_type)
            console.print(f"\n[green]Validation report saved to:[/green] {report_path}")

            # Print summary to console
            summary = report.get_summary()
            console.print()
            console.print(
                Panel(
                    "[bold]Validation Summary[/bold]",
                    border_style="cyan",
                )
            )

            # Create summary table
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
            console.print()

        # Write output
        excel_handler.write_excel(
            output_df, args.output_file, fixed_widths={"Original Procedure": 12}
        )

        # Print summary
        summary = excel_handler.get_data_summary(output_df)
        print_summary(output_file, summary)

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except ValueError as e:
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


def print_summary(output_file: Path, summary: dict[str, Any]):
    console.print()
    console.print(
        Panel(
            "[bold]Output Summary[/bold]",
            border_style="green",
        )
    )

    # Create summary table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(style="white")

    table.add_row("Cases:", str(summary["total_cases"]))
    table.add_row("Date range:", summary["date_range"])

    console.print(table)

    if summary["empty_cases"] > 0:
        console.print(
            f"  [yellow]Warning:[/yellow] {summary['empty_cases']} "
            "cases have empty Case IDs"
        )

    console.print()
    console.print(f"[green]Output saved to:[/green] {output_file}")
    console.print("[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
