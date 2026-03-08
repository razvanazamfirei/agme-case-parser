"""
Text extraction functions.

This module provides extraction functions for medical case data. The actual
extraction logic lives in the patterns/ directory, organized by field category.

For implementation details and pattern definitions, see:
- patterns/airway_patterns.py
- patterns/vascular_access_patterns.py
- patterns/monitoring_patterns.py
"""

from __future__ import annotations

import math
import re
from numbers import Real

import pandas as pd

from .patterns import (
    extract_airway_management,
    extract_monitoring,
    extract_vascular_access,
)

__all__ = [
    "clean_names",
    "extract_airway_management",
    "extract_attending",
    "extract_monitoring",
    "extract_vascular_access",
]


def _is_missing_scalar(value: object) -> bool:
    """Return True for scalar missing-value sentinels handled by these helpers."""
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    # Preserve literal strings like "nan"; only real scalar null sentinels
    # should be treated as missing by these helpers.
    if isinstance(value, (str, bytes)):
        return False
    if isinstance(value, Real):
        return math.isnan(float(value))
    return False


def clean_names(name: object) -> str:
    """
    Clean and standardize provider names.

    Removes titles, trailing commas, and normalizes whitespace.

    Args:
        name: Raw provider name or missing scalar.

    Returns:
        Cleaned name string, or an empty string for missing values.

    Example:
        clean_names("Smith, John MD")
        # Returns: "Smith, John"
    """
    if _is_missing_scalar(name):
        return ""
    # Take only the first attending if multiple are listed
    name = str(name).split(";")[0].strip()
    # Remove titles
    name = re.sub(r"\b(MD|DO|PhD|CRNA|RN)\b", "", name, flags=re.IGNORECASE).strip()
    # Remove trailing commas and extra whitespace
    name = re.sub(r",\s*$", "", name).strip()
    return re.sub(r"\s+", " ", name)


def extract_attending(value: object) -> str:
    """Clean an attending name by removing timestamps and extra entries.

    Input format: "DOE, JOHN@2023-01-01 08:00:00" or semicolon-separated list.
    Returns the first name with the timestamp stripped.

    Args:
        value: Raw attending name value from the MPOG AnesAttendings field.
            May be NaN or contain multiple semicolon-separated entries, each
            optionally followed by an "@timestamp" suffix.

    Returns:
        First attending name with the timestamp removed, or an empty string
        if value is NaN.
    """
    if _is_missing_scalar(value):
        return ""
    first_part = str(value).split(";")[0]
    return first_part.split("@")[0].strip()
