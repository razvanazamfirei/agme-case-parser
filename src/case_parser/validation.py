"""Validation and reporting for parsed cases."""

from __future__ import annotations

import json
from operator import itemgetter
from pathlib import Path
from typing import Any

import pandas as pd

from .domain import ParsedCase


class ValidationReport:
    """Generate validation reports for parsed cases."""

    def __init__(self, cases: list[ParsedCase]):
        """Initialize with list of parsed cases."""
        self.cases = cases

    def get_summary(self) -> dict[str, Any]:
        """Get overall validation summary statistics."""
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
        self, min_warnings: int = 1, max_confidence: float = 0.7
    ) -> list[ParsedCase]:
        """
        Get cases that have issues.

        Args:
            min_warnings: Minimum number of warnings to be considered problematic
            max_confidence: Maximum confidence score to be considered problematic

        Returns:
            List of problematic cases
        """
        return [
            case
            for case in self.cases
            if (
                len(case.parsing_warnings) >= min_warnings
                or case.confidence_score <= max_confidence
            )
        ]

    def generate_text_report(self) -> str:
        """Generate human-readable text report."""
        summary = self.get_summary()
        total = summary["total_cases"]
        warnings_pct = summary["cases_with_warnings"] / total * 100
        low_conf_pct = summary["low_confidence_cases"] / total * 100

        lines = [
            "=" * 80,
            "VALIDATION REPORT",
            "=" * 80,
            "",
            "SUMMARY",
            "-" * 80,
            f"Total Cases: {total}",
            f"Cases with Warnings: {summary['cases_with_warnings']} "
            f"({warnings_pct:.1f}%)",
            f"Low Confidence Cases: {summary['low_confidence_cases']} "
            f"({low_conf_pct:.1f}%)",
            f"Average Confidence: {summary['average_confidence']:.3f}",
            "",
            "MISSING CRITICAL FIELDS",
            "-" * 80,
        ]

        # Summary statistics

        # Missing fields
        for field, count in summary["missing_fields"].items():
            if count > 0:
                pct = count / summary["total_cases"] * 100
                lines.append(f"  {field}: {count} cases ({pct:.1f}%)")
        lines.append("")

        # Warning types
        if summary["warning_types"]:
            lines.extend(("WARNING TYPES (Top 10)", "-" * 80))
            sorted_warnings = sorted(
                summary["warning_types"].items(), key=itemgetter(1), reverse=True
            )
            for warning, count in sorted_warnings[:10]:
                lines.append(f"  [{count:3d}] {warning}")
            lines.append("")

        # Problematic cases details
        problematic = self.get_problematic_cases()
        if problematic:
            lines.extend((f"PROBLEMATIC CASES ({len(problematic)} cases)", "-" * 80))
            for i, case in enumerate(problematic[:20], 1):  # Show first 20
                self.print_problematic_case(case, i, lines)

            if len(problematic) > 20:
                lines.append(
                    f"\n... and {len(problematic) - 20} more problematic cases"
                )
            lines.append("")

        lines.extend(("=" * 80, "END OF REPORT", "=" * 80))

        return "\n".join(lines)

    @staticmethod
    def print_problematic_case(case: ParsedCase, i: int, lines: list[str | Any]):
        missing_fields = ", ".join(case._get_missing_critical_fields()) or "None"
        lines.extend(
            (
                f"\n{i}. Case ID: {case.episode_id or 'UNKNOWN'}",
                f"   Confidence: {case.confidence_score:.3f}",
                f"   Warnings ({len(case.parsing_warnings)}):",
            )
        )
        lines.extend(f"     - {warning}" for warning in case.parsing_warnings)
        lines.append(f"   Missing fields: {missing_fields}")

    def generate_json_report(self) -> dict[str, Any]:
        """Generate machine-readable JSON report."""
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
        """Get statistics about extraction performance."""
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
        """Convert validation summary to DataFrame for Excel export."""
        rows = []
        for case in self.cases:
            summary = case.get_validation_summary()
            rows.append(
                {
                    "Case ID": summary["case_id"] or "",
                    "Has Warnings": "Yes" if summary["has_warnings"] else "No",
                    "Warning Count": summary["warning_count"],
                    "Warnings": "; ".join(summary["warnings"]),
                    "Confidence Score": f"{summary['confidence_score']:.3f}",
                    "Low Confidence": "Yes" if summary["is_low_confidence"] else "No",
                    "Missing Fields": ", ".join(summary["missing_fields"]) or "None",
                }
            )
        return pd.DataFrame(rows)

    def save_report(self, output_path: str | Path, output_format: str = "text") -> None:
        """
        Save validation report to file.

        Args:
            output_path: Path to save report
            output_format: 'text', 'json', or 'excel'
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
