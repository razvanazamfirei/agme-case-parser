"""Tests for domain models."""

from datetime import date

import pytest
from pydantic import ValidationError

from case_parser.domain import (
    AgeCategory,
    AirwayManagement,
    AnesthesiaType,
    ParsedCase,
    ProcedureCategory,
)


def test_age_category_enum():
    """Test age category enum values."""
    assert AgeCategory.UNDER_3_MONTHS.value == "a. < 3 months"
    assert AgeCategory.OVER_65_YR.value == "e. >= 65 year"


def test_anesthesia_type_enum():
    """Test anesthesia type enum values."""
    assert AnesthesiaType.GENERAL.value == "GA"
    assert AnesthesiaType.MAC.value == "MAC"
    assert AnesthesiaType.SPINAL.value == "Spinal"


def test_parsed_case_creation():
    """Test creating a ParsedCase with minimal data."""
    case = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=["ORTHO"],
        procedure="Hip Replacement",
        procedure_notes="Intubation routine",
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
        age_category=AgeCategory.TWELVE_YR_TO_65_YR,
        asa_physical_status="2",
        anesthesia_type=AnesthesiaType.GENERAL,
        procedure_category=ProcedureCategory.OTHER,
    )

    assert case.episode_id == "12345"
    assert case.age_category == AgeCategory.TWELVE_YR_TO_65_YR
    assert case.anesthesia_type == AnesthesiaType.GENERAL
    assert case.confidence_score == 1.0  # default


def test_services_field_validator():
    """Test that services field properly splits newline-separated values."""
    # Test with string input
    case = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services="ORTHO\nTRAUMA",  # Newline-separated
        procedure="Hip Replacement",
        procedure_notes=None,
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
    )

    assert case.services == ["ORTHO", "TRAUMA"]


def test_services_field_validator_with_list():
    """Test that services field accepts list input."""
    case = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=["ORTHO", "TRAUMA"],
        procedure="Hip Replacement",
        procedure_notes=None,
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
    )

    assert case.services == ["ORTHO", "TRAUMA"]


def test_to_output_dict():
    """Test conversion to output dictionary format."""
    case = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=["ORTHO"],
        procedure="Hip Replacement",
        procedure_notes="Intubation routine",
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
        age_category=AgeCategory.TWELVE_YR_TO_65_YR,
        asa_physical_status="2",
        anesthesia_type=AnesthesiaType.GENERAL,
        procedure_category=ProcedureCategory.OTHER,
        airway_management=[
            AirwayManagement.ORAL_ETT,
            AirwayManagement.DIRECT_LARYNGOSCOPE,
        ],
    )

    output = case.to_output_dict()

    assert output["Case ID"] == "12345"
    assert output["Case Date"] == "08/27/2025"
    assert output["Supervisor"] == "Dr. Smith"
    assert output["Age"] == "d. >= 12 yr. and < 65 yr."
    assert output["Original Procedure"] == "Hip Replacement"
    assert output["ASA Physical Status"] == "2"
    assert output["Anesthesia Type"] == "GA"
    assert output["Airway Management"] == "Oral ETT; Direct Laryngoscope"
    assert output["Procedure Category"] == "Other (procedure cat)"


def test_to_output_dict_with_empty_extractions():
    """Test that empty extractions produce empty strings in output."""
    case = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=[],
        procedure="Test Procedure",
        procedure_notes=None,
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
        airway_management=[],  # Empty
        vascular_access=[],  # Empty
        monitoring=[],  # Empty
    )

    output = case.to_output_dict()

    assert output["Airway Management"] == ""
    assert output["Specialized Vascular Access"] == ""
    assert output["Specialized Monitoring Techniques"] == ""


def test_has_warnings():
    """Test warning detection."""
    case_without_warnings = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=[],
        procedure="Test",
        procedure_notes=None,
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
        parsing_warnings=[],
    )

    case_with_warnings = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=[],
        procedure="Test",
        procedure_notes=None,
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
        parsing_warnings=["Missing procedure notes"],
    )

    assert not case_without_warnings.has_warnings()
    assert case_with_warnings.has_warnings()


def test_is_low_confidence():
    """Test confidence threshold checking."""
    high_confidence = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=[],
        procedure="Test",
        procedure_notes=None,
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
        confidence_score=0.9,
    )

    low_confidence = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=[],
        procedure="Test",
        procedure_notes=None,
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
        confidence_score=0.5,
    )

    assert not high_confidence.is_low_confidence()
    assert low_confidence.is_low_confidence()


def test_get_validation_summary():
    """Test validation summary generation."""
    case = ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=None,  # Missing
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=[],
        procedure=None,  # Missing
        procedure_notes=None,
        responsible_provider=None,  # Missing
        case_date=date(2025, 8, 27),
        parsing_warnings=["Test warning"],
        confidence_score=0.6,
    )

    summary = case.get_validation_summary()

    assert summary["case_id"] == "12345"
    assert summary["has_warnings"] is True
    assert summary["warning_count"] == 1
    assert summary["warnings"] == ["Test warning"]
    assert summary["confidence_score"] == 0.6
    assert summary["is_low_confidence"] is True
    assert "responsible_provider" in summary["missing_fields"]
    assert "procedure" in summary["missing_fields"]
    assert "age_category" in summary["missing_fields"]


def test_confidence_score_validation():
    """Test that confidence score must be between 0 and 1."""
    # Valid confidence
    ParsedCase(
        raw_date="08/27/2025",
        episode_id="12345",
        raw_age=45.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type="general",
        services=[],
        procedure="Test",
        procedure_notes=None,
        responsible_provider="Dr. Smith",
        case_date=date(2025, 8, 27),
        confidence_score=0.5,
    )

    # Invalid confidence (too high)
    with pytest.raises(ValidationError):
        ParsedCase(
            raw_date="08/27/2025",
            episode_id="12345",
            raw_age=45.0,
            raw_asa="2",
            emergent=False,
            raw_anesthesia_type="general",
            services=[],
            procedure="Test",
            procedure_notes=None,
            responsible_provider="Dr. Smith",
            case_date=date(2025, 8, 27),
            confidence_score=1.5,
        )

    # Invalid confidence (negative)
    with pytest.raises(ValidationError):
        ParsedCase(
            raw_date="08/27/2025",
            episode_id="12345",
            raw_age=45.0,
            raw_asa="2",
            emergent=False,
            raw_anesthesia_type="general",
            services=[],
            procedure="Test",
            procedure_notes=None,
            responsible_provider="Dr. Smith",
            case_date=date(2025, 8, 27),
            confidence_score=-0.1,
        )
