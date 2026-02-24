"""Data models and configuration for the case parser.

NOTE: Business rules (age ranges, anesthesia mappings, procedure rules) have been
moved to the patterns/ directory for easier modification. Import them from there:
- patterns.age_patterns.AGE_RANGES
- patterns.anesthesia_patterns.ANESTHESIA_MAPPING
- patterns.procedure_patterns.PROCEDURE_RULES
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnMap:
    """Column mapping configuration for input Excel files."""

    date: str = "Date"
    episode_id: str = "Episode ID"
    anesthesiologist: str = "Responsible Provider"
    age: str = "Age At Encounter"
    emergent: str = "Emergent"  # optional; used to append E to ASA if present
    asa: str = "ASA"
    final_anesthesia_type: str = "Final Anesthesia Type"
    procedure_notes: str = "Procedure Notes"
    procedure: str = "Procedure"
    services: str = "Services"


# Invasiveness ranking for MPOG ProcedureName values (higher = more invasive/complex).
# Used to select the primary anesthesia technique when a case has multiple procedures.
TECHNIQUE_RANK: dict[str, int] = {
    "Intubation complex": 6,
    "Intubation routine": 5,
    "Spinal": 4,
    "Epidural": 3,
    "LMA": 2,
    "Peripheral nerve block": 1,
}


# Output column order
OUTPUT_COLUMNS = [
    "Case ID",
    "Case Date",
    "Supervisor",
    "Age",
    "Original Procedure",
    "ASA Physical Status",
    "Anesthesia Type",
    "Airway Management",
    "Procedure Category",
    "Specialized Vascular Access",
    "Specialized Monitoring Techniques",
]
