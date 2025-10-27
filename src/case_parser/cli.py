"""Command line interface for the case parser."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from .exceptions import CaseParserError
from .io import ExcelHandler, read_excel
from .logging_config import setup_logging
from .models import ColumnMap
from .processors import CaseProcessor


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert anesthesia Excel file to case log format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.xlsx output.xlsx
  %(prog)s input.xlsx output.xlsx --sheet "Data" --default-year 2024
  %(prog)s input.xlsx output.xlsx --col-date "Date of Service" --col-age "Patient Age"
        """,
    )

    # Required arguments
    parser.add_argument("input_file", help="Input Excel file path (.xlsx or .xls)")
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
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if input_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(f"Unsupported input file format: {input_path.suffix}")

    if not output_path.suffix.lower() == ".xlsx":
        raise ValueError("Output file must have .xlsx extension")

    if args.default_year < 1900 or args.default_year > 2100:
        raise ValueError("Default year must be between 1900 and 2100")


def main() -> None:
    """Main entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()

    # Set up logging
    setup_logging(level=args.log_level, verbose=args.verbose)

    try:
        # Validate arguments
        validate_arguments(args)

        # Create column mapping
        columns = columns_from_args(args)

        # Initialize handlers
        excel_handler = ExcelHandler()
        processor = CaseProcessor(columns, args.default_year)

        # Read input file
        df = read_excel(args.input_file, args.sheet)

        if df.empty:
            print("Warning: Input file is empty")
            return

        # Process data
        output_df = processor.process_dataframe(df)

        # Write output
        excel_handler.write_excel(
            output_df, args.output_file, fixed_widths={"Original Procedure": 12}
        )

        # Print summary
        summary = excel_handler.get_data_summary(output_df)
        print("\nSummary:")
        print(f"  Cases: {summary['total_cases']}")
        print(f"  Date range: {summary['date_range']}")

        if summary["empty_cases"] > 0:
            print(f"  Warning: {summary['empty_cases']} cases have empty Case IDs")

        print("Done.")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except PermissionError as e:
        print(f"Permission error: {e}")
        sys.exit(1)
    except CaseParserError as e:
        print(f"Processing error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
