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

import re

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


def clean_names(name: str) -> str:
    """
    Clean and standardize provider names.

    Removes titles, trailing commas, and normalizes whitespace.

    Args:
        name: Raw provider name

    Returns:
        Cleaned name string

    Example:
        clean_names("Smith, John MD")
        # Returns: "Smith, John"
    """
    if pd.isna(name):
        return ""
    # Take only the first attending if multiple are listed
    name = str(name).split(";")[0].strip()
    # Remove titles
    name = re.sub(r"\b(MD|DO|PhD|CRNA|RN)\b", "", name, flags=re.IGNORECASE).strip()
    # Remove trailing commas and extra whitespace
    name = re.sub(r",\s*$", "", name).strip()
    return re.sub(r"\s+", " ", name)


def extract_attending(value: str) -> str:
    """Clean an attending name by removing timestamps and extra entries.

    Input format: "DOE, JOHN@2023-01-01 08:00:00" or semicolon-separated list.
    Returns the first name with the timestamp stripped.
    """
    if pd.isna(value):
        return ""
    first_part = str(value).split(";")[0]
    return first_part.split("@")[0].strip()
