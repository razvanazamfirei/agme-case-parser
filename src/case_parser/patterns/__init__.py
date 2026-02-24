"""
Pattern definitions and extraction functions for case parsing.

This module organizes all pattern-based extraction logic by field category.
Each category has its own module containing:
- Pattern definitions (regex lists)
- Extraction function
- Documentation and examples

PATTERN MODULES:
- airway_patterns: Airway management extraction (ETT, LMA, laryngoscopy, etc.)
- vascular_patterns: Vascular access extraction (arterial lines, CVCs, PACs)
- monitoring_patterns: Specialized monitoring (TEE, neuromonitoring, CSF drains)
- procedure_patterns: Procedure categorization rules
- approach_patterns: Surgical approach detection (endovascular vs open)
- age_patterns: Age range categorization
- anesthesia_patterns: Anesthesia type mapping
"""

from .age_patterns import AGE_RANGES
from .airway_patterns import (
    BRONCHOSCOPY_PATTERNS,
    DIFFICULT_AIRWAY_PATTERNS,
    DIRECT_LARYNGOSCOPY_PATTERNS,
    INTUBATION_PATTERNS,
    MASK_VENTILATION_PATTERNS,
    NEGATION_PATTERNS,
    SUPRAGLOTTIC_PATTERNS,
    VIDEO_LARYNGOSCOPY_PATTERNS,
    extract_airway_management,
)
from .anesthesia_patterns import (
    ANESTHESIA_MAPPING,
    MAC_WITHOUT_AIRWAY_PROCEDURE_KEYWORDS,
)
from .approach_patterns import (
    ENDOVASCULAR_KEYWORDS,
    NONVASCULAR_PATHOLOGY_KEYWORDS,
    OPEN_KEYWORDS,
    VASCULAR_PATHOLOGY_KEYWORDS,
    detect_approach,
    detect_intracerebral_pathology,
)
from .categorization import categorize_procedure
from .monitoring_patterns import (
    CSF_DRAIN_PATTERNS,
    ELECTROPHYSIOLOGIC_PATTERNS,
    INVASIVE_NEURO_PATTERNS,
    TEE_PATTERNS,
    extract_monitoring,
)
from .procedure_patterns import PROCEDURE_RULES
from .vascular_access_patterns import (
    ARTERIAL_LINE_PATTERNS,
    CENTRAL_LINE_PATTERNS,
    PA_CATHETER_PATTERNS,
    extract_vascular_access,
)

__all__ = [
    "AGE_RANGES",
    "ANESTHESIA_MAPPING",
    "ARTERIAL_LINE_PATTERNS",
    "BRONCHOSCOPY_PATTERNS",
    "CENTRAL_LINE_PATTERNS",
    "CSF_DRAIN_PATTERNS",
    "DIFFICULT_AIRWAY_PATTERNS",
    "DIRECT_LARYNGOSCOPY_PATTERNS",
    "ELECTROPHYSIOLOGIC_PATTERNS",
    "ENDOVASCULAR_KEYWORDS",
    "INTUBATION_PATTERNS",
    "INVASIVE_NEURO_PATTERNS",
    "MAC_WITHOUT_AIRWAY_PROCEDURE_KEYWORDS",
    "MASK_VENTILATION_PATTERNS",
    "NEGATION_PATTERNS",
    "NONVASCULAR_PATHOLOGY_KEYWORDS",
    "OPEN_KEYWORDS",
    "PA_CATHETER_PATTERNS",
    "PROCEDURE_RULES",
    "SUPRAGLOTTIC_PATTERNS",
    "TEE_PATTERNS",
    "VASCULAR_PATHOLOGY_KEYWORDS",
    "VIDEO_LARYNGOSCOPY_PATTERNS",
    "categorize_procedure",
    "detect_approach",
    "detect_intracerebral_pathology",
    "extract_airway_management",
    "extract_monitoring",
    "extract_vascular_access",
]
