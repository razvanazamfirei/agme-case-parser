"""Domain models for typed intermediate representation of parsed cases."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _strip_phi(text: str) -> str:
    """Remove [PHI] markers and normalize whitespace."""
    return " ".join(text.replace("[PHI]", "").split())


class AgeCategory(StrEnum):
    """Age category classifications for residency requirements."""

    UNDER_3_MONTHS = "a. < 3 months"
    THREE_MOS_TO_3_YR = "b. >= 3 mos. and < 3 yr."
    THREE_YR_TO_12_YR = "c. >= 3 yr. and < 12 yr."
    TWELVE_YR_TO_65_YR = "d. >= 12 yr. and < 65 yr."
    OVER_65_YR = "e. >= 65 year"


class AnesthesiaType(StrEnum):
    """Standardized anesthesia type classifications."""

    GENERAL = "GA"
    MAC = "MAC"
    SPINAL = "Spinal"
    EPIDURAL = "Epidural"
    CSE = "CSE"
    PERIPHERAL_NERVE_BLOCK = "Peripheral nerve block"


class ProcedureCategory(StrEnum):
    """Procedure category classifications."""

    CARDIAC_WITH_CPB = "Cardiac with CPB"
    CARDIAC_WITHOUT_CPB = "Cardiac without CPB"
    INTRACEREBRAL_ENDOVASCULAR = "Intracerebral (endovascular)"
    INTRACEREBRAL_VASCULAR_OPEN = "Intracerebral Vascular (open)"
    INTRACEREBRAL_NONVASCULAR_OPEN = "Intracerebral Nonvascular (open)"
    INTRATHORACIC_NON_CARDIAC = "Intrathoracic non-cardiac"
    MAJOR_VESSELS_ENDOVASCULAR = "Procedures on major vessels (endovascular)"
    MAJOR_VESSELS_OPEN = "Procedures on major vessels (open)"
    CESAREAN = "Cesarean del"
    VAGINAL_DELIVERY = "Vaginal del"
    OTHER = "Other (procedure cat)"


class AirwayManagement(StrEnum):
    """Airway management techniques."""

    ORAL_ETT = "Oral ETT"
    NASAL_ETT = "Nasal ETT"
    DOUBLE_LUMEN_ETT = "Double Lumen Tube"
    DIRECT_LARYNGOSCOPE = "Direct Laryngoscope"
    VIDEO_LARYNGOSCOPE = "Video Laryngoscope"
    SUPRAGLOTTIC_AIRWAY = "Supraglottic Airway"
    FLEXIBLE_BRONCHOSCOPIC = "Flexible Bronchoscopic"
    MASK = "Mask"
    DIFFICULT_AIRWAY = "Difficult Airway"


class AirwayTubeRoute(StrEnum):
    """Route used for an endotracheal tube when present."""

    ORAL = "Oral"
    NASAL = "Nasal"


class VascularAccess(StrEnum):
    """Specialized vascular access types."""

    ARTERIAL_CATHETER = "Arterial Catheter"
    CENTRAL_VENOUS_CATHETER = "Central Venous Catheter"
    PULMONARY_ARTERY_CATHETER = "Pulmonary Artery Catheter"


class MonitoringTechnique(StrEnum):
    """Specialized monitoring techniques."""

    TEE = "TEE"
    ELECTROPHYSIOLOGIC_MON = "Electrophysiologic mon"
    CSF_DRAIN = "CSF Drain"
    INVASIVE_NEURO_MON = "Invasive neuro mon"


class ExtractionFinding(BaseModel):
    """A single extraction finding with metadata."""

    value: str = Field(description="The extracted value")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score 0-1"
    )
    context: str | None = Field(default=None, description="Surrounding text context")
    source_field: str = Field(description="Which field this was extracted from")


class ParsedCase(BaseModel):
    """Typed intermediate representation of a parsed anesthesia case."""

    # Source data (raw/original)
    raw_date: str | None = Field(description="Original date value from input")
    episode_id: str | None = Field(description="Case episode identifier")
    raw_age: float | None = Field(description="Original age value")
    raw_asa: str | None = Field(description="Original ASA value")
    emergent: bool = Field(default=False, description="Emergency case flag")
    raw_anesthesia_type: str | None = Field(description="Original anesthesia type text")
    services: list[str] = Field(
        default_factory=list, description="Service departments (split from multiline)"
    )
    procedure: str | None = Field(description="Procedure description")
    procedure_notes: str | None = Field(description="Free-text procedure notes")
    responsible_provider: str | None = Field(description="Responsible provider name")
    nerve_block_type: str | None = Field(
        default=None, description="Nerve block type from MPOG PrimaryBlock field"
    )
    raw_nerve_block_type: str | None = Field(
        default=None,
        description="Original, unnormalized MPOG PrimaryBlock free text",
    )
    unmatched_block_source: str | None = Field(
        default=None,
        description=(
            "Original block text retained when normalization was unknown/generic"
        ),
    )

    # Parsed/categorized data
    case_date: date = Field(description="Parsed case date")
    age_category: AgeCategory | None = Field(
        default=None, description="Categorized age range"
    )
    asa_physical_status: str = Field(
        default="", description="ASA physical status (e.g., '2E', '3')"
    )
    anesthesia_type: AnesthesiaType | None = Field(
        default=None, description="Categorized anesthesia type"
    )
    procedure_category: ProcedureCategory = Field(
        default=ProcedureCategory.OTHER, description="Categorized procedure"
    )

    # Extracted findings (with type safety)
    airway_management: list[AirwayManagement] = Field(
        default_factory=list, description="Airway techniques identified"
    )
    vascular_access: list[VascularAccess] = Field(
        default_factory=list, description="Vascular access identified"
    )
    monitoring: list[MonitoringTechnique] = Field(
        default_factory=list, description="Monitoring techniques identified"
    )

    # Detailed extraction findings (for debugging/validation)
    extraction_findings: list[ExtractionFinding] = Field(
        default_factory=list, description="Detailed extraction results with context"
    )

    # Metadata and quality metrics
    parsing_warnings: list[str] = Field(
        default_factory=list, description="Warnings during parsing"
    )
    confidence_score: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Overall confidence in parsing (0-1)"
    )

    @field_validator("services", mode="before")
    @classmethod
    def split_services(cls, v: str | list[str] | None) -> list[str]:
        """Split newline-separated services into list.

        Args:
            v: The raw value from the input, which can be a string, list, or None.

        Returns:
            A list of service strings, split on newlines if the input is a string.
        """
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Split on newlines and filter empty strings
            return [s.strip() for s in v.split("\n") if s.strip()]
        return []

    def to_output_dict(self) -> dict[str, str]:
        """Convert this case to an output dictionary for DataFrame assembly.

        Enum values are serialized to their string representations. Multi-value
        fields (airway management, vascular access, monitoring) are joined with
        "; ". Absent optional fields are returned as empty strings.

        Returns:
            Dictionary keyed by output column names, with empty strings for
            absent fields.
        """
        return {
            "Case ID": self.episode_id or "",
            "Case Date": self.case_date.strftime("%m/%d/%Y"),
            "Supervisor": self.responsible_provider or "",
            "Age": self.age_category.value if self.age_category else "",
            "Original Procedure": self.procedure or "",
            "ASA Physical Status": self.asa_physical_status,
            "Anesthesia Type": self.anesthesia_type.value
            if self.anesthesia_type
            else "",
            "Airway Management": "; ".join(am.value for am in self.airway_management)
            if self.airway_management
            else "",
            "Procedure Category": self.procedure_category.value,
            "Specialized Vascular Access": "; ".join(
                va.value for va in self.vascular_access
            )
            if self.vascular_access
            else "",
            "Specialized Monitoring Techniques": "; ".join(
                mt.value for mt in self.monitoring
            )
            if self.monitoring
            else "",
        }

    def to_standalone_output_dict(self) -> dict[str, str]:
        """Convert this case to a standalone-procedure output dictionary.

        Used for MPOG ProcedureList orphans (nerve blocks, epidurals, etc.)
        that have no matching surgical case. All text fields are stripped of
        [PHI] markers before output.

        Returns:
            Dictionary keyed by STANDALONE_OUTPUT_COLUMNS, with empty strings
            for absent fields.
        """
        return {
            "Case ID": self.episode_id or "",
            "Case Date": self.case_date.strftime("%m/%d/%Y"),
            "Supervisor": _strip_phi(self.responsible_provider or ""),
            "Age": self.age_category.value
            if self.age_category
            else AgeCategory.TWELVE_YR_TO_65_YR.value,
            "Original Procedure": _strip_phi(self.procedure or ""),
            "ASA Physical Status": self.asa_physical_status,
            "Procedure Category": self.procedure_category.value,
            "Procedure Name": _strip_phi(self.raw_anesthesia_type or ""),
            "Primary Block": _strip_phi(self.nerve_block_type or ""),
            "Unmatched Primary Block (Original)": _strip_phi(
                self.unmatched_block_source or ""
            ),
        }

    def has_warnings(self) -> bool:
        """Return True if any parsing warnings were recorded for this case.

        Returns:
            True if parsing_warnings is non-empty, False otherwise.
        """
        return len(self.parsing_warnings) > 0

    @property
    def has_double_lumen_tube(self) -> bool:
        """Return True when airway findings include a double-lumen tube."""
        return AirwayManagement.DOUBLE_LUMEN_ETT in self.airway_management

    @property
    def tube_route(self) -> AirwayTubeRoute | None:
        """Return oral vs nasal route when an ETT route can be inferred."""
        if AirwayManagement.NASAL_ETT in self.airway_management:
            return AirwayTubeRoute.NASAL
        if (
            AirwayManagement.ORAL_ETT in self.airway_management
            or AirwayManagement.DOUBLE_LUMEN_ETT in self.airway_management
        ):
            return AirwayTubeRoute.ORAL
        return None

    @property
    def ga_mac_inference(self) -> AnesthesiaType | None:
        """Return GA or MAC when the anesthesia type resolves to that binary."""
        if self.anesthesia_type in {AnesthesiaType.GENERAL, AnesthesiaType.MAC}:
            return self.anesthesia_type
        return None

    def is_low_confidence(self, threshold: float = 0.7) -> bool:
        """Return True if the overall confidence score falls below threshold.

        Args:
            threshold: Minimum acceptable confidence in the range 0.0-1.0.
                Defaults to 0.7.

        Returns:
            True if confidence_score < threshold, False otherwise.
        """
        return self.confidence_score < threshold

    def get_validation_summary(self) -> dict[str, Any]:
        """Return a summary dictionary of validation issues for reporting.

        Returns:
            Dictionary with keys: case_id, has_warnings, warning_count,
            warnings, confidence_score, is_low_confidence, and missing_fields.
        """
        return {
            "case_id": self.episode_id,
            "has_warnings": self.has_warnings(),
            "warning_count": len(self.parsing_warnings),
            "warnings": self.parsing_warnings,
            "confidence_score": self.confidence_score,
            "is_low_confidence": self.is_low_confidence(),
            "missing_fields": self.get_missing_critical_fields(),
        }

    def get_missing_critical_fields(self) -> list[str]:
        """Identify critical fields that are missing or empty.

        Returns:
            List of field names (episode_id, responsible_provider, procedure,
            age_category) that are None or empty for this case.
        """
        missing = []
        if not self.episode_id:
            missing.append("episode_id")
        if not self.responsible_provider:
            missing.append("responsible_provider")
        if not self.procedure:
            missing.append("procedure")
        if not self.age_category:
            missing.append("age_category")
        return missing
