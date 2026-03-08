"""
Airway Management Extraction Patterns.

This file contains all regex patterns used to extract airway management techniques
from procedure notes. Each pattern list corresponds to a specific airway technique
or device.

FIELDS EXTRACTED:
- Oral/Nasal ETT (Endotracheal Tube)
- Direct Laryngoscope
- Video Laryngoscope
- Supraglottic Airway (LMA, i-gel, etc.)
- Flexible Bronchoscopic intubation
- Mask ventilation
- Difficult Airway encounters

MODIFICATION GUIDE:
To add a new pattern, simply append it to the relevant list below.
Patterns are case-insensitive and use standard Python regex syntax.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from ..domain import AirwayManagement, ExtractionFinding
from .extraction_utils import (
    calculate_pattern_confidence,
    extract_with_context,
    remove_duplicates_preserve_order,
)

# ============================================================================
# INTUBATION DETECTION
# ============================================================================
# Detects any form of endotracheal intubation
INTUBATION_PATTERNS = [
    r"\bintubat(ed|ion|e)?\b",
    r"\bETT\b",
    r"\bendotrache(al)?\b",
    r"\b(tube|ett)\s+(placed|inserted|exchanged)\b",
    r"\bnasal\s+intubat",
    r"\boral\s+intubat",
]

# Double-lumen tube / thoracic tube variants
DOUBLE_LUMEN_PATTERNS = [
    r"\bdouble[- ]lumen(\s+(tube|ett))?\b",
    r"\bDLT\b",
]

# ============================================================================
# LARYNGOSCOPY TECHNIQUES
# ============================================================================
# Direct laryngoscopy using traditional blades
DIRECT_LARYNGOSCOPY_PATTERNS = [
    r"\bdirect\s+laryngosc",
    r"\bDL\b",
    r"\bmiller\b",  # Miller blade
    r"\bmacintosh\b",  # Macintosh blade
    r"\bmac\s+\d+\b",  # Mac 3, Mac 4, etc.
]

# Video laryngoscopy using video-assisted devices
VIDEO_LARYNGOSCOPY_PATTERNS = [
    r"\bvideo\s+laryngosc",
    r"\bVL\b",
    r"\bglidescope\b",
    r"\bc-?mac\b",  # C-MAC
    r"\bmcgrath\b",  # McGrath
    r"\bking\s+vision\b",  # King Vision
]

# ============================================================================
# SUPRAGLOTTIC AIRWAYS
# ============================================================================
# LMA and similar devices that sit above the vocal cords
SUPRAGLOTTIC_PATTERNS = [
    r"\bLMA\b",
    r"\blaryngeal\s+mask\b",
    r"\bsupraglottic\b",
    r"\bi-?gel\b",  # i-gel
    r"\bair-?q\b",  # Air-Q
]

# ============================================================================
# BRONCHOSCOPY
# ============================================================================
# Flexible bronchoscopic intubation (fiberoptic)
BRONCHOSCOPY_PATTERNS = [
    r"\bbronchosc(op(y|e|ic))?\b",
    r"\bfiberoptic\b.*\bintubat",
    r"\bFOI\b",  # Fiberoptic intubation
]

# ============================================================================
# MASK VENTILATION
# ============================================================================
# Face mask ventilation (excludes LMA which is supraglottic)
MASK_VENTILATION_PATTERNS = [
    r"\bmask\b(?!.*\bLMA\b)",  # Mask but not LMA
    r"\bmask\s+vent(ilation)?\b",
    r"\bBVM\b",  # Bag-valve-mask
    r"\bbag[- ]?mask\b",
    r"\bface\s+mask\b",
]

# ============================================================================
# DIFFICULT AIRWAY
# ============================================================================
# Patterns indicating a difficult airway encounter
DIFFICULT_AIRWAY_PATTERNS = [
    r"\bdifficult\s+(airway|intubat)",
    r"\bairway\s+difficult",
    r"\bfailed\s+intubat",
    r"\bmultiple\s+attempt",
]

# ============================================================================
# NEGATION PATTERNS
# ============================================================================
# Patterns that suggest the absence of a technique (used for confidence scoring)
NEGATION_PATTERNS = [
    r"\bno\s+",
    r"\bnot\s+",
    r"\bwithout\s+",
    r"\bdenied\b",
    r"\battempted\s+but\s+not\b",
]


# ============================================================================
# EXTRACTION FUNCTION
# ============================================================================


def extract_airway_management(  # noqa: PLR0914, PLR0915
    notes: Any, source_field: str = "procedure_notes"
) -> tuple[list[AirwayManagement], list[ExtractionFinding]]:
    """
    Extract airway management techniques with pattern matching and confidence scoring.

    This function analyzes procedure notes to identify:
    - Type of intubation (oral vs nasal ETT)
    - Laryngoscopy technique (direct vs video)
    - Alternative airways (LMA, mask ventilation)
    - Special techniques (bronchoscopy)
    - Difficult airway encounters

    Args:
        notes: Procedure notes text (can be None, NaN, or string)
        source_field: Name of the field being analyzed (for tracking)

    Returns:
        Tuple of (airway_management_list, extraction_findings)
        - airway_management_list: List of AirwayManagement enums found
        - extraction_findings: List of ExtractionFinding objects with confidence scores

    Example:
        notes = "Patient intubated with video laryngoscopy"
        techniques, findings = extract_airway_management(notes)
        # techniques: [AirwayManagement.ORAL_ETT, AirwayManagement.VIDEO_LARYNGOSCOPE]
    """
    if notes is None or (isinstance(notes, float) and pd.isna(notes)):
        return [], []

    text = str(notes)
    airway_techniques = []
    findings = []
    has_nasal_route = bool(re.search(r"\bnasal\b", text, re.IGNORECASE))

    # Check for intubation
    double_lumen_matches = extract_with_context(text, DOUBLE_LUMEN_PATTERNS)
    intubation_matches = extract_with_context(text, INTUBATION_PATTERNS)
    if intubation_matches or double_lumen_matches:
        route_context = (
            intubation_matches[0][1]
            if intubation_matches
            else double_lumen_matches[0][1]
        )
        route_patterns = (
            [*INTUBATION_PATTERNS, *DOUBLE_LUMEN_PATTERNS]
            if double_lumen_matches
            else INTUBATION_PATTERNS
        )

        # Determine if nasal vs oral
        if has_nasal_route:
            airway_techniques.append(AirwayManagement.NASAL_ETT)
            confidence = calculate_pattern_confidence(
                text, route_patterns, [r"\bnasal\b"], NEGATION_PATTERNS
            )
            route_value = AirwayManagement.NASAL_ETT.value
        else:
            airway_techniques.append(AirwayManagement.ORAL_ETT)
            confidence = calculate_pattern_confidence(
                text, route_patterns, None, NEGATION_PATTERNS
            )
            route_value = AirwayManagement.ORAL_ETT.value

        findings.append(
            ExtractionFinding(
                value=route_value,
                confidence=confidence,
                context=route_context,
                source_field=source_field,
            )
        )

        if double_lumen_matches:
            airway_techniques.append(AirwayManagement.DOUBLE_LUMEN_ETT)
            confidence = calculate_pattern_confidence(
                text,
                DOUBLE_LUMEN_PATTERNS,
                [r"\bintubat(ed|ion|e)?\b", r"\bETT\b"],
                NEGATION_PATTERNS,
            )
            findings.append(
                ExtractionFinding(
                    value=AirwayManagement.DOUBLE_LUMEN_ETT.value,
                    confidence=confidence,
                    context=double_lumen_matches[0][1],
                    source_field=source_field,
                )
            )

        # Check for laryngoscopy method
        dl_matches = extract_with_context(text, DIRECT_LARYNGOSCOPY_PATTERNS)
        if dl_matches:
            airway_techniques.append(AirwayManagement.DIRECT_LARYNGOSCOPE)
            confidence = calculate_pattern_confidence(
                text, DIRECT_LARYNGOSCOPY_PATTERNS, INTUBATION_PATTERNS
            )
            findings.append(
                ExtractionFinding(
                    value=AirwayManagement.DIRECT_LARYNGOSCOPE.value,
                    confidence=confidence,
                    context=dl_matches[0][1],
                    source_field=source_field,
                )
            )

        vl_matches = extract_with_context(text, VIDEO_LARYNGOSCOPY_PATTERNS)
        if vl_matches:
            airway_techniques.append(AirwayManagement.VIDEO_LARYNGOSCOPE)
            confidence = calculate_pattern_confidence(
                text, VIDEO_LARYNGOSCOPY_PATTERNS, INTUBATION_PATTERNS
            )
            findings.append(
                ExtractionFinding(
                    value=AirwayManagement.VIDEO_LARYNGOSCOPE.value,
                    confidence=confidence,
                    context=vl_matches[0][1],
                    source_field=source_field,
                )
            )

    # Check for supraglottic airway
    sga_matches = extract_with_context(text, SUPRAGLOTTIC_PATTERNS)
    if sga_matches:
        airway_techniques.append(AirwayManagement.SUPRAGLOTTIC_AIRWAY)
        confidence = calculate_pattern_confidence(
            text, SUPRAGLOTTIC_PATTERNS, None, NEGATION_PATTERNS
        )
        findings.append(
            ExtractionFinding(
                value=AirwayManagement.SUPRAGLOTTIC_AIRWAY.value,
                confidence=confidence,
                context=sga_matches[0][1],
                source_field=source_field,
            )
        )

    # Check for bronchoscopy
    bronch_matches = extract_with_context(text, BRONCHOSCOPY_PATTERNS)
    if bronch_matches:
        airway_techniques.append(AirwayManagement.FLEXIBLE_BRONCHOSCOPIC)
        confidence = calculate_pattern_confidence(
            text, BRONCHOSCOPY_PATTERNS, INTUBATION_PATTERNS
        )
        findings.append(
            ExtractionFinding(
                value=AirwayManagement.FLEXIBLE_BRONCHOSCOPIC.value,
                confidence=confidence,
                context=bronch_matches[0][1],
                source_field=source_field,
            )
        )

    # Check for mask ventilation
    mask_matches = extract_with_context(text, MASK_VENTILATION_PATTERNS)
    if mask_matches:
        airway_techniques.append(AirwayManagement.MASK)
        confidence = calculate_pattern_confidence(
            text, MASK_VENTILATION_PATTERNS, None, NEGATION_PATTERNS
        )
        findings.append(
            ExtractionFinding(
                value=AirwayManagement.MASK.value,
                confidence=confidence,
                context=mask_matches[0][1],
                source_field=source_field,
            )
        )

    # Check for difficult airway
    difficult_matches = extract_with_context(text, DIFFICULT_AIRWAY_PATTERNS)
    if difficult_matches:
        airway_techniques.append(AirwayManagement.DIFFICULT_AIRWAY)
        confidence = calculate_pattern_confidence(text, DIFFICULT_AIRWAY_PATTERNS)
        findings.append(
            ExtractionFinding(
                value=AirwayManagement.DIFFICULT_AIRWAY.value,
                confidence=confidence,
                context=difficult_matches[0][1],
                source_field=source_field,
            )
        )

    return remove_duplicates_preserve_order(airway_techniques), findings
