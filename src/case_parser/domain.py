"""Domain models for typed intermediate representation of parsed cases."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


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

    CARDIAC = "Cardiac"
    INTRACEREBRAL = "Intracerebral"
    INTRATHORACIC_NON_CARDIAC = "Intrathoracic non-cardiac"
    MAJOR_VESSELS = "Procedures Major Vessels"
    CESAREAN = "Cesarean del"
    OTHER = "Other (procedure cat)"


class AirwayManagement(StrEnum):
    """Airway management techniques."""

    ORAL_ETT = "Oral ETT"
    NASAL_ETT = "Nasal ETT"
    DIRECT_LARYNGOSCOPE = "Direct Laryngoscope"
    VIDEO_LARYNGOSCOPE = "Video Laryngoscope"
    SUPRAGLOTTIC_AIRWAY = "Supraglottic Airway"
    FLEXIBLE_BRONCHOSCOPIC = "Flexible Bronchoscopic"
    MASK = "Mask"
    DIFFICULT_AIRWAY = "Difficult Airway"


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
        """Split newline-separated services into list."""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Split on newlines and filter empty strings
            return [s.strip() for s in v.split("\n") if s.strip()]
        return []

    def to_output_dict(self) -> dict[str, str]:
        """Convert to Excel output format matching expected columns."""
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

    def to_json_dict(
        self, include_metadata: bool = True, include_raw: bool = False
    ) -> dict[str, Any]:
        """
        Convert to JSON format for Chrome extension consumption.

        Args:
            include_metadata: Include parsing warnings, confidence scores, etc.
            include_raw: Include raw/original field values for debugging

        Returns:
            Dictionary suitable for JSON serialization
        """
        data: dict[str, Any] = {
            "episode_id": self.episode_id,
            "case_date": self.case_date.isoformat(),
            "responsible_provider": self.responsible_provider,
            "age_category": self.age_category.value if self.age_category else None,
            "procedure": self.procedure,
            "asa_physical_status": self.asa_physical_status,
            "anesthesia_type": self.anesthesia_type.value if self.anesthesia_type else None,
            "procedure_category": self.procedure_category.value,
            "emergent": self.emergent,
            # Lists exported as arrays for easier Chrome extension processing
            "airway_management": [am.value for am in self.airway_management],
            "vascular_access": [va.value for va in self.vascular_access],
            "monitoring": [mt.value for mt in self.monitoring],
            "services": self.services,
        }

        # Include raw values if requested (useful for debugging/form validation)
        if include_raw:
            data["raw"] = {
                "date": self.raw_date,
                "age": self.raw_age,
                "asa": self.raw_asa,
                "anesthesia_type": self.raw_anesthesia_type,
            }
            data["procedure_notes"] = self.procedure_notes

        # Include metadata if requested
        if include_metadata:
            data["metadata"] = {
                "confidence_score": self.confidence_score,
                "has_warnings": self.has_warnings(),
                "warning_count": len(self.parsing_warnings),
                "warnings": self.parsing_warnings,
            }
            if self.extraction_findings:
                data["metadata"]["extraction_findings"] = [
                    {
                        "value": f.value,
                        "confidence": f.confidence,
                        "context": f.context,
                        "source_field": f.source_field,
                    }
                    for f in self.extraction_findings
                ]

        return data

    def has_warnings(self) -> bool:
        """Check if this case has any parsing warnings."""
        return len(self.parsing_warnings) > 0

    def is_low_confidence(self, threshold: float = 0.7) -> bool:
        """Check if confidence is below threshold."""
        return self.confidence_score < threshold

    def get_validation_summary(self) -> dict[str, Any]:
        """Get summary of validation issues for reporting."""
        return {
            "case_id": self.episode_id,
            "has_warnings": self.has_warnings(),
            "warning_count": len(self.parsing_warnings),
            "warnings": self.parsing_warnings,
            "confidence_score": self.confidence_score,
            "is_low_confidence": self.is_low_confidence(),
            "missing_fields": self._get_missing_critical_fields(),
        }

    def _get_missing_critical_fields(self) -> list[str]:
        """Identify critical fields that are missing or empty."""
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
