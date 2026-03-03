"""Validation and reporting for parsed cases."""

from __future__ import annotations

import json
from operator import itemgetter
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .domain import ParsedCase


class ValidationReport:
    """Generate validation reports for parsed cases."""

    def __init__(self, cases: list[ParsedCase]):
        """Initialize with list of parsed cases.

        Args:
            cases: Parsed cases to validate and report on.
        """
        self.cases = cases

    def get_summary(self) -> dict[str, Any]:
        """Get overall validation summary statistics.

        Returns:
            Dict with keys: total_cases, cases_with_warnings,
            low_confidence_cases, average_confidence, warning_types (dict of
            warning message to count), and missing_fields (dict of field name
            to count of cases missing that field).
        """
        total_cases = len(self.cases)
        cases_with_warnings = sum(1 for case in self.cases if case.has_warnings())
        low_confidence_cases = sum(1 for case in self.cases if case.is_low_confidence())

        # Collect all unique warnings
        all_warnings = []
        for case in self.cases:
            all_warnings.extend(case.parsing_warnings)

        warning_counts: dict[str, int] = {}
        for warning in all_warnings:
            warning_counts[warning] = warning_counts.get(warning, 0) + 1

        # Calculate average confidence
        avg_confidence = (
            sum(case.confidence_score for case in self.cases) / total_cases
            if total_cases > 0
            else 0
        )

        # Missing critical fields
        missing_episode_id = sum(1 for case in self.cases if not case.episode_id)
        missing_provider = sum(
            1 for case in self.cases if not case.responsible_provider
        )
        missing_procedure = sum(1 for case in self.cases if not case.procedure)
        missing_age = sum(1 for case in self.cases if not case.age_category)

        return {
            "total_cases": total_cases,
            "cases_with_warnings": cases_with_warnings,
            "low_confidence_cases": low_confidence_cases,
            "average_confidence": round(avg_confidence, 3),
            "warning_types": warning_counts,
            "missing_fields": {
                "episode_id": missing_episode_id,
                "provider": missing_provider,
                "procedure": missing_procedure,
                "age_category": missing_age,
            },
        }

    def get_problematic_cases(
        self, min_warnings: int = 1, max_confidence: float = 0.4
    ) -> list[ParsedCase]:
        """
        Get cases that have issues.

        A case is considered problematic if it has warnings OR very low confidence.
        Routine cases with moderate confidence (0.5-0.9) and no warnings are not
        flagged as problematic.

        Args:
            min_warnings: Minimum number of warnings to be considered problematic
            max_confidence: Maximum confidence score to be considered problematic
                (only applies if case has NO warnings)

        Returns:
            List of problematic cases
        """
        return [
            case
            for case in self.cases
            if (
                len(case.parsing_warnings) >= min_warnings
                or (
                    case.confidence_score < max_confidence
                    and len(case.parsing_warnings) == 0
                )
            )
        ]

    @staticmethod
    def _print_summary_section(console: Console, summary: dict[str, Any]):
        """Print summary section of validation report.

        Args:
            console: Rich Console to write output to.
            summary: Summary dict as returned by get_summary().
        """
        total = summary["total_cases"]
        warnings_pct = summary["cases_with_warnings"] / total * 100 if total > 0 else 0
        low_conf_pct = summary["low_confidence_cases"] / total * 100 if total > 0 else 0

        console.print("[bold cyan]SUMMARY[/bold cyan]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold", no_wrap=True)
        table.add_column()

        table.add_row("Total Cases:", str(total))
        table.add_row(
            "Cases with Warnings:",
            f"{summary['cases_with_warnings']} ({warnings_pct:.1f}%)",
        )
        table.add_row(
            "Low Confidence Cases:",
            f"{summary['low_confidence_cases']} ({low_conf_pct:.1f}%)",
        )
        table.add_row("Average Confidence:", f"{summary['average_confidence']:.3f}")
        console.print(table)
        console.print()

    @staticmethod
    def _print_missing_fields_section(
        console: Console, summary: dict[str, Any], total: int
    ):
        """Print missing fields section of validation report.

        Args:
            console: Rich Console to write output to.
            summary: Summary dict as returned by get_summary().
            total: Total number of cases, used to compute percentages.
        """
        if not any(summary["missing_fields"].values()):
            return

        console.print("[bold yellow]MISSING CRITICAL FIELDS[/bold yellow]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold", no_wrap=True)
        table.add_column()

        for field, count in summary["missing_fields"].items():
            if count > 0:
                pct = count / total * 100 if total > 0 else 0
                table.add_row(f"{field}:", f"{count} cases ({pct:.1f}%)")
        console.print(table)
        console.print()

    @staticmethod
    def _print_warning_types_section(console: Console, summary: dict[str, Any]):
        """Print warning types section of validation report.

        Args:
            console: Rich Console to write output to.
            summary: Summary dict as returned by get_summary(). The top 10
                warning types by frequency are displayed.
        """
        if not summary["warning_types"]:
            return

        console.print("[bold yellow]WARNING TYPES (Top 10)[/bold yellow]")
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("Count", justify="right", style="cyan")
        table.add_column("Warning")

        sorted_warnings = sorted(
            summary["warning_types"].items(), key=itemgetter(1), reverse=True
        )
        for warning, count in sorted_warnings[:10]:
            table.add_row(str(count), warning)
        console.print(table)
        console.print()

    def _print_problematic_cases_section(self, console: Console):
        """Print problematic cases section of validation report.

        Args:
            console: Rich Console to write output to. Up to 20 problematic
                cases are printed; a count of remaining cases is shown if more
                exist.
        """
        problematic = self.get_problematic_cases()
        if not problematic:
            return

        console.print(
            f"[bold red]PROBLEMATIC CASES ({len(problematic)} cases)[/bold red]"
        )
        for i, case in enumerate(problematic[:20], 1):
            missing_fields = ", ".join(case.get_missing_critical_fields()) or "None"
            console.print(
                f"\n[bold]{i}. Case ID:[/bold] {case.episode_id or 'UNKNOWN'}"
            )
            console.print(f"   [bold]Confidence:[/bold] {case.confidence_score:.3f}")
            console.print(f"   [bold]Warnings ({len(case.parsing_warnings)}):[/bold]")
            for warning in case.parsing_warnings:
                console.print(f"     • {warning}")
            console.print(f"   [bold]Missing fields:[/bold] {missing_fields}")

        if len(problematic) > 20:
            console.print(f"\n... and {len(problematic) - 20} more problematic cases")
        console.print()

    def generate_text_report(self) -> str:
        """Generate human-readable text report.

        Returns:
            Multi-line string containing the full validation report rendered
            with Rich formatting stripped to plain text.
        """
        console = Console(
            file=None, width=100, force_terminal=False, legacy_windows=False
        )

        with console.capture() as capture:
            summary = self.get_summary()

            # Header
            console.print(
                Panel(
                    "[bold]VALIDATION REPORT[/bold]",
                    border_style="cyan",
                    expand=False,
                )
            )
            console.print()

            # Print sections
            self._print_summary_section(console, summary)
            self._print_missing_fields_section(console, summary, summary["total_cases"])
            self._print_warning_types_section(console, summary)
            self._print_problematic_cases_section(console)

            # Footer
            console.print(
                Panel(
                    "[bold]END OF REPORT[/bold]",
                    border_style="cyan",
                    expand=False,
                )
            )

        return capture.get()

    def generate_json_report(self) -> dict[str, Any]:
        """Generate machine-readable JSON report.

        Returns:
            Dict with keys: summary (from get_summary()), problematic_cases
            (validation summaries for flagged cases), and extraction_details
            (extraction performance statistics).
        """
        summary = self.get_summary()
        problematic = self.get_problematic_cases()

        return {
            "summary": summary,
            "problematic_cases": [
                case.get_validation_summary() for case in problematic
            ],
            "extraction_details": self._get_extraction_statistics(),
        }

    def _get_extraction_statistics(self) -> dict[str, Any]:
        """Get statistics about extraction performance.

        Returns:
            Dict with counts of cases with each extraction type, per-type
            value breakdowns, and extraction rates (as fractions of total cases)
            for airway, vascular, and monitoring.
        """
        total_cases = len(self.cases)

        # Count extraction types
        airway_extractions = sum(1 for case in self.cases if case.airway_management)
        vascular_extractions = sum(1 for case in self.cases if case.vascular_access)
        monitoring_extractions = sum(1 for case in self.cases if case.monitoring)

        # Detailed extraction counts
        airway_types: dict[str, int] = {}
        vascular_types: dict[str, int] = {}
        monitoring_types: dict[str, int] = {}

        for case in self.cases:
            for airway in case.airway_management:
                airway_types[airway.value] = airway_types.get(airway.value, 0) + 1
            for vascular in case.vascular_access:
                vascular_types[vascular.value] = (
                    vascular_types.get(vascular.value, 0) + 1
                )
            for monitor in case.monitoring:
                monitoring_types[monitor.value] = (
                    monitoring_types.get(monitor.value, 0) + 1
                )

        return {
            "cases_with_airway_extraction": airway_extractions,
            "cases_with_vascular_extraction": vascular_extractions,
            "cases_with_monitoring_extraction": monitoring_extractions,
            "airway_types": airway_types,
            "vascular_types": vascular_types,
            "monitoring_types": monitoring_types,
            "extraction_rate": {
                "airway": round(airway_extractions / total_cases, 3)
                if total_cases > 0
                else 0,
                "vascular": round(vascular_extractions / total_cases, 3)
                if total_cases > 0
                else 0,
                "monitoring": round(monitoring_extractions / total_cases, 3)
                if total_cases > 0
                else 0,
            },
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Convert validation summary to DataFrame for Excel export.

        Returns:
            DataFrame with one row per case containing Case ID, warning
            flags and counts, confidence score, low-confidence flag, and
            a semicolon-separated list of missing critical fields.
        """
        rows = []
        for case in self.cases:
            summary = case.get_validation_summary()
            rows.append({
                "Case ID": summary["case_id"] or "",
                "Has Warnings": "Yes" if summary["has_warnings"] else "No",
                "Warning Count": summary["warning_count"],
                "Warnings": "; ".join(summary["warnings"]),
                "Confidence Score": f"{summary['confidence_score']:.3f}",
                "Low Confidence": "Yes" if summary["is_low_confidence"] else "No",
                "Missing Fields": "; ".join(summary["missing_fields"]) or "None",
            })
        return pd.DataFrame(rows)

    def save_report(self, output_path: str | Path, output_format: str = "text") -> None:
        """
        Save validation report to file.

        Args:
            output_path: Path to save report
            output_format: 'text', 'json', or 'excel'

        Raises:
            ValueError: If output_format is not one of the supported values.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_format == "text":
            text_report = self.generate_text_report()
            output_path.write_text(text_report, encoding="utf-8")
        elif output_format == "json":
            json_report = self.generate_json_report()
            output_path.write_text(json.dumps(json_report, indent=2), encoding="utf-8")
        elif output_format == "excel":
            df = self.to_dataframe()
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Validation", index=False)
        else:
            raise ValueError(
                f"Unsupported format: {output_format}. Use 'text', 'json', or 'excel'"
            )
