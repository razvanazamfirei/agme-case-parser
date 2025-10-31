"""Enhanced text extraction with improved patterns and confidence scoring."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .domain import (
    AirwayManagement,
    ExtractionFinding,
    MonitoringTechnique,
    VascularAccess,
)


def _extract_with_context(
    text: str, patterns: list[str], context_window: int = 50
) -> list[tuple[str, str, int]]:
    """
    Extract matches with surrounding context.

    Returns:
        List of (matched_text, context, position) tuples
    """
    findings = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - context_window)
            end = min(len(text), match.end() + context_window)
            context = text[start:end].strip()
            findings.append((match.group(), context, match.start()))
    return findings


def _calculate_pattern_confidence(
    text: str,
    primary_patterns: list[str],
    supporting_patterns: list[str] | None = None,
    negation_patterns: list[str] | None = None,
) -> float:
    """
    Calculate confidence score based on pattern matches.

    Args:
        text: Text to analyze
        primary_patterns: Main patterns that must match
        supporting_patterns: Optional patterns that increase confidence
        negation_patterns: Patterns that decrease confidence (e.g., "no intubation")

    Returns:
        Confidence score between 0 and 1
    """
    confidence = 0.5  # Base confidence if primary pattern matches

    # Check for supporting evidence
    if supporting_patterns:
        supporting_matches = sum(
            1
            for pattern in supporting_patterns
            if re.search(pattern, text, re.IGNORECASE)
        )
        # Each supporting pattern adds 0.1, max 0.4
        confidence += min(supporting_matches * 0.1, 0.4)

    # Check for negations
    if negation_patterns:
        negation_matches = sum(
            1
            for pattern in negation_patterns
            if re.search(pattern, text, re.IGNORECASE)
        )
        # Each negation reduces confidence by 0.3
        confidence -= negation_matches * 0.3

    return max(0.0, min(1.0, confidence))


def clean_names(name: str) -> str:
    """Clean and standardize provider names."""
    if pd.isna(name):
        return ""
    name = str(name).strip()
    # Remove titles
    name = re.sub(r"\b(MD|DO|PhD|CRNA|RN)\b", "", name, flags=re.IGNORECASE).strip()
    # Remove trailing commas and extra whitespace
    name = re.sub(r",\s*$", "", name).strip()
    return re.sub(r"\s+", " ", name)


# Enhanced pattern definitions
INTUBATION_PATTERNS = [
    r"\bintubat(ed|ion|e)?\b",
    r"\bETT\b",
    r"\bendotrache(al)?\b",
    r"\b(tube|ett)\s+(placed|inserted|exchanged)\b",
    r"\bnasal\s+intubat",
    r"\boral\s+intubat",
]

DIRECT_LARYNGOSCOPY_PATTERNS = [
    r"\bdirect\s+laryngosc",
    r"\bDL\b",
    r"\bmiller\b",
    r"\bmacintosh\b",
    r"\bmac\s+\d+\b",
]

VIDEO_LARYNGOSCOPY_PATTERNS = [
    r"\bvideo\s+laryngosc",
    r"\bVL\b",
    r"\bglidescope\b",
    r"\bc-?mac\b",
    r"\bmcgrath\b",
    r"\bking\s+vision\b",
]

SUPRAGLOTTIC_PATTERNS = [
    r"\bLMA\b",
    r"\blaryngeal\s+mask\b",
    r"\bsupraglottic\b",
    r"\bi-?gel\b",
    r"\bair-?q\b",
]

BRONCHOSCOPY_PATTERNS = [
    r"\bbronchosc(op(y|e|ic))?\b",
    r"\bfiberoptic\b.*\bintubat",
    r"\bFOI\b",
]

MASK_VENTILATION_PATTERNS = [
    r"\bmask\b(?!.*\bLMA\b)",
    r"\bmask\s+vent(ilation)?\b",
    r"\bBVM\b",
    r"\bbag[- ]?mask\b",
    r"\bface\s+mask\b",
]

DIFFICULT_AIRWAY_PATTERNS = [
    r"\bdifficult\s+(airway|intubat)",
    r"\bairway\s+difficult",
    r"\bfailed\s+intubat",
    r"\bmultiple\s+attempt",
]

ARTERIAL_LINE_PATTERNS = [
    r"\barterial\s+line\b",
    r"\bA-?line\b",
    r"\bart[- ]line\b",
    r"\barterial\s+catheter\b",
    r"\b[Aa]\s+line\b",
    r"\bradial\s+(artery|arterial|line)\b",
    r"\bfemoral\s+(artery|arterial|line)\b",
]

CENTRAL_LINE_PATTERNS = [
    r"\bcentral\s+(venous|line)\b",
    r"\bCVC\b",
    r"\binternal\s+jugular\b",
    r"\bIJ\b.*\b(line|catheter)\b",
    r"\bsubclavian\b.*\b(line|catheter)\b",
    r"\bfemoral\s+(venous\s+)?(line|catheter)\b",
    r"\bcentral\s+access\b",
]

PA_CATHETER_PATTERNS = [
    r"\bpulmonary\s+artery\s+catheter\b",
    r"\bPA\s+catheter\b",
    r"\bSwan[- ]?Ganz\b",
    r"\bPAC\b",
]

TEE_PATTERNS = [
    r"\bTEE\b",
    r"\btransesophageal\s+echo(cardiograph(y|ic))?\b",
    r"\btrans[- ]?esophageal\b",
]

ELECTROPHYSIOLOGIC_PATTERNS = [
    r"\belectrophysiolog(ic|y)\b",
    r"\bEP\s+stud(y|ies)\b",
    r"\bSSCP\b",
    r"\bSSEP\b",
    r"\bneuro(physiologic)?\s+monitor",
    r"\bevoked\s+potential",
]

CSF_DRAIN_PATTERNS = [
    r"\bCSF\s+(drain(age)?|catheter)\b",
    r"\blumbar\s+drain\b",
    r"\bcerebrospinal\s+fluid\s+drain",
    r"\bspinal\s+drain\b",
]

INVASIVE_NEURO_PATTERNS = [
    r"\bICP\s+(monitor|catheter)\b",
    r"\bintracranial\s+pressure\b",
    r"\bventriculostomy\b",
    r"\bEVD\b",
]

# Negation patterns
NEGATION_PATTERNS = [
    r"\bno\s+",
    r"\bnot\s+",
    r"\bwithout\s+",
    r"\bdenied\b",
    r"\battempted\s+but\s+not\b",
]


def extract_airway_management_enhanced(
    notes: Any, source_field: str = "procedure_notes"
) -> tuple[list[AirwayManagement], list[ExtractionFinding]]:
    """
    Extract airway management techniques with enhanced pattern matching.

    Returns:
        Tuple of (airway_management_list, extraction_findings)
    """
    if notes is None or (isinstance(notes, float) and pd.isna(notes)):
        return [], []

    text = str(notes)
    airway_techniques = []
    findings = []

    # Check for intubation
    intubation_matches = _extract_with_context(text, INTUBATION_PATTERNS)
    if intubation_matches:
        # Determine if nasal vs oral
        if re.search(r"\bnasal\b", text, re.IGNORECASE):
            airway_techniques.append(AirwayManagement.NASAL_ETT)
            confidence = _calculate_pattern_confidence(
                text, INTUBATION_PATTERNS, [r"\bnasal\b"], NEGATION_PATTERNS
            )
        else:
            airway_techniques.append(AirwayManagement.ORAL_ETT)
            confidence = _calculate_pattern_confidence(
                text, INTUBATION_PATTERNS, None, NEGATION_PATTERNS
            )

        findings.append(
            ExtractionFinding(
                value=AirwayManagement.ORAL_ETT.value,
                confidence=confidence,
                context=intubation_matches[0][1],
                source_field=source_field,
            )
        )

        # Check for laryngoscopy method
        dl_matches = _extract_with_context(text, DIRECT_LARYNGOSCOPY_PATTERNS)
        if dl_matches:
            airway_techniques.append(AirwayManagement.DIRECT_LARYNGOSCOPE)
            confidence = _calculate_pattern_confidence(
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

        vl_matches = _extract_with_context(text, VIDEO_LARYNGOSCOPY_PATTERNS)
        if vl_matches:
            airway_techniques.append(AirwayManagement.VIDEO_LARYNGOSCOPE)
            confidence = _calculate_pattern_confidence(
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
    sga_matches = _extract_with_context(text, SUPRAGLOTTIC_PATTERNS)
    if sga_matches:
        airway_techniques.append(AirwayManagement.SUPRAGLOTTIC_AIRWAY)
        confidence = _calculate_pattern_confidence(
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
    bronch_matches = _extract_with_context(text, BRONCHOSCOPY_PATTERNS)
    if bronch_matches:
        airway_techniques.append(AirwayManagement.FLEXIBLE_BRONCHOSCOPIC)
        confidence = _calculate_pattern_confidence(
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
    mask_matches = _extract_with_context(text, MASK_VENTILATION_PATTERNS)
    if mask_matches:
        airway_techniques.append(AirwayManagement.MASK)
        confidence = _calculate_pattern_confidence(
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
    difficult_matches = _extract_with_context(text, DIFFICULT_AIRWAY_PATTERNS)
    if difficult_matches:
        airway_techniques.append(AirwayManagement.DIFFICULT_AIRWAY)
        confidence = _calculate_pattern_confidence(text, DIFFICULT_AIRWAY_PATTERNS)
        findings.append(
            ExtractionFinding(
                value=AirwayManagement.DIFFICULT_AIRWAY.value,
                confidence=confidence,
                context=difficult_matches[0][1],
                source_field=source_field,
            )
        )

    # Remove duplicates while preserving order
    seen = set()
    unique_airway = []
    for technique in airway_techniques:
        if technique not in seen:
            seen.add(technique)
            unique_airway.append(technique)

    return unique_airway, findings


def extract_vascular_access_enhanced(
    notes: Any, source_field: str = "procedure_notes"
) -> tuple[list[VascularAccess], list[ExtractionFinding]]:
    """
    Extract vascular access with enhanced pattern matching.

    Returns:
        Tuple of (vascular_access_list, extraction_findings)
    """
    if notes is None or (isinstance(notes, float) and pd.isna(notes)):
        return [], []

    text = str(notes)
    vascular = []
    findings = []

    # Arterial line
    art_matches = _extract_with_context(text, ARTERIAL_LINE_PATTERNS)
    if art_matches:
        vascular.append(VascularAccess.ARTERIAL_CATHETER)
        confidence = _calculate_pattern_confidence(
            text, ARTERIAL_LINE_PATTERNS, None, NEGATION_PATTERNS
        )
        findings.append(
            ExtractionFinding(
                value=VascularAccess.ARTERIAL_CATHETER.value,
                confidence=confidence,
                context=art_matches[0][1],
                source_field=source_field,
            )
        )

    # Central venous catheter
    cvc_matches = _extract_with_context(text, CENTRAL_LINE_PATTERNS)
    if cvc_matches:
        vascular.append(VascularAccess.CENTRAL_VENOUS_CATHETER)
        confidence = _calculate_pattern_confidence(
            text, CENTRAL_LINE_PATTERNS, None, NEGATION_PATTERNS
        )
        findings.append(
            ExtractionFinding(
                value=VascularAccess.CENTRAL_VENOUS_CATHETER.value,
                confidence=confidence,
                context=cvc_matches[0][1],
                source_field=source_field,
            )
        )

    # PA catheter
    pa_matches = _extract_with_context(text, PA_CATHETER_PATTERNS)
    if pa_matches:
        vascular.append(VascularAccess.PULMONARY_ARTERY_CATHETER)
        confidence = _calculate_pattern_confidence(
            text, PA_CATHETER_PATTERNS, CENTRAL_LINE_PATTERNS
        )
        findings.append(
            ExtractionFinding(
                value=VascularAccess.PULMONARY_ARTERY_CATHETER.value,
                confidence=confidence,
                context=pa_matches[0][1],
                source_field=source_field,
            )
        )

    # Remove duplicates
    seen = set()
    unique_vascular = []
    for access in vascular:
        if access not in seen:
            seen.add(access)
            unique_vascular.append(access)

    return unique_vascular, findings


def extract_monitoring_enhanced(
    notes: Any, source_field: str = "procedure_notes"
) -> tuple[list[MonitoringTechnique], list[ExtractionFinding]]:
    """
    Extract monitoring techniques with enhanced pattern matching.

    Returns:
        Tuple of (monitoring_list, extraction_findings)
    """
    if notes is None or (isinstance(notes, float) and pd.isna(notes)):
        return [], []

    text = str(notes)
    monitoring = []
    findings = []

    # TEE
    tee_matches = _extract_with_context(text, TEE_PATTERNS)
    if tee_matches:
        monitoring.append(MonitoringTechnique.TEE)
        confidence = _calculate_pattern_confidence(text, TEE_PATTERNS)
        findings.append(
            ExtractionFinding(
                value=MonitoringTechnique.TEE.value,
                confidence=confidence,
                context=tee_matches[0][1],
                source_field=source_field,
            )
        )

    # Electrophysiologic monitoring
    ep_matches = _extract_with_context(text, ELECTROPHYSIOLOGIC_PATTERNS)
    if ep_matches:
        monitoring.append(MonitoringTechnique.ELECTROPHYSIOLOGIC_MON)
        confidence = _calculate_pattern_confidence(text, ELECTROPHYSIOLOGIC_PATTERNS)
        findings.append(
            ExtractionFinding(
                value=MonitoringTechnique.ELECTROPHYSIOLOGIC_MON.value,
                confidence=confidence,
                context=ep_matches[0][1],
                source_field=source_field,
            )
        )

    # CSF drain
    csf_matches = _extract_with_context(text, CSF_DRAIN_PATTERNS)
    if csf_matches:
        monitoring.append(MonitoringTechnique.CSF_DRAIN)
        confidence = _calculate_pattern_confidence(text, CSF_DRAIN_PATTERNS)
        findings.append(
            ExtractionFinding(
                value=MonitoringTechnique.CSF_DRAIN.value,
                confidence=confidence,
                context=csf_matches[0][1],
                source_field=source_field,
            )
        )

    # Invasive neuro monitoring
    neuro_matches = _extract_with_context(text, INVASIVE_NEURO_PATTERNS)
    if neuro_matches:
        monitoring.append(MonitoringTechnique.INVASIVE_NEURO_MON)
        confidence = _calculate_pattern_confidence(text, INVASIVE_NEURO_PATTERNS)
        findings.append(
            ExtractionFinding(
                value=MonitoringTechnique.INVASIVE_NEURO_MON.value,
                confidence=confidence,
                context=neuro_matches[0][1],
                source_field=source_field,
            )
        )

    # Remove duplicates
    seen = set()
    unique_monitoring = []
    for tech in monitoring:
        if tech not in seen:
            seen.add(tech)
            unique_monitoring.append(tech)

    return unique_monitoring, findings
