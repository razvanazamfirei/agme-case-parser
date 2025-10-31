"""Tests for enhanced case processor."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from case_parser.domain import (
    AgeCategory,
    AirwayManagement,
    AnesthesiaType,
    ParsedCase,
    ProcedureCategory,
)
from case_parser.enhanced_processor import EnhancedCaseProcessor
from case_parser.models import ColumnMap


@pytest.fixture
def default_column_map():
    """Provide default column mapping for tests."""
    return ColumnMap(
        date="Date",
        episode_id="Episode ID",
        anesthesiologist="Anesthesiologist",
        age="Age",
        asa="ASA",
        emergent="Emergent",
        final_anesthesia_type="Anesthesia Type",
        procedure="Procedure",
        services="Services",
        procedure_notes="Procedure Notes",
    )


@pytest.fixture
def processor(default_column_map):
    """Provide a processor instance for tests."""
    return EnhancedCaseProcessor(default_column_map, default_year=2025)


class TestDateParsing:
    """Test date parsing functionality."""

    def test_parse_valid_date(self, processor):
        """Test parsing a valid date."""
        parsed_date, warnings = processor.parse_date("08/27/2025")

        assert isinstance(parsed_date, datetime)
        assert parsed_date.year == 2025
        assert parsed_date.month == 8
        assert parsed_date.day == 27
        assert len(warnings) == 0

    def test_parse_missing_date(self, processor):
        """Test parsing missing date falls back to default year."""
        parsed_date, warnings = processor.parse_date(None)

        assert parsed_date.year == 2025
        assert parsed_date.month == 1
        assert parsed_date.day == 1
        assert len(warnings) == 1
        assert "default year" in warnings[0]

    def test_parse_invalid_date(self, processor):
        """Test parsing invalid date falls back to default year."""
        parsed_date, warnings = processor.parse_date("invalid-date")

        assert parsed_date.year == 2025
        assert len(warnings) == 1
        assert "Could not parse" in warnings[0]

    def test_parse_timestamp(self, processor):
        """Test parsing pandas Timestamp."""
        timestamp = pd.Timestamp("2024-12-15")
        parsed_date, warnings = processor.parse_date(timestamp)

        assert parsed_date.year == 2024
        assert parsed_date.month == 12
        assert parsed_date.day == 15
        assert len(warnings) == 0


class TestAgeCategorization:
    """Test age categorization functionality."""

    def test_categorize_infant(self, processor):
        """Test categorization of infant age."""
        category, warnings = processor.determine_age_category(0.2)  # 2.4 months

        assert category == AgeCategory.UNDER_3_MONTHS
        assert len(warnings) == 0

    def test_categorize_toddler(self, processor):
        """Test categorization of toddler age."""
        category, warnings = processor.determine_age_category(1.5)

        assert category == AgeCategory.THREE_MOS_TO_3_YR
        assert len(warnings) == 0

    def test_categorize_child(self, processor):
        """Test categorization of child age."""
        category, warnings = processor.determine_age_category(8.0)

        assert category == AgeCategory.THREE_YR_TO_12_YR
        assert len(warnings) == 0

    def test_categorize_adult(self, processor):
        """Test categorization of adult age."""
        category, warnings = processor.determine_age_category(45.0)

        assert category == AgeCategory.TWELVE_YR_TO_65_YR
        assert len(warnings) == 0

    def test_categorize_elderly(self, processor):
        """Test categorization of elderly age."""
        category, warnings = processor.determine_age_category(70.0)

        assert category == AgeCategory.OVER_65_YR
        assert len(warnings) == 0

    def test_categorize_missing_age(self, processor):
        """Test handling of missing age."""
        category, warnings = processor.determine_age_category(None)

        assert category is None
        assert len(warnings) == 1
        assert "Missing age" in warnings[0]

    def test_categorize_invalid_age(self, processor):
        """Test handling of invalid age."""
        category, warnings = processor.determine_age_category("not-a-number")

        assert category is None
        assert len(warnings) == 1
        assert "Invalid age" in warnings[0]

    def test_categorize_out_of_range_age(self, processor):
        """Test warning for out of range age."""
        _category, warnings = processor.determine_age_category(150.0)

        assert len(warnings) == 1
        assert "outside expected range" in warnings[0]


class TestAnesthesiaTypeMapping:
    """Test anesthesia type mapping functionality."""

    def test_map_general_anesthesia(self, processor):
        """Test mapping general anesthesia."""
        anesthesia_type, warnings = processor.map_anesthesia_type("General")

        assert anesthesia_type == AnesthesiaType.GENERAL
        assert len(warnings) == 0

    def test_map_general_anesthesia_variations(self, processor):
        """Test various general anesthesia notations."""
        variations = ["GENERAL", "general", "Endotracheal"]

        for variation in variations:
            anesthesia_type, _warnings = processor.map_anesthesia_type(variation)
            assert anesthesia_type == AnesthesiaType.GENERAL, f"Failed for: {variation}"

    def test_map_mac(self, processor):
        """Test mapping MAC."""
        anesthesia_type, warnings = processor.map_anesthesia_type("MAC")

        assert anesthesia_type == AnesthesiaType.MAC
        assert len(warnings) == 0

    def test_map_sedation_as_mac(self, processor):
        """Test mapping sedation to MAC."""
        anesthesia_type, warnings = processor.map_anesthesia_type("Sedation")

        assert anesthesia_type == AnesthesiaType.MAC
        assert len(warnings) == 0

    def test_map_spinal(self, processor):
        """Test mapping spinal anesthesia."""
        anesthesia_type, warnings = processor.map_anesthesia_type("Spinal")

        assert anesthesia_type == AnesthesiaType.SPINAL
        assert len(warnings) == 0

    def test_map_epidural(self, processor):
        """Test mapping epidural anesthesia."""
        anesthesia_type, warnings = processor.map_anesthesia_type("Epidural")

        assert anesthesia_type == AnesthesiaType.EPIDURAL
        assert len(warnings) == 0

    def test_map_cse(self, processor):
        """Test mapping CSE anesthesia."""
        anesthesia_type, warnings = processor.map_anesthesia_type("CSE")

        assert anesthesia_type == AnesthesiaType.CSE
        assert len(warnings) == 0

    def test_map_peripheral_nerve_block(self, processor):
        """Test mapping peripheral nerve block."""
        for variation in ["Block", "PNB"]:
            anesthesia_type, _warnings = processor.map_anesthesia_type(variation)
            assert anesthesia_type == AnesthesiaType.PERIPHERAL_NERVE_BLOCK, (
                f"Failed for: {variation}"
            )

    def test_map_missing_anesthesia_type(self, processor):
        """Test handling of missing anesthesia type."""
        anesthesia_type, warnings = processor.map_anesthesia_type(None)

        assert anesthesia_type is None
        assert len(warnings) == 1
        assert "Missing anesthesia type" in warnings[0]

    def test_map_unrecognized_anesthesia_type(self, processor):
        """Test handling of unrecognized anesthesia type."""
        anesthesia_type, warnings = processor.map_anesthesia_type("Unknown Type")

        assert anesthesia_type is None
        assert len(warnings) == 1
        assert "Unrecognized" in warnings[0]


class TestProcedureCategorization:
    """Test procedure categorization functionality."""

    def test_categorize_cardiac(self, processor):
        """Test cardiac procedure categorization."""
        category, warnings = processor.determine_procedure_category(
            "Heart surgery", ["CARDIAC"]
        )

        assert category == ProcedureCategory.CARDIAC
        assert len(warnings) == 0

    def test_categorize_intracerebral(self, processor):
        """Test intracerebral procedure categorization."""
        category, warnings = processor.determine_procedure_category(
            "Brain surgery", ["NEUROSURGERY"]
        )

        assert category == ProcedureCategory.INTRACEREBRAL
        assert len(warnings) == 0

    def test_categorize_intrathoracic(self, processor):
        """Test intrathoracic non-cardiac procedure categorization."""
        category, warnings = processor.determine_procedure_category(
            "Lung surgery", ["THORACIC"]
        )

        assert category == ProcedureCategory.INTRATHORACIC_NON_CARDIAC
        assert len(warnings) == 0

    def test_categorize_major_vessels(self, processor):
        """Test major vessels procedure categorization."""
        category, warnings = processor.determine_procedure_category(
            "Vascular surgery", ["VASCULAR"]
        )

        assert category == ProcedureCategory.MAJOR_VESSELS
        assert len(warnings) == 0

    def test_categorize_cesarean(self, processor):
        """Test cesarean procedure categorization."""
        category, warnings = processor.determine_procedure_category(
            "Cesarean delivery", ["OB/GYN"]
        )

        assert category == ProcedureCategory.CESAREAN
        assert len(warnings) == 0

    def test_categorize_cesarean_variations(self, processor):
        """Test cesarean with various notations."""
        variations = [
            ("C-SECTION delivery", ["OB"]),
            ("C SECTION", ["GYN"]),
            ("Emergency cesarean", ["OBSTETRICS"]),
        ]

        for procedure, services in variations:
            category, _warnings = processor.determine_procedure_category(
                procedure, services
            )
            assert category == ProcedureCategory.CESAREAN, f"Failed for: {procedure}"

    def test_categorize_obgyn_non_cesarean(self, processor):
        """Test non-cesarean OB/GYN procedure."""
        category, warnings = processor.determine_procedure_category(
            "Hysterectomy", ["GYN"]
        )

        assert category == ProcedureCategory.OTHER
        assert len(warnings) == 0

    def test_categorize_other(self, processor):
        """Test other procedure categorization."""
        category, warnings = processor.determine_procedure_category(
            "General surgery", ["GENERAL"]
        )

        assert category == ProcedureCategory.OTHER
        assert len(warnings) == 0

    def test_categorize_multiple_services(self, processor):
        """Test multiple categories warning."""
        category, warnings = processor.determine_procedure_category(
            "Complex procedure", ["CARDIAC", "VASCULAR"]
        )

        # Should return first category and warn
        assert category in {ProcedureCategory.CARDIAC, ProcedureCategory.MAJOR_VESSELS}
        assert len(warnings) == 1
        assert "Multiple procedure categories" in warnings[0]

    def test_categorize_empty_services(self, processor):
        """Test categorization with no services."""
        category, warnings = processor.determine_procedure_category(
            "Some procedure", []
        )

        assert category == ProcedureCategory.OTHER
        assert len(warnings) == 0


class TestEmergentFlag:
    """Test emergent flag normalization."""

    def test_normalize_emergent_true_variations(self, processor):
        """Test various true emergent flag values."""
        true_values = ["E", "Y", "YES", "TRUE", "1", "e", "yes", "true"]

        for value in true_values:
            result = processor.normalize_emergent_flag(value)
            assert result is True, f"Failed for: {value}"

    def test_normalize_emergent_false_variations(self, processor):
        """Test various false emergent flag values."""
        false_values = ["N", "NO", "FALSE", "0", "n", "no", "false", None, pd.NA]

        for value in false_values:
            result = processor.normalize_emergent_flag(value)
            assert result is False, f"Failed for: {value}"


class TestRowProcessing:
    """Test full row processing."""

    def test_process_complete_row(self, processor, default_column_map):
        """Test processing a complete row with all data."""
        row = pd.Series(
            {
                "Date": "08/27/2025",
                "Episode ID": "12345",
                "Anesthesiologist": "Dr. Smith, MD",
                "Age": 45.0,
                "ASA": "2",
                "Emergent": "N",
                "Anesthesia Type": "General",
                "Procedure": "Hip Replacement",
                "Services": "ORTHO",
                "Procedure Notes": "Patient intubated with oral ETT. Direct laryngoscope used.",
            }
        )

        case = processor.process_row(row)

        assert isinstance(case, ParsedCase)
        assert case.episode_id == "12345"
        assert case.age_category == AgeCategory.TWELVE_YR_TO_65_YR
        assert case.anesthesia_type == AnesthesiaType.GENERAL
        assert case.asa_physical_status == "2"
        assert case.responsible_provider == "Dr. Smith"
        assert case.procedure_category == ProcedureCategory.OTHER
        assert AirwayManagement.ORAL_ETT in case.airway_management

    def test_process_row_with_emergent_asa(self, processor, default_column_map):
        """Test ASA E flag is added when emergent is true."""
        row = pd.Series(
            {
                "Date": "08/27/2025",
                "Episode ID": "12345",
                "Anesthesiologist": "Dr. Smith",
                "Age": 45.0,
                "ASA": "2",
                "Emergent": "Y",
                "Anesthesia Type": "General",
                "Procedure": "Emergency Surgery",
                "Services": "GENERAL",
                "Procedure Notes": None,
            }
        )

        case = processor.process_row(row)

        assert case.asa_physical_status == "2E"
        assert any(
            "Added 'E' to ASA status" in warning for warning in case.parsing_warnings
        )

    def test_process_row_with_multiline_services(self, processor, default_column_map):
        """Test processing multiline services field."""
        row = pd.Series(
            {
                "Date": "08/27/2025",
                "Episode ID": "12345",
                "Anesthesiologist": "Dr. Smith",
                "Age": 45.0,
                "ASA": "2",
                "Emergent": "N",
                "Anesthesia Type": "General",
                "Procedure": "Complex Surgery",
                "Services": "ORTHO\nTRAUMA",
                "Procedure Notes": None,
            }
        )

        case = processor.process_row(row)

        assert len(case.services) == 2
        assert "ORTHO" in case.services
        assert "TRAUMA" in case.services

    def test_process_row_with_missing_notes(self, processor, default_column_map):
        """Test processing row with missing procedure notes."""
        row = pd.Series(
            {
                "Date": "08/27/2025",
                "Episode ID": "12345",
                "Anesthesiologist": "Dr. Smith",
                "Age": 45.0,
                "ASA": "2",
                "Emergent": "N",
                "Anesthesia Type": "General",
                "Procedure": "Surgery",
                "Services": "GENERAL",
                "Procedure Notes": None,
            }
        )

        case = processor.process_row(row)

        assert case.confidence_score == 0.5
        assert any(
            "No procedure notes available" in warning
            for warning in case.parsing_warnings
        )

    def test_process_row_with_extractions(self, processor, default_column_map):
        """Test processing row with rich extraction data."""
        row = pd.Series(
            {
                "Date": "08/27/2025",
                "Episode ID": "12345",
                "Anesthesiologist": "Dr. Smith",
                "Age": 45.0,
                "ASA": "2",
                "Emergent": "N",
                "Anesthesia Type": "General",
                "Procedure": "Cardiac Surgery",
                "Services": "CARDIAC",
                "Procedure Notes": "Intubated with ETT. Arterial line and central line placed. TEE used.",
            }
        )

        case = processor.process_row(row)

        assert len(case.airway_management) > 0
        assert len(case.vascular_access) > 0
        assert len(case.monitoring) > 0
        assert len(case.extraction_findings) > 0
        # Average of individual extraction confidences (each is 0.5)
        assert case.confidence_score == 0.5


class TestDataFrameProcessing:
    """Test processing entire dataframes."""

    def test_process_dataframe(self, processor, default_column_map):
        """Test processing a complete dataframe."""
        df = pd.DataFrame(
            [
                {
                    "Date": "08/27/2025",
                    "Episode ID": "12345",
                    "Anesthesiologist": "Dr. Smith",
                    "Age": 45.0,
                    "ASA": "2",
                    "Emergent": "N",
                    "Anesthesia Type": "General",
                    "Procedure": "Surgery A",
                    "Services": "ORTHO",
                    "Procedure Notes": "Intubated",
                },
                {
                    "Date": "08/28/2025",
                    "Episode ID": "12346",
                    "Anesthesiologist": "Dr. Jones",
                    "Age": 65.0,
                    "ASA": "3",
                    "Emergent": "Y",
                    "Anesthesia Type": "Spinal",
                    "Procedure": "Surgery B",
                    "Services": "CARDIAC",
                    "Procedure Notes": "TEE used",
                },
            ]
        )

        cases = processor.process_dataframe(df)

        assert len(cases) == 2
        assert all(isinstance(case, ParsedCase) for case in cases)
        assert cases[0].episode_id == "12345"
        assert cases[1].episode_id == "12346"

    def test_process_dataframe_with_errors(self, processor, default_column_map):
        """Test processing dataframe with error rows."""
        df = pd.DataFrame(
            [
                {
                    "Date": "08/27/2025",
                    "Episode ID": "12345",
                    "Anesthesiologist": "Dr. Smith",
                    "Age": 45.0,
                    "ASA": "2",
                    "Emergent": "N",
                    "Anesthesia Type": "General",
                    "Procedure": "Surgery A",
                    "Services": "ORTHO",
                    "Procedure Notes": "Intubated",
                },
            ]
        )

        # Process should handle errors gracefully
        cases = processor.process_dataframe(df)

        assert len(cases) == 1

    def test_cases_to_dataframe(self, processor):
        """Test converting cases back to dataframe."""
        cases = [
            ParsedCase(
                raw_date="08/27/2025",
                episode_id="12345",
                raw_age=45.0,
                raw_asa="2",
                emergent=False,
                raw_anesthesia_type="General",
                services=["ORTHO"],
                procedure="Hip Replacement",
                procedure_notes="Intubated",
                responsible_provider="Dr. Smith",
                case_date=date(2025, 8, 27),
                age_category=AgeCategory.TWELVE_YR_TO_65_YR,
                asa_physical_status="2",
                anesthesia_type=AnesthesiaType.GENERAL,
                procedure_category=ProcedureCategory.OTHER,
            ),
        ]

        df = processor.cases_to_dataframe(cases)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "Case ID" in df.columns
        assert "Case Date" in df.columns
        assert df.iloc[0]["Case ID"] == "12345"
