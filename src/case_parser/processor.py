"""Case processor using typed intermediate representation."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
from .models import OUTPUT_COLUMNS, STANDALONE_OUTPUT_COLUMNS, ColumnMap
from .patterns.age_patterns import AGE_RANGES
from .patterns.anesthesia_patterns import (
    ANESTHESIA_MAPPING,
    MAC_WITHOUT_AIRWAY_PROCEDURE_KEYWORDS,
)
from .patterns.categorization import categorize_procedure

logger = logging.getLogger(__name__)


@dataclass
class _ParsedRowMetadata:
    """Parsed fields derived from a source row before text extraction."""

    timestamp: datetime
    age_category: AgeCategory | None
    asa_str: str
    emergent: bool
    raw_asa: Any
    anesthesia_type: AnesthesiaType | None
    services: list[str]
    procedure_category: ProcedureCategory
    procedure_text: Any


@dataclass
class _ExtractionResult:
    """Extraction results from notes/procedure text."""

    anesthesia_type: AnesthesiaType | None
    airway_management: list[Any]
    vascular_access: list[Any]
    monitoring: list[Any]


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
        """Parse date with fallback to default year.

        Args:
            value: Raw date value from the input row; may be NaN, a string,
                or a pandas Timestamp.

        Returns:
            Tuple of (parsed_datetime, warnings_list) where parsed_datetime is
            timezone-aware and warnings_list is empty on success.
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
        """Categorize age using structured age ranges.

        Args:
            age: Raw age value; expected to be numeric (years) or coercible to
                float. None or NaN values produce a warning and return None.

        Returns:
            Tuple of (age_category, warnings_list) where age_category is None
            when the value is missing or invalid.
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
        """Map anesthesia description to standardized type.

        Args:
            anesthesia_input: Raw anesthesia type value from the input row;
                matched case-insensitively against ANESTHESIA_MAPPING keywords.

        Returns:
            Tuple of (anesthesia_type, warnings_list) where anesthesia_type is
            None when the value is missing or unrecognized.
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

    def determine_procedure_category(
        self, procedure: Any, services: list[str]
    ) -> tuple[ProcedureCategory, list[str]]:
        """Determine procedure category using hybrid classification.

        Uses the configured HybridClassifier (rules + optional ML) so
        ``use_ml`` and ``ml_threshold`` affect categorization behavior.
        Falls back to rule-based ``categorize_procedure`` if hybrid output is
        unavailable or malformed.

        Args:
            procedure: Procedure description text (may be None or NaN).
            services: List of service strings from the input row.

        Returns:
            Tuple of (procedure_category, warnings_list).
        """
        procedure_text = "" if pd.isna(procedure) else str(procedure)
        hybrid_result = self.classifier.classify(procedure_text, services)
        category = hybrid_result.get("category")
        if category is None:
            return categorize_procedure(procedure, services)
        return category, hybrid_result.get("warnings", [])

    @staticmethod
    def normalize_emergent_flag(value: Any) -> bool:
        """Convert various emergent flag formats to boolean.

        Args:
            value: Raw emergent column value; accepts "E", "Y", "YES", "TRUE",
                "1" (case-insensitive) as truthy. NaN and empty values are False.

        Returns:
            True if the value indicates an emergency case, False otherwise.
        """
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
        """Infer anesthesia type from context clues when not directly mapped.

        Args:
            anesthesia_type: Already-mapped type; returned unchanged if not None.
            airway_mgmt: List of AirwayManagement findings from extraction.
            procedure_text: Raw procedure description used for MAC keyword checks.
            procedure_category: Categorized procedure type used to suppress
                defaulting for obstetric cases.

        Returns:
            Tuple of (anesthesia_type, warnings_list) with the inferred type
            and any explanatory warning messages.
        """
        if anesthesia_type is not None:
            return anesthesia_type, []

        if airway_mgmt:
            return (
                AnesthesiaType.GENERAL,
                ["Inferred general anesthesia from airway management findings"],
            )

        procedure_upper = "" if pd.isna(procedure_text) else str(procedure_text).upper()
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
        """Calculate overall extraction confidence from per-finding scores.

        Args:
            confidence_scores: List of individual confidence values from
                airway, vascular, and monitoring extraction findings.
            notes: Raw procedure notes field; used to distinguish "no notes"
                (score 0.7) from "notes present but no findings" (score 0.9).

        Returns:
            Tuple of (confidence_score, warnings_list) where confidence_score
            is the mean of per-finding scores, or a fallback value when no
            findings were recorded.
        """
        if confidence_scores:
            return sum(confidence_scores) / len(confidence_scores), []
        if pd.isna(notes) or not str(notes).strip():
            return 0.7, ["No procedure notes available for extraction"]
        return 0.9, []

    @staticmethod
    def _extend_findings(
        new_findings: list[Any],
        all_findings: list[Any],
        confidence_scores: list[float],
    ) -> None:
        """Append extraction findings and track their confidence scores."""
        all_findings.extend(new_findings)
        confidence_scores.extend(f.confidence for f in new_findings)

    @staticmethod
    def _split_services(raw_services: Any) -> list[str]:
        """Split a multiline services field into normalized items."""
        if pd.isna(raw_services):
            return []
        return [item.strip() for item in str(raw_services).split("\n") if item.strip()]

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        """Convert non-null values to string and preserve nulls as None."""
        if pd.isna(value):
            return None
        return str(value)

    @staticmethod
    def _trimmed_optional_str(value: Any, max_length: int) -> str | None:
        """Convert to string and trim to max_length, preserving nulls."""
        optional_value = CaseProcessor._optional_str(value)
        if optional_value is None:
            return None
        return optional_value[:max_length]

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        """Convert non-null values to float, preserving nulls."""
        if pd.isna(value):
            return None
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_provider_name(value: Any) -> str | None:
        """Normalize provider names when present."""
        if pd.isna(value):
            return None
        return clean_names(value)

    @staticmethod
    def _normalize_nerve_block_type(value: Any) -> str | None:
        """Normalize optional nerve block field for output."""
        if pd.isna(value):
            return None
        return str(value).strip()

    def _parse_row_metadata(
        self, row: pd.Series, all_warnings: list[str]
    ) -> _ParsedRowMetadata:
        """Parse non-extraction metadata from a source row."""
        timestamp, date_warnings = self.parse_date(row.get(self.column_map.date))
        all_warnings.extend(date_warnings)

        age_category, age_warnings = self.determine_age_category(
            row.get(self.column_map.age)
        )
        all_warnings.extend(age_warnings)

        asa_str, emergent, raw_asa = self.get_asa(all_warnings, row)
        anesthesia_type, anesthesia_warnings = self.map_anesthesia_type(
            row.get(self.column_map.final_anesthesia_type)
        )
        all_warnings.extend(anesthesia_warnings)

        services = self._split_services(row.get(self.column_map.services))
        procedure_text = row.get(self.column_map.procedure)
        procedure_category, proc_warnings = self.determine_procedure_category(
            procedure_text, services
        )
        all_warnings.extend(proc_warnings)

        return _ParsedRowMetadata(
            timestamp=timestamp,
            age_category=age_category,
            asa_str=asa_str,
            emergent=emergent,
            raw_asa=raw_asa,
            anesthesia_type=anesthesia_type,
            services=services,
            procedure_category=procedure_category,
            procedure_text=procedure_text,
        )

    def _extract_case_data(
        self,
        notes: Any,
        metadata: _ParsedRowMetadata,
        all_warnings: list[str],
        all_findings: list[Any],
        confidence_scores: list[float],
    ) -> _ExtractionResult:
        """Extract airway/vascular/monitoring findings and inferred type."""
        airway_mgmt, airway_findings = extract_airway_management(notes)
        self._extend_findings(airway_findings, all_findings, confidence_scores)

        anesthesia_type, infer_warnings = self._infer_anesthesia_type(
            metadata.anesthesia_type,
            airway_mgmt,
            metadata.procedure_text,
            metadata.procedure_category,
        )
        all_warnings.extend(infer_warnings)

        vascular_access, vascular_findings = extract_vascular_access(notes)
        self._extend_findings(vascular_findings, all_findings, confidence_scores)

        monitoring, monitoring_findings = extract_monitoring(notes)
        self._extend_findings(monitoring_findings, all_findings, confidence_scores)

        if pd.notna(metadata.procedure_text) and str(metadata.procedure_text).strip():
            procedure_monitoring, procedure_findings = extract_monitoring(
                metadata.procedure_text, source_field="procedure"
            )
            for monitor in procedure_monitoring:
                if monitor not in monitoring:
                    monitoring.append(monitor)
            self._extend_findings(procedure_findings, all_findings, confidence_scores)

        return _ExtractionResult(
            anesthesia_type=anesthesia_type,
            airway_management=airway_mgmt,
            vascular_access=vascular_access,
            monitoring=monitoring,
        )

    def process_row(self, row: pd.Series) -> ParsedCase:
        """Process a single row into a typed ParsedCase.

        Args:
            row: A single row from the input DataFrame, accessed by column
                names defined in self.column_map.

        Returns:
            ParsedCase with all extracted and categorized data, including
            warnings and a confidence score.
        """
        try:
            all_warnings: list[str] = []
            all_findings: list[Any] = []
            confidence_scores: list[float] = []

            metadata = self._parse_row_metadata(row, all_warnings)
            notes = row.get(self.column_map.procedure_notes)
            extracted = self._extract_case_data(
                notes, metadata, all_warnings, all_findings, confidence_scores
            )
            overall_confidence, conf_warnings = self._calculate_confidence(
                confidence_scores, notes
            )
            all_warnings.extend(conf_warnings)

            return ParsedCase(
                raw_date=self._optional_str(row.get(self.column_map.date)),
                episode_id=self._trimmed_optional_str(
                    row.get(self.column_map.episode_id), max_length=25
                ),
                raw_age=self._optional_float(row.get(self.column_map.age)),
                raw_asa=self._optional_str(metadata.raw_asa),
                emergent=metadata.emergent,
                raw_anesthesia_type=self._optional_str(
                    row.get(self.column_map.final_anesthesia_type)
                ),
                services=metadata.services,
                procedure=self._optional_str(metadata.procedure_text),
                procedure_notes=self._optional_str(notes),
                responsible_provider=self._clean_provider_name(
                    row.get(self.column_map.anesthesiologist)
                ),
                nerve_block_type=self._normalize_nerve_block_type(
                    row.get(self.column_map.nerve_block_type)
                ),
                case_date=metadata.timestamp.date(),
                age_category=metadata.age_category,
                asa_physical_status=metadata.asa_str,
                anesthesia_type=extracted.anesthesia_type,
                procedure_category=metadata.procedure_category,
                airway_management=extracted.airway_management,
                vascular_access=extracted.vascular_access,
                monitoring=extracted.monitoring,
                extraction_findings=all_findings,
                parsing_warnings=all_warnings,
                confidence_score=overall_confidence,
            )
        except Exception as e:
            logger.exception("Error processing row: %s", e)
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
                nerve_block_type=None,
                case_date=datetime(self.default_year, 1, 1, tzinfo=UTC).date(),
                age_category=None,
                asa_physical_status="",
                anesthesia_type=None,
                procedure_category=ProcedureCategory.OTHER,
                airway_management=[],
                vascular_access=[],
                monitoring=[],
                extraction_findings=[],
                parsing_warnings=[f"Failed to process row: {e!s}"],
                confidence_score=0.0,
            )

    def get_asa(self, all_warnings: list[str], row: pd.Series) -> tuple[str, bool, Any]:
        # Handle ASA with emergent flag
        raw_asa = row.get(self.column_map.asa)
        asa_str = "" if pd.isna(raw_asa) else str(raw_asa)
        emergent = self.normalize_emergent_flag(row.get(self.column_map.emergent))

        if emergent and "E" not in asa_str.upper():
            asa_str = f"{asa_str}E" if asa_str else "E"
            all_warnings.append("Added 'E' to ASA status based on emergent flag")
        return asa_str, emergent, raw_asa

    def _process_row_safe(self, idx: Any, row: pd.Series) -> ParsedCase:
        """Process a single row, returning an error case on failure.

        Args:
            idx: Row index used in the error log message.
            row: A single row from the input DataFrame.

        Returns:
            ParsedCase on success, or a minimal error case if processing raises.
        """
        try:
            return self.process_row(row)
        except Exception as e:
            logger.exception("Error processing row %d: %s", idx, e)
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
        """Transform input DataFrame to a list of ParsedCase objects.

        Args:
            df: Input DataFrame with columns matching self.column_map.
                Missing columns are warned about but do not halt processing.
            workers: Number of threads for parallel row processing. Defaults
                to 1 (sequential). Values > 1 use ThreadPoolExecutor.

        Returns:
            List of ParsedCase objects, one per row. Rows that raise an
            exception produce a minimal error case rather than stopping the run.
        """
        logger.info("Processing %d rows of data", len(df))
        if workers < 1:
            raise ValueError("workers must be at least 1")

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
        """Convert a list of ParsedCase objects to an output DataFrame.

        Args:
            cases: ParsedCase objects to serialize.

        Returns:
            DataFrame with columns defined by OUTPUT_COLUMNS, one row per case.
        """
        output_rows = [case.to_output_dict() for case in cases]
        df = pd.DataFrame(output_rows)
        return df[OUTPUT_COLUMNS]

    @staticmethod
    def procedures_to_dataframe(cases: list[ParsedCase]) -> pd.DataFrame:
        """Convert standalone procedure cases to a tailored output DataFrame.

        Used for MPOG ProcedureList orphans (nerve blocks, epidurals, etc.)
        that have no associated surgical case.  Produces the schema defined
        by STANDALONE_OUTPUT_COLUMNS rather than the standard case log layout.

        Args:
            cases: ParsedCase objects representing standalone procedures.

        Returns:
            DataFrame with columns defined by STANDALONE_OUTPUT_COLUMNS.
        """
        output_rows = [case.to_standalone_output_dict() for case in cases]
        df = pd.DataFrame(output_rows)
        return df.reindex(columns=STANDALONE_OUTPUT_COLUMNS)
