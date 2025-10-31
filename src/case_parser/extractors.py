"""Text extraction functions for parsing procedure notes and other text fields."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _regex_any(patterns: list[str], text: str) -> bool:
    """Check if any regex pattern matches text (case-insensitive)."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def clean_names(name: str) -> str:
    """Clean and standardize anesthesiologist names."""
    if pd.isna(name):
        return ""
    name = str(name).strip()
    # Remove titles
    name = re.sub(r"\b(MD|DO|PhD)", "", name, flags=re.IGNORECASE).strip()
    # Remove trailing commas
    return re.sub(r",\s*$", "", name).strip()


def extract_airway_management(notes: Any) -> str:
    """Extract airway management techniques from procedure notes."""
    if notes is None or (isinstance(notes, float) and pd.isna(notes)):
        return ""

    text = str(notes)
    findings = []

    # Intubation detection
    if _regex_any([r"\bintubat", r"\bett\b", r"\bendotrache"], text):
        findings.append("Oral ETT")

        # Laryngoscopy types
        if _regex_any([r"direct laryngosc", r"\bDL\b", r"miller", r"macintosh"], text):
            findings.append("Direct Laryngoscope")
        if _regex_any([r"video laryngosc", r"\bVL\b", r"glidescope", r"c-?mac"], text):
            findings.append("Video Laryngoscope")

    # Other airway devices
    if _regex_any([r"\bLMA\b", r"supraglottic", r"\bigel\b", r"i-gel"], text):
        findings.append("Supraglottic Airway")
    if _regex_any([r"bronchosc"], text):
        findings.append("Flexible Bronchoscopic")
    if _regex_any([r"\bmask\b", r"mask vent", r"\bBVM\b", r"bag[- ]?mask"], text):
        findings.append("Mask")
    if _regex_any([r"\bdifficult\b"], text):
        findings.append("Difficult Airway")

    # Remove duplicates while preserving order
    return "; ".join(dict.fromkeys(findings))


def extract_vascular_access(notes: Any) -> str:
    """Extract vascular access information from procedure notes."""
    if notes is None or (isinstance(notes, float) and pd.isna(notes)):
        return ""

    text = str(notes)
    findings = []

    if _regex_any([r"arterial line", r"\bA[- ]?line\b", r"\bart line\b"], text):
        findings.append("Arterial Catheter")

    if _regex_any(
        [
            r"central venous",
            r"\bCVC\b",
            r"central line",
            r"internal jugular",
            r"subclavian",
            r"femoral line",
        ],
        text,
    ):
        findings.append("Central Venous Catheter")

    return "; ".join(dict.fromkeys(findings))


def extract_monitoring(notes: Any) -> str:
    """Extract specialized monitoring techniques from procedure notes."""
    if notes is None or (isinstance(notes, float) and pd.isna(notes)):
        return ""

    text = str(notes)
    findings = []

    if _regex_any([r"\bTEE\b", r"transesophageal echo"], text):
        findings.append("TEE")
    if _regex_any([r"electrophysiolog", r"\bEP study\b", r"\bSSCP\b"], text):
        findings.append("Electrophysiologic mon")
    if _regex_any([r"\bCSF\b.*drain|\bCSF\b.*drainage|lumbar drain"], text):
        findings.append("CSF Drain")

    return "; ".join(dict.fromkeys(findings))

