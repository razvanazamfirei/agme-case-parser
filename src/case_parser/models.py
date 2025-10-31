"""Data models and configuration for the case parser."""

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


@dataclass(frozen=True)
class AgeRange:
    """Age range with upper bound and category label."""

    upper_bound: float
    category: str


@dataclass(frozen=True)
class ProcedureRule:
    """Rule for categorizing procedures based on service keywords."""

    keywords: tuple[str, ...]
    category: str
    exclude_keywords: tuple[str, ...] = ()


# Default age ranges for categorization
AGE_RANGES = [
    AgeRange(0.25, "a. < 3 months"),
    AgeRange(3, "b. >= 3 mos. and < 3 yr."),
    AgeRange(12, "c. >= 3 yr. and < 12 yr."),
    AgeRange(65, "d. >= 12 yr. and < 65 yr."),
    AgeRange(float("inf"), "e. >= 65 year"),
]

# Anesthesia type mapping
ANESTHESIA_MAPPING = {
    "CSE": "CSE",
    "EPIDURAL": "Epidural",
    "SPINAL": "Spinal",
    "BLOCK": "Peripheral nerve block",
    "PNB": "Peripheral nerve block",
    "MAC": "MAC",
    "SEDATION": "MAC",
    "GENERAL": "GA",
    "ENDOTRACHEAL": "GA",
}

# Procedure categorization rules in priority order
PROCEDURE_RULES = [
    ProcedureRule(("CARDIAC",), "Cardiac"),
    ProcedureRule(("NEURO",), "Intracerebral"),
    ProcedureRule(("THOR",), "Intrathoracic non-cardiac", exclude_keywords=("CARD",)),
    ProcedureRule(("VASC",), "Procedures Major Vessels"),
    ProcedureRule(("TRANSPLANT",), "Other (procedure cat)"),
    # Special case for OB/GYN - handled separately due to procedure-dependent logic
]

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

