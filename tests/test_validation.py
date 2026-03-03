"""Tests for ValidationReport."""

from __future__ import annotations

import json
from datetime import date

import pytest

from case_parser.domain import (
    AgeCategory,
    AirwayManagement,
    AnesthesiaType,
    MonitoringTechnique,
    ParsedCase,
    ProcedureCategory,
    VascularAccess,
)
from case_parser.validation import ValidationReport


def _make_case(
    episode_id: str | None = "C001",
    confidence_score: float = 0.9,
    warnings: list[str] | None = None,
    airway: list[AirwayManagement] | None = None,
    vascular: list[VascularAccess] | None = None,
    monitoring: list[MonitoringTechnique] | None = None,
    responsible_provider: str | None = "Dr. Smith",
    procedure: str | None = "Hip Replacement",
    age_category: AgeCategory | None = AgeCategory.TWELVE_YR_TO_65_YR,
) -> ParsedCase:
    """Build a minimal ParsedCase for testing."""
    return ParsedCase(
        raw_date="08/27/2025",
        episode_id=episode_id,
        raw_age=45.0,
        raw_asa="2",
        raw_anesthesia_type="General",
        procedure=procedure,
        procedure_notes=None,
        responsible_provider=responsible_provider,
        case_date=date(2025, 8, 27),
        age_category=age_category,
        anesthesia_type=AnesthesiaType.GENERAL,
        procedure_category=ProcedureCategory.OTHER,
        airway_management=airway or [],
        vascular_access=vascular or [],
        monitoring=monitoring or [],
        parsing_warnings=warnings or [],
        confidence_score=confidence_score,
    )


@pytest.fixture
def sample_cases() -> list[ParsedCase]:
    """Three cases with varying warnings and confidence levels."""
    return [
        _make_case("C001", confidence_score=0.9, warnings=[]),
        _make_case(
            "C002",
            confidence_score=0.6,
            warnings=["Missing age value", "Missing age value"],
        ),
        _make_case("C003", confidence_score=0.3, warnings=[]),
        _make_case(
            "C004",
            confidence_score=0.8,
            warnings=["Missing age value"],
            airway=[AirwayManagement.ORAL_ETT],
            vascular=[VascularAccess.ARTERIAL_CATHETER],
            monitoring=[MonitoringTechnique.TEE],
        ),
        _make_case(
            episode_id=None,
            confidence_score=0.95,
            warnings=[],
            responsible_provider=None,
            procedure=None,
            age_category=None,
        ),
    ]


class TestGetSummary:
    def test_empty_cases_list(self):
        report = ValidationReport([])
        summary = report.get_summary()

        assert summary["total_cases"] == 0
        assert summary["average_confidence"] == 0
        assert summary["cases_with_warnings"] == 0
        assert summary["low_confidence_cases"] == 0

    def test_counts_cases_with_warnings(self, sample_cases):
        report = ValidationReport(sample_cases)
        summary = report.get_summary()

        # C002 and C004 have warnings
        assert summary["cases_with_warnings"] == 2

    def test_counts_low_confidence_cases(self, sample_cases):
        report = ValidationReport(sample_cases)
        summary = report.get_summary()

        # is_low_confidence uses threshold=0.7; C002 (0.6) and C003 (0.3) are below
        assert summary["low_confidence_cases"] == 2

    def test_warning_type_aggregation(self, sample_cases):
        report = ValidationReport(sample_cases)
        summary = report.get_summary()

        # "Missing age value" appears 3 times total (2 from C002, 1 from C004)
        assert summary["warning_types"].get("Missing age value") == 3

    def test_missing_field_counts(self, sample_cases):
        report = ValidationReport(sample_cases)
        summary = report.get_summary()

        # C005 is missing episode_id, responsible_provider, procedure, age_category
        assert summary["missing_fields"]["episode_id"] == 1
        assert summary["missing_fields"]["provider"] == 1
        assert summary["missing_fields"]["procedure"] == 1
        assert summary["missing_fields"]["age_category"] == 1


class TestGetProblematicCases:
    def test_returns_cases_with_warnings(self, sample_cases):
        report = ValidationReport(sample_cases)
        problematic = report.get_problematic_cases()

        ids = {c.episode_id for c in problematic}
        assert "C002" in ids
        assert "C004" in ids

    def test_returns_low_confidence_cases_without_warnings(self, sample_cases):
        # C003 has confidence 0.3 (below max_confidence=0.4 default) and no warnings
        report = ValidationReport(sample_cases)
        problematic = report.get_problematic_cases()

        ids = {c.episode_id for c in problematic}
        assert "C003" in ids

    def test_excludes_normal_cases(self, sample_cases):
        report = ValidationReport(sample_cases)
        problematic = report.get_problematic_cases()

        ids = {c.episode_id for c in problematic}
        # C001: high confidence, no warnings → not problematic
        assert "C001" not in ids

    def test_empty_input(self):
        report = ValidationReport([])
        assert report.get_problematic_cases() == []


class TestGenerateJsonReport:
    def test_returns_dict_with_expected_keys(self, sample_cases):
        report = ValidationReport(sample_cases)
        result = report.generate_json_report()

        assert "summary" in result
        assert "problematic_cases" in result
        assert "extraction_details" in result

    def test_extraction_statistics_included(self, sample_cases):
        report = ValidationReport(sample_cases)
        result = report.generate_json_report()

        details = result["extraction_details"]
        assert "cases_with_airway_extraction" in details
        assert "extraction_rate" in details

    def test_problematic_cases_listed(self, sample_cases):
        report = ValidationReport(sample_cases)
        result = report.generate_json_report()

        assert len(result["problematic_cases"]) > 0


class TestGetExtractionStatistics:
    def test_counts_each_extraction_type(self, sample_cases):
        report = ValidationReport(sample_cases)
        # C004 has airway, vascular, monitoring
        stats = report._get_extraction_statistics()

        assert stats["cases_with_airway_extraction"] == 1
        assert stats["cases_with_vascular_extraction"] == 1
        assert stats["cases_with_monitoring_extraction"] == 1

    def test_zero_extractions(self):
        cases = [_make_case("X1"), _make_case("X2")]
        report = ValidationReport(cases)
        stats = report._get_extraction_statistics()

        assert stats["cases_with_airway_extraction"] == 0
        assert stats["extraction_rate"]["airway"] == 0

    def test_rates_sum_correctly(self, sample_cases):
        report = ValidationReport(sample_cases)
        stats = report._get_extraction_statistics()

        total = len(sample_cases)
        expected_airway_rate = round(stats["cases_with_airway_extraction"] / total, 3)
        assert stats["extraction_rate"]["airway"] == expected_airway_rate


class TestToDataframe:
    def test_returns_dataframe_with_expected_columns(self, sample_cases):
        report = ValidationReport(sample_cases)
        df = report.to_dataframe()

        expected = {
            "Case ID",
            "Has Warnings",
            "Warning Count",
            "Warnings",
            "Confidence Score",
            "Low Confidence",
            "Missing Fields",
        }
        assert set(df.columns) == expected

    def test_one_row_per_case(self, sample_cases):
        report = ValidationReport(sample_cases)
        df = report.to_dataframe()

        assert len(df) == len(sample_cases)

    def test_field_values_formatted_correctly(self, sample_cases):
        report = ValidationReport(sample_cases)
        df = report.to_dataframe()

        # Has Warnings should be "Yes" or "No"
        assert set(df["Has Warnings"].unique()).issubset({"Yes", "No"})
        # Confidence Score is formatted as a string with 3 decimal places
        assert (
            df.loc[0, "Confidence Score"] == f"{sample_cases[0].confidence_score:.3f}"
        )


class TestSaveReport:
    def test_saves_text_report(self, tmp_path, sample_cases):
        report = ValidationReport(sample_cases)
        path = tmp_path / "report.txt"

        report.save_report(path, "text")

        assert path.exists()
        assert path.stat().st_size > 0

    def test_saves_json_report(self, tmp_path, sample_cases):
        report = ValidationReport(sample_cases)
        path = tmp_path / "report.json"

        report.save_report(path, "json")

        assert path.exists()
        parsed = json.loads(path.read_text())
        assert "summary" in parsed

    def test_saves_excel_report(self, tmp_path, sample_cases):
        report = ValidationReport(sample_cases)
        path = tmp_path / "report.xlsx"

        report.save_report(path, "excel")

        assert path.exists()

    def test_raises_for_invalid_format(self, tmp_path, sample_cases):
        report = ValidationReport(sample_cases)
        path = tmp_path / "report.xyz"

        with pytest.raises(ValueError, match="Unsupported format"):
            report.save_report(path, "xyz")

    def test_creates_parent_directory(self, tmp_path, sample_cases):
        report = ValidationReport(sample_cases)
        path = tmp_path / "nested" / "dir" / "report.txt"

        report.save_report(path, "text")

        assert path.exists()
