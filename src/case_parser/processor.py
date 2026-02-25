"""Case processor using typed intermediate representation."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from itertools import starmap
from typing import Any

import pandas as pd

from .domain import (
    AgeCategory,
    AnesthesiaType,
    ParsedCase,
    ProcedureCategory,
)
from .extractors import (
    clean_names,
    extract_airway_management,
    extract_monitoring,
    extract_vascular_access,
)
from .ml import get_hybrid_classifier
from .ml.hybrid import HybridClassifier
from .models import OUTPUT_COLUMNS, ColumnMap
from .patterns.age_patterns import AGE_RANGES
from .patterns.anesthesia_patterns import (
    ANESTHESIA_MAPPING,
    MAC_WITHOUT_AIRWAY_PROCEDURE_KEYWORDS,
)
from .patterns.categorization import categorize_procedure

logger = logging.getLogger(__name__)


class CaseProcessor:
    """Enhanced processor using typed intermediate representation."""

    def __init__(
        self,
        column_map: ColumnMap,
        default_year: int = 2025,
        use_ml: bool = True,
        ml_threshold: float = 0.7,
    ):
        """Initialize the processor with column mapping and default year.

        Args:
            column_map: Column mapping configuration
            default_year: Default year for date parsing
            use_ml: Whether to use ML-enhanced classification
            ml_threshold: Minimum ML confidence threshold (0.0-1.0)
        """
        self.column_map = column_map
        self.default_year = default_year

        # Initialize hybrid classifier
        if use_ml:
            self.classifier = get_hybrid_classifier(ml_threshold=ml_threshold)
        else:
            self.classifier = HybridClassifier(ml_predictor=None)

    def parse_date(self, value: Any) -> tuple[datetime, list[str]]:
        """
        Parse date with fallback to default year.

        Returns:
            Tuple of (parsed_datetime, warnings_list)
        """
        warnings = []

        if pd.isna(value):
            warnings.append(
                f"Missing date value, using default year {self.default_year}"
            )
            return (
                datetime(year=self.default_year, month=1, day=1, tzinfo=UTC),
                warnings,
            )

        # Try standard parsing first
        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.notna(timestamp):
            return timestamp.to_pydatetime(), warnings

        # Try specific format
        timestamp = pd.to_datetime(str(value), format="%m/%d/%Y", errors="coerce")
        if pd.notna(timestamp):
            return timestamp.to_pydatetime(), warnings

        # Fallback to default
        warnings.append(
            f"Could not parse date '{value}', using default year {self.default_year}"
        )
        return (
            datetime(year=self.default_year, month=1, day=1, tzinfo=UTC),
            warnings,
        )

    @staticmethod
    def determine_age_category(age: Any) -> tuple[AgeCategory | None, list[str]]:
        """
        Categorize age using structured age ranges.

        Returns:
            Tuple of (age_category, warnings_list)
        """
        warnings = []

        if age is None or (isinstance(age, float) and pd.isna(age)):
            warnings.append("Missing age value")
            return None, warnings

        try:
            age_float = float(age)
        except (ValueError, TypeError):
            warnings.append(f"Invalid age value: {age}")
            return None, warnings

        # Validate age is reasonable
        if age_float < 0 or age_float > 120:
            warnings.append(f"Age {age_float} is outside expected range (0-120)")

        # Find first range where age is below upper bound
        for range_ in AGE_RANGES:
            if age_float < range_.upper_bound:
                # Map to enum
                category_map = {
                    "a. < 3 months": AgeCategory.UNDER_3_MONTHS,
                    "b. >= 3 mos. and < 3 yr.": AgeCategory.THREE_MOS_TO_3_YR,
                    "c. >= 3 yr. and < 12 yr.": AgeCategory.THREE_YR_TO_12_YR,
                    "d. >= 12 yr. and < 65 yr.": AgeCategory.TWELVE_YR_TO_65_YR,
                    "e. >= 65 year": AgeCategory.OVER_65_YR,
                }
                return category_map.get(range_.category), warnings

        return None, warnings

    @staticmethod
    def map_anesthesia_type(
        anesthesia_input: Any,
    ) -> tuple[AnesthesiaType | None, list[str]]:
        """
        Map anesthesia description to standardized type.

        Returns:
            Tuple of (anesthesia_type, warnings_list)
        """
        warnings = []

        if anesthesia_input is None or (
            isinstance(anesthesia_input, float) and pd.isna(anesthesia_input)
        ):
            warnings.append("Missing anesthesia type")
            return None, warnings

        input_str = str(anesthesia_input).strip().upper()

        # Convert standardized string category from patterns file to enum.
        category_to_enum = {
            "GA": AnesthesiaType.GENERAL,
            "MAC": AnesthesiaType.MAC,
            "Spinal": AnesthesiaType.SPINAL,
            "Epidural": AnesthesiaType.EPIDURAL,
            "CSE": AnesthesiaType.CSE,
        }

        # Return first matching anesthesia type from pattern definitions.
        for keyword, category in ANESTHESIA_MAPPING.items():
            if keyword in input_str:
                mapped = category_to_enum.get(category)
                if mapped is not None:
                    return mapped, warnings
                warnings.append(f"Unsupported anesthesia mapping value: {category}")
                return None, warnings

        # Unrecognized type
        warnings.append(f"Unrecognized anesthesia type: {anesthesia_input}")
        return None, warnings

    @staticmethod
    def determine_procedure_category(
        procedure: Any, services: list[str]
    ) -> tuple[ProcedureCategory, list[str]]:
        """
        Determine procedure category based on services and procedure text.

        The actual categorization logic is delegated to patterns/categorization.py
        for better maintainability and clarity.

        Returns:
            Tuple of (procedure_category, warnings_list)
        """
        return categorize_procedure(procedure, services)

    @staticmethod
    def normalize_emergent_flag(value: Any) -> bool:
        """Convert various emergent flag formats to boolean."""
        if pd.isna(value):
            return False
        return str(value).strip().upper() in {"E", "Y", "YES", "TRUE", "1"}

    @staticmethod
    def _infer_anesthesia_type(
        anesthesia_type: AnesthesiaType | None,
        airway_mgmt: list,
        procedure_text: Any,
        procedure_category: ProcedureCategory,
    ) -> tuple[AnesthesiaType | None, list[str]]:
        """Infer anesthesia type from context clues when not directly mapped."""
        if anesthesia_type is not None:
            return anesthesia_type, []

        if airway_mgmt:
            return (
                AnesthesiaType.GENERAL,
                ["Inferred general anesthesia from airway management findings"],
            )

        procedure_upper = (
            "" if pd.isna(procedure_text) else str(procedure_text).upper()
        )
        if any(
            keyword in procedure_upper
            for keyword in MAC_WITHOUT_AIRWAY_PROCEDURE_KEYWORDS
        ):
            return (
                AnesthesiaType.MAC,
                ["Inferred MAC from procedure type without airway documentation"],
            )

        if procedure_category in {
            ProcedureCategory.CESAREAN,
            ProcedureCategory.VAGINAL_DELIVERY,
        }:
            return None, ["Left anesthesia type blank for obstetric procedure category"]

        return (
            AnesthesiaType.GENERAL,
            ["Defaulted anesthesia type to GA for non-obstetric case"],
        )

    @staticmethod
    def _calculate_confidence(
        confidence_scores: list[float], notes: Any
    ) -> tuple[float, list[str]]:
        """Calculate overall extraction confidence from per-finding scores."""
        if confidence_scores:
            return sum(confidence_scores) / len(confidence_scores), []
        if pd.isna(notes) or not str(notes).strip():
            return 0.7, ["No procedure notes available for extraction"]
        return 0.9, []

    def process_row(self, row: pd.Series) -> ParsedCase:  # noqa: PLR0914
        """
        Process a single row into typed ParsedCase.

        Returns:
            ParsedCase with all extracted and categorized data
        """
        all_warnings = []
        all_findings = []
        confidence_scores = []

        # Parse date
        timestamp, date_warnings = self.parse_date(row.get(self.column_map.date))
        all_warnings.extend(date_warnings)

        # Parse age
        age_category, age_warnings = self.determine_age_category(
            row.get(self.column_map.age)
        )
        all_warnings.extend(age_warnings)

        # Handle ASA with emergent flag
        raw_asa = row.get(self.column_map.asa)
        asa_str = "" if pd.isna(raw_asa) else str(raw_asa)
        emergent = self.normalize_emergent_flag(row.get(self.column_map.emergent))

        if asa_str and "E" not in asa_str.upper() and emergent:
            asa_str = f"{asa_str}E"
            all_warnings.append("Added 'E' to ASA status based on emergent flag")

        # Parse anesthesia type
        anesthesia_type, anesthesia_warnings = self.map_anesthesia_type(
            row.get(self.column_map.final_anesthesia_type)
        )
        all_warnings.extend(anesthesia_warnings)

        # Parse services (handle multiline)
        raw_services = row.get(self.column_map.services)
        services = []
        if raw_services is not None and raw_services is not pd.NA and not (
            isinstance(raw_services, float) and pd.isna(raw_services)
        ):
            services = [s.strip() for s in str(raw_services).split("\n") if s.strip()]

        # Determine procedure category
        procedure_category, proc_warnings = self.determine_procedure_category(
            row.get(self.column_map.procedure), services
        )
        all_warnings.extend(proc_warnings)

        # Extract findings from procedure notes
        notes = row.get(self.column_map.procedure_notes)
        procedure_text = row.get(self.column_map.procedure)

        airway_mgmt, airway_findings = extract_airway_management(notes)
        all_findings.extend(airway_findings)
        if airway_findings:
            confidence_scores.extend([f.confidence for f in airway_findings])

        anesthesia_type, infer_warnings = self._infer_anesthesia_type(
            anesthesia_type, airway_mgmt, procedure_text, procedure_category
        )
        all_warnings.extend(infer_warnings)

        vascular, vascular_findings = extract_vascular_access(notes)
        all_findings.extend(vascular_findings)
        if vascular_findings:
            confidence_scores.extend([f.confidence for f in vascular_findings])

        # Extract monitoring from both notes and procedure fields
        monitoring, monitoring_findings = extract_monitoring(notes)
        all_findings.extend(monitoring_findings)
        if monitoring_findings:
            confidence_scores.extend([f.confidence for f in monitoring_findings])

        # Also check procedure field for monitoring (TEE often in procedure list)
        if procedure_text:
            monitoring_proc, monitoring_proc_findings = extract_monitoring(
                procedure_text, source_field="procedure"
            )
            for mon in monitoring_proc:
                if mon not in monitoring:
                    monitoring.append(mon)
            all_findings.extend(monitoring_proc_findings)
            if monitoring_proc_findings:
                confidence_scores.extend(
                    [f.confidence for f in monitoring_proc_findings]
                )

        overall_confidence, conf_warnings = self._calculate_confidence(
            confidence_scores, notes
        )
        all_warnings.extend(conf_warnings)

        # Clean provider name
        provider = row.get(self.column_map.anesthesiologist)
        cleaned_provider = clean_names(provider) if not pd.isna(provider) else None

        # Build ParsedCase
        return ParsedCase(
            raw_date=str(row.get(self.column_map.date))
            if not pd.isna(row.get(self.column_map.date))
            else None,
            episode_id=str(row.get(self.column_map.episode_id))[:25]
            if not pd.isna(row.get(self.column_map.episode_id))
            else None,
            raw_age=float(str(row.get(self.column_map.age)))
            if not pd.isna(row.get(self.column_map.age))
            else None,
            raw_asa=str(raw_asa) if not pd.isna(raw_asa) else None,
            emergent=emergent,
            raw_anesthesia_type=str(row.get(self.column_map.final_anesthesia_type))
            if not pd.isna(row.get(self.column_map.final_anesthesia_type))
            else None,
            services=services,
            procedure=str(row.get(self.column_map.procedure))
            if not pd.isna(row.get(self.column_map.procedure))
            else None,
            procedure_notes=str(notes) if not pd.isna(notes) else None,
            responsible_provider=cleaned_provider,
            case_date=timestamp.date(),
            age_category=age_category,
            asa_physical_status=asa_str,
            anesthesia_type=anesthesia_type,
            procedure_category=procedure_category,
            airway_management=airway_mgmt,
            vascular_access=vascular,
            monitoring=monitoring,
            extraction_findings=all_findings,
            parsing_warnings=all_warnings,
            confidence_score=overall_confidence,
        )
    def _process_row_safe(self, idx: Any, row: pd.Series) -> ParsedCase:
        try:
            return self.process_row(row)
        except Exception as e:
            logger.error("Error processing row %d: %s", idx, e)
            return ParsedCase(
                raw_date=None,
                episode_id=None,
                raw_age=None,
                raw_asa=None,
                emergent=False,
                raw_anesthesia_type=None,
                services=[],
                procedure=None,
                procedure_notes=None,
                responsible_provider=None,
                case_date=datetime(self.default_year, 1, 1, tzinfo=UTC).date(),
                parsing_warnings=[f"Failed to process row: {e!s}"],
                confidence_score=0.0,
            )

    def process_dataframe(self, df: pd.DataFrame, workers: int = 1) -> list[ParsedCase]:
        """
        Transform input dataframe to list of ParsedCase objects.

        Returns:
            List of ParsedCase objects
        """
        logger.info("Processing %d rows of data", len(df))

        # Validate required columns exist
        required_columns = [
            self.column_map.date,
            self.column_map.episode_id,
            self.column_map.anesthesiologist,
            self.column_map.age,
            self.column_map.asa,
            self.column_map.final_anesthesia_type,
            self.column_map.procedure,
            self.column_map.services,
        ]

        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.warning("Missing columns in input data: %s", missing_columns)

        indexed_rows = list(df.iterrows())
        processed_cases: list[ParsedCase] = []
        if workers == 1:
            processed_cases = list(starmap(self._process_row_safe, indexed_rows))
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(self._process_row_safe, idx, row)
                    for idx, row in indexed_rows
                ]
                processed_cases = [f.result() for f in futures]

        logger.info("Successfully processed %d cases", len(processed_cases))
        return processed_cases

    @staticmethod
    def cases_to_dataframe(cases: list[ParsedCase]) -> pd.DataFrame:
        """Convert list of ParsedCase objects to output DataFrame."""
        output_rows = [case.to_output_dict() for case in cases]
        df = pd.DataFrame(output_rows)
        return df[OUTPUT_COLUMNS]
