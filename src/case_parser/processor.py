"""Case processor using typed intermediate representation."""

from __future__ import annotations

import logging
import math
import multiprocessing as mp
import threading
from collections.abc import Hashable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import chain, starmap
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
from .ml.config import DEFAULT_ML_THRESHOLD
from .ml.hybrid import HybridClassifier
from .models import OUTPUT_COLUMNS, STANDALONE_OUTPUT_COLUMNS, ColumnMap
from .patterns.age_patterns import AGE_RANGES
from .patterns.anesthesia_patterns import (
    ANESTHESIA_MAPPING,
    GA_NOTE_KEYWORDS,
    MAC_NOTE_KEYWORDS,
    MAC_WITHOUT_AIRWAY_PROCEDURE_KEYWORDS,
)
from .patterns.block_site_patterns import (
    NEURAXIAL_BLOCK_SITE_TERMS,
    PERIPHERAL_BLOCK_SITE_TERMS,
    normalize_block_site_terms,
)
from .patterns.categorization import categorize_procedure

logger = logging.getLogger(__name__)
_CANONICAL_BLOCK_SITE_TERMS = {
    *PERIPHERAL_BLOCK_SITE_TERMS,
    *NEURAXIAL_BLOCK_SITE_TERMS,
}
_GENERIC_PERIPHERAL_BLOCK_SITE = "Other - peripheral nerve blockade site"
_PROCESS_POOL_MIN_ROWS = 25_000
_PROCESS_POOL_TARGET_CHUNK_ROWS = 12_500
_PROCESS_CHUNK_LOCK = threading.Lock()
_PROCESS_CHUNK_STATE: dict[str, Any] = {
    "df": None,
    "processor": None,
}


def _get_process_pool_context() -> mp.context.BaseContext | None:
    """Return a fork-based context when the runtime supports it."""
    try:
        return mp.get_context("fork")
    except ValueError:
        return None


def _init_process_chunk_worker(
    column_map: ColumnMap,
    default_year: int,
    use_ml: bool,
    ml_threshold: float,
) -> None:
    """Initialize one CaseProcessor per process-pool worker."""
    _PROCESS_CHUNK_STATE["processor"] = CaseProcessor(
        column_map,
        default_year=default_year,
        use_ml=use_ml,
        ml_threshold=ml_threshold,
    )


def _process_dataframe_chunk(span: tuple[int, int]) -> list[ParsedCase]:
    """Process one dataframe span using inherited forked state."""
    dataframe = _PROCESS_CHUNK_STATE["df"]
    processor = _PROCESS_CHUNK_STATE["processor"]
    if dataframe is None:
        raise RuntimeError("process chunk dataframe was not initialized")
    if processor is None:
        raise RuntimeError("process chunk worker processor was not initialized")

    start, end = span
    chunk = dataframe.iloc[start:end].reset_index(drop=True)
    return processor.process_dataframe(chunk, workers=1)


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


@dataclass
class _PreparedRow:
    """Precomputed row inputs shared across row processing."""

    timestamp: datetime
    date_warnings: list[str]
    services: list[str]
    procedure_category: ProcedureCategory
    procedure_warnings: list[str]


class CaseProcessor:
    """Enhanced processor using typed intermediate representation."""

    def __init__(
        self,
        column_map: ColumnMap,
        default_year: int = 2025,
        use_ml: bool = True,
        ml_threshold: float = DEFAULT_ML_THRESHOLD,
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
        self._use_ml = use_ml
        self._ml_threshold = ml_threshold

        # Initialize hybrid classifier
        if use_ml:
            self.classifier = get_hybrid_classifier(ml_threshold=ml_threshold)
        else:
            self.classifier = HybridClassifier(ml_predictor=None)

    @property
    def _default_timestamp(self) -> datetime:
        """Return the fallback datetime used when parsing fails."""
        return datetime(year=self.default_year, month=1, day=1, tzinfo=UTC)

    @staticmethod
    def _normalize_timestamp_to_utc(value: pd.Timestamp | datetime) -> datetime:
        """Return a consistently UTC-aware datetime from parsed timestamp values."""
        timestamp = value.to_pydatetime() if isinstance(value, pd.Timestamp) else value
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)

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
            return self._default_timestamp, warnings

        # Try standard parsing first
        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.notna(timestamp):
            return self._normalize_timestamp_to_utc(timestamp), warnings

        # Try specific format
        timestamp = pd.to_datetime(str(value), format="%m/%d/%Y", errors="coerce")
        if pd.notna(timestamp):
            return self._normalize_timestamp_to_utc(timestamp), warnings

        # Fallback to default
        warnings.append(
            f"Could not parse date '{value}', using default year {self.default_year}"
        )
        return self._default_timestamp, warnings

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
    def _infer_anesthesia_type(  # noqa: PLR0911
        anesthesia_type: AnesthesiaType | None,
        airway_mgmt: list,
        procedure_text: Any,
        procedure_category: ProcedureCategory,
        notes: Any,
    ) -> tuple[AnesthesiaType | None, list[str]]:
        """Infer anesthesia type from context clues when not directly mapped.

        Args:
            anesthesia_type: Already-mapped type; returned unchanged if not None.
            airway_mgmt: List of AirwayManagement findings from extraction.
            procedure_text: Raw procedure description used for MAC keyword checks.
            procedure_category: Categorized procedure type used to suppress
                defaulting for obstetric cases.
            notes: Free-text procedure or airway notes used for GA/MAC clues.

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
        notes_upper = "" if pd.isna(notes) else str(notes).upper()
        if any(keyword in notes_upper for keyword in MAC_NOTE_KEYWORDS):
            return (
                AnesthesiaType.MAC,
                ["Inferred MAC from note text without airway documentation"],
            )

        if any(keyword in notes_upper for keyword in GA_NOTE_KEYWORDS):
            return (
                AnesthesiaType.GENERAL,
                ["Inferred general anesthesia from note text"],
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
    def _normalize_nerve_block_type(
        value: Any, procedure_name: Any, procedure_notes: Any
    ) -> str | None:
        """Normalize optional nerve-block text to canonical site term(s)."""
        return normalize_block_site_terms(
            CaseProcessor._optional_str(value),
            procedure_name=CaseProcessor._optional_str(procedure_name),
            procedure_notes=CaseProcessor._optional_str(procedure_notes),
        )

    @staticmethod
    def _derive_unmatched_block_source(
        raw_block_type: str | None, normalized_block_type: str | None
    ) -> str | None:
        """Return original block text when normalization was unknown/generic."""
        if raw_block_type is None:
            return None
        if normalized_block_type is None:
            return raw_block_type

        normalized_terms = {
            term.strip() for term in normalized_block_type.split(";") if term.strip()
        }
        if not normalized_terms:
            return raw_block_type

        # Keep original text for generic or unknown mappings to aid pattern tuning.
        if _GENERIC_PERIPHERAL_BLOCK_SITE in normalized_terms:
            return raw_block_type
        if not normalized_terms.issubset(_CANONICAL_BLOCK_SITE_TERMS):
            return raw_block_type

        return None

    def _build_error_case(self, message: str) -> ParsedCase:
        """Create a minimal ParsedCase used for row-level failures."""
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
            raw_nerve_block_type=None,
            unmatched_block_source=None,
            case_date=datetime(self.default_year, 1, 1, tzinfo=UTC).date(),
            parsing_warnings=[message],
            confidence_score=0.0,
        )

    def _parse_row_metadata(
        self,
        row: Mapping[Hashable, Any],
        all_warnings: list[str],
        prepared: _PreparedRow | None = None,
    ) -> _ParsedRowMetadata:
        """Parse non-extraction metadata from a source row.

        Reuses precomputed date/service/category data when ``prepared`` is
        supplied; otherwise performs the per-row parsing work directly.
        """
        if prepared is not None:
            timestamp = prepared.timestamp
            all_warnings.extend(prepared.date_warnings)
        else:
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

        services = (
            prepared.services
            if prepared is not None
            else self._split_services(row.get(self.column_map.services))
        )
        procedure_text = row.get(self.column_map.procedure)
        procedure_category, proc_warnings = (
            (prepared.procedure_category, prepared.procedure_warnings)
            if prepared is not None
            else self.determine_procedure_category(procedure_text, services)
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
        """Extract findings from notes/procedure text and infer anesthesia type.

        Monitoring extraction runs on both free-text notes and the procedure
        text so technique signals present only in the scheduled procedure are
        still captured.
        """
        airway_mgmt, airway_findings = extract_airway_management(notes)
        self._extend_findings(airway_findings, all_findings, confidence_scores)

        anesthesia_type, infer_warnings = self._infer_anesthesia_type(
            metadata.anesthesia_type,
            airway_mgmt,
            metadata.procedure_text,
            metadata.procedure_category,
            notes,
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

    def process_row(
        self,
        row: Mapping[Hashable, Any],
        prepared: _PreparedRow | None = None,
    ) -> ParsedCase:
        """Process a single row into a typed ParsedCase.

        Args:
            row: A single row from the input DataFrame, accessed by column
                names defined in self.column_map.
            prepared: Optional precomputed date/service/category metadata for
                this row, typically supplied by batch processing.

        Returns:
            ParsedCase with all extracted and categorized data, including
            warnings and a confidence score.
        """
        try:
            all_warnings: list[str] = []
            all_findings: list[Any] = []
            confidence_scores: list[float] = []

            metadata = self._parse_row_metadata(row, all_warnings, prepared=prepared)
            notes = row.get(self.column_map.procedure_notes)
            extracted = self._extract_case_data(
                notes, metadata, all_warnings, all_findings, confidence_scores
            )
            overall_confidence, conf_warnings = self._calculate_confidence(
                confidence_scores, notes
            )
            all_warnings.extend(conf_warnings)
            raw_nerve_block_type = self._optional_str(
                row.get(self.column_map.nerve_block_type)
            )
            normalized_nerve_block_type = self._normalize_nerve_block_type(
                raw_nerve_block_type,
                row.get(self.column_map.final_anesthesia_type),
                notes,
            )

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
                nerve_block_type=normalized_nerve_block_type,
                raw_nerve_block_type=raw_nerve_block_type,
                unmatched_block_source=self._derive_unmatched_block_source(
                    raw_nerve_block_type,
                    normalized_nerve_block_type,
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
            return self._build_error_case(f"Failed to process row: {e!s}")

    def get_asa(
        self, all_warnings: list[str], row: Mapping[Hashable, Any]
    ) -> tuple[str, bool, Any]:
        """Return ASA text, normalized emergent flag, and original ASA value."""
        # Handle ASA with emergent flag
        raw_asa = row.get(self.column_map.asa)
        asa_str = "" if pd.isna(raw_asa) else str(raw_asa)
        emergent = self.normalize_emergent_flag(row.get(self.column_map.emergent))

        if emergent and "E" not in asa_str.upper():
            asa_str = f"{asa_str}E" if asa_str else "E"
            all_warnings.append("Added 'E' to ASA status based on emergent flag")
        return asa_str, emergent, raw_asa

    def _process_row_safe(
        self,
        idx: Any,
        row: Mapping[Hashable, Any],
        prepared: _PreparedRow | None = None,
    ) -> ParsedCase:
        """Process a single row, returning an error case on failure.

        Args:
            idx: Row index used in the error log message.
            row: A single row from the input DataFrame.

        Returns:
            ParsedCase on success, or a minimal error case if processing raises.
        """
        try:
            return self.process_row(row, prepared=prepared)
        except Exception as e:
            logger.exception("Error processing row %d: %s", idx, e)
            return self._build_error_case(f"Failed to process row: {e!s}")

    def _prepare_rows(
        self, rows: Sequence[Mapping[Hashable, Any]]
    ) -> list[_PreparedRow]:
        """Precompute per-row metadata for a dataframe batch.

        This batches date parsing and hybrid categorization so downstream
        row-processing can reuse normalized timestamps, services, categories,
        and warning lists.
        """
        date_preparations = self._prepare_dates([
            row.get(self.column_map.date) for row in rows
        ])
        services_list = [
            self._split_services(row.get(self.column_map.services)) for row in rows
        ]
        procedure_texts = [
            ""
            if pd.isna(row.get(self.column_map.procedure))
            else str(row.get(self.column_map.procedure))
            for row in rows
        ]
        classifications = self.classifier.classify_many(procedure_texts, services_list)
        return [
            _PreparedRow(
                timestamp=timestamp,
                date_warnings=date_warnings,
                services=services,
                procedure_category=classification["category"],
                procedure_warnings=list(classification.get("warnings", [])),
            )
            for (timestamp, date_warnings), services, classification in zip(
                date_preparations,
                services_list,
                classifications,
                strict=True,
            )
        ]

    def _prepare_dates(self, values: list[Any]) -> list[tuple[datetime, list[str]]]:
        """Parse many dates at once while preserving row-level warnings.

        Successful parses are normalized to UTC-aware datetimes so batched
        rows use the same timestamp contract as single-row ``parse_date()``.
        """
        if not values:
            return []

        series = pd.Series(values, dtype="object")
        missing_mask = series.isna()
        parsed = pd.to_datetime(series, errors="coerce")

        unparsed_mask = (~missing_mask) & parsed.isna()
        if unparsed_mask.any():
            parsed.loc[unparsed_mask] = pd.to_datetime(
                series.loc[unparsed_mask].astype(str),
                format="%m/%d/%Y",
                errors="coerce",
            )

        prepared_dates: list[tuple[datetime, list[str]]] = []
        parsed_values = parsed.tolist()
        missing_values = missing_mask.tolist()
        default_timestamp = self._default_timestamp
        for value, is_missing, timestamp in zip(
            values,
            missing_values,
            parsed_values,
            strict=False,
        ):
            if is_missing:
                prepared_dates.append((
                    default_timestamp,
                    [f"Missing date value, using default year {self.default_year}"],
                ))
                continue

            if pd.notna(timestamp):
                prepared_dates.append((self._normalize_timestamp_to_utc(timestamp), []))
                continue

            prepared_dates.append((
                default_timestamp,
                [
                    f"Could not parse date '{value}', "
                    f"using default year {self.default_year}"
                ],
            ))

        return prepared_dates

    def _should_use_process_pool(self, row_count: int, workers: int) -> bool:
        """Return whether large-batch process chunking is worth attempting."""
        return (
            workers > 1
            and row_count >= _PROCESS_POOL_MIN_ROWS
            and self.classifier.ml_predictor is not None
            and _get_process_pool_context() is not None
        )

    @staticmethod
    def _build_chunk_spans(row_count: int) -> list[tuple[int, int]]:
        """Split a large dataframe into balanced process-pool chunk spans."""
        if row_count <= 0:
            return []

        chunk_count = max(
            1,
            math.ceil(row_count / _PROCESS_POOL_TARGET_CHUNK_ROWS),
        )
        chunk_size = math.ceil(row_count / chunk_count)
        return [
            (start, min(start + chunk_size, row_count))
            for start in range(0, row_count, chunk_size)
        ]

    def _process_rows_in_process_chunks(
        self,
        df: pd.DataFrame,
        workers: int,
    ) -> list[ParsedCase]:
        """Process a large ML-heavy dataframe through forked dataframe chunks.

        This path is used only when large-batch heuristics indicate that the
        process-pool startup cost is likely to be worthwhile.
        """
        context = _get_process_pool_context()
        if context is None:
            raise RuntimeError("fork-based process pools are not available")

        chunk_spans = self._build_chunk_spans(len(df))
        if not chunk_spans:
            return []

        if not _PROCESS_CHUNK_LOCK.acquire(blocking=False):
            raise RuntimeError("process chunk state is already in use")

        try:
            _PROCESS_CHUNK_STATE["df"] = df
            _PROCESS_CHUNK_STATE["processor"] = None
            try:
                with ProcessPoolExecutor(
                    max_workers=min(workers, len(chunk_spans)),
                    mp_context=context,
                    initializer=_init_process_chunk_worker,
                    initargs=(
                        self.column_map,
                        self.default_year,
                        self._use_ml,
                        self._ml_threshold,
                    ),
                ) as executor:
                    chunk_results = list(
                        executor.map(_process_dataframe_chunk, chunk_spans)
                    )
            finally:
                _PROCESS_CHUNK_STATE["df"] = None
                _PROCESS_CHUNK_STATE["processor"] = None
        finally:
            _PROCESS_CHUNK_LOCK.release()

        return list(chain.from_iterable(chunk_results))

    def process_dataframe(self, df: pd.DataFrame, workers: int = 1) -> list[ParsedCase]:
        """Transform input DataFrame to a list of ParsedCase objects.

        Args:
            df: Input DataFrame with columns matching self.column_map.
                Missing columns are warned about but do not halt processing.
            workers: Number of worker slots for parallel processing. Defaults
                to 1 (sequential). Large ML-heavy batches may use process
                chunks; smaller batches otherwise stay in-process and use row
                threads when workers > 1.

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

        if self._should_use_process_pool(len(df), workers):
            try:
                processed_cases = self._process_rows_in_process_chunks(df, workers)
            except Exception as e:
                logger.exception(
                    "Process chunk execution failed; "
                    "falling back to in-process row handling: %s",
                    e,
                )
            else:
                logger.info("Successfully processed %d cases", len(processed_cases))
                return processed_cases

        rows = df.to_dict(orient="records")
        try:
            prepared_rows: list[_PreparedRow | None] = [
                *self._prepare_rows(rows)
            ]
        except Exception as e:
            logger.exception(
                "Batch row preparation failed; falling back to per-row processing: %s",
                e,
            )
            prepared_rows = [None for _ in rows]
        processed_cases: list[ParsedCase] = []
        if workers == 1:
            indexed_rows = zip(
                range(len(rows)),
                rows,
                prepared_rows,
                strict=False,
            )
            processed_cases = list(starmap(self._process_row_safe, indexed_rows))
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                processed_cases = list(
                    executor.map(
                        self._process_row_safe,
                        range(len(rows)),
                        rows,
                        prepared_rows,
                    )
                )

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
