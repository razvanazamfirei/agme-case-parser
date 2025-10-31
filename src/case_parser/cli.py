"""Command line interface for the case parser."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any

from .enhanced_processor import EnhancedCaseProcessor
from .exceptions import CaseParserError
from .export_service import ExportService
from .io import ExcelHandler, read_excel
from .logging_config import setup_logging
from .models import ColumnMap
from .processors import CaseProcessor
from .typescript_generator import TypeScriptGenerator
from .validation import ValidationReport


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
    parser.add_argument(
        "--validation-report",
        help="Generate validation report (text, json, or excel format)",
        metavar="FILE",
    )
    parser.add_argument(
        "--use-enhanced",
        action="store_true",
        help="Use enhanced processor with typed intermediate representation",
    )
    parser.add_argument(
        "--export-json",
        metavar="FILE",
        help="Export parsed cases to JSON file for Chrome extension consumption",
    )
    parser.add_argument(
        "--export-json-dir",
        metavar="DIR",
        help="Export each case to individual JSON files in specified directory",
    )
    parser.add_argument(
        "--json-include-raw",
        action="store_true",
        help="Include raw/original field values in JSON export (for debugging)",
    )
    parser.add_argument(
        "--json-no-metadata",
        action="store_true",
        help="Exclude metadata (warnings, confidence scores) from JSON export",
    )
    parser.add_argument(
        "--generate-types",
        metavar="FILE",
        help="Generate TypeScript type definitions (.d.ts) for exported JSON",
    )
    parser.add_argument(
        "--export-with-types",
        action="store_true",
        help="Automatically generate TypeScript types alongside JSON export",
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


def main() -> None:  # noqa: PLR0912, PLR0915
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

        # Read input file
        df = read_excel(args.input_file, sheet_name=args.sheet if args.sheet else 0)

        if df.empty:
            print("Warning: Input file is empty")
            return

        # Choose processor
        if args.use_enhanced:
            print("Using enhanced processor with typed intermediate representation...")
            enhanced_processor = EnhancedCaseProcessor(columns, args.default_year)

            # Process data to get typed cases
            parsed_cases = enhanced_processor.process_dataframe(df)

            # Export to JSON if requested (before Excel conversion)
            if args.export_json:
                export_service = ExportService()
                if args.export_with_types:
                    # Export JSON with TypeScript types
                    types_path = Path(args.export_json).with_suffix(".d.ts")
                    export_service.export_cases_with_typescript_types(
                        parsed_cases,
                        args.export_json,
                        types_output_path=types_path,
                        include_metadata=not args.json_no_metadata,
                        include_raw=args.json_include_raw,
                    )
                    print(f"\nJSON export saved to: {args.export_json}")
                    print(f"TypeScript types saved to: {types_path}")
                else:
                    export_service.export_cases_to_json(
                        parsed_cases,
                        args.export_json,
                        include_metadata=not args.json_no_metadata,
                        include_raw=args.json_include_raw,
                    )
                    print(f"\nJSON export saved to: {args.export_json}")

            # Generate TypeScript types independently if requested
            if args.generate_types:
                TypeScriptGenerator.generate_type_definitions(args.generate_types)
                print(f"\nTypeScript type definitions saved to: {args.generate_types}")

            if args.export_json_dir:
                export_service = ExportService()
                created_files = export_service.export_cases_to_individual_json(
                    parsed_cases,
                    args.export_json_dir,
                    include_metadata=not args.json_no_metadata,
                    include_raw=args.json_include_raw,
                )
                print(
                    f"\nExported {len(created_files)} cases to individual JSON files in: {args.export_json_dir}"
                )

            # Convert to output dataframe
            output_df = enhanced_processor.cases_to_dataframe(parsed_cases)

            # Generate validation report if requested
            if args.validation_report:
                report_path = Path(args.validation_report)
                report = ValidationReport(parsed_cases)

                # Determine format from extension
                if report_path.suffix.lower() == ".json":
                    format_type = "json"
                elif report_path.suffix.lower() in {".xlsx", ".xls"}:
                    format_type = "excel"
                else:
                    format_type = "text"

                report.save_report(report_path, output_format=format_type)
                print(f"\nValidation report saved to: {report_path}")

                # Print summary to console
                summary = report.get_summary()
                print("\nValidation Summary:")
                print(f"  Total Cases: {summary['total_cases']}")
                print(f"  Cases with Warnings: {summary['cases_with_warnings']}")
                print(f"  Low Confidence Cases: {summary['low_confidence_cases']}")
                print(f"  Average Confidence: {summary['average_confidence']:.3f}")

        else:
            print("Using legacy processor...")
            legacy_processor = CaseProcessor(columns, args.default_year)
            output_df = legacy_processor.process_dataframe(df)

        # Write output
        excel_handler.write_excel(
            output_df, args.output_file, fixed_widths={"Original Procedure": 12}
        )

        # Print summary
        summary = excel_handler.get_data_summary(output_df)
        print_summary(output_file, summary)

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


def print_summary(output_file: Path, summary: dict[str, Any]):
    print("\nOutput Summary:")
    print(f"  Cases: {summary['total_cases']}")
    print(f"  Date range: {summary['date_range']}")

    if summary["empty_cases"] > 0:
        print(f"  Warning: {summary['empty_cases']} cases have empty Case IDs")

    print(f"\nOutput saved to: {output_file}")
    print("Done.")


if __name__ == "__main__":
    main()

