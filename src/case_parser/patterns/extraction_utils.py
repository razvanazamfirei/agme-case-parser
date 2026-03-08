"""
Shared utilities for pattern-based extraction.

This module contains helper functions used across all extraction modules.
These utilities handle pattern matching, confidence scoring, and context extraction.
"""

from __future__ import annotations

import re
from functools import cache

PatternLike = str | re.Pattern[str]


@cache
def _compile_ignore_case(pattern: str) -> re.Pattern[str]:
    """Compile a case-insensitive regex once and reuse it across rows."""
    return re.compile(pattern, re.IGNORECASE)


def _coerce_pattern(pattern: PatternLike) -> re.Pattern[str]:
    """Normalize a string or compiled regex pattern to a compiled regex."""
    if isinstance(pattern, re.Pattern):
        return pattern
    return _compile_ignore_case(pattern)


def extract_with_context(
    text: str, patterns: list[PatternLike], context_window: int = 50
) -> list[tuple[str, str, int]]:
    r"""
    Extract matches with surrounding context.

    Args:
        text: Text to search in
        patterns: List of regex patterns to match
        context_window: Number of characters before/after match to include

    Returns:
        List of (matched_text, context, position) tuples

    Example:
        text = "Patient had arterial line placed in radial artery"
        patterns = [r"arterial\s+line"]
        matches = extract_with_context(text, patterns, context_window=20)
        # Returns: [("arterial line", "had arterial line placed", 12)]
    """
    findings = []
    for pattern in patterns:
        compiled_pattern = _coerce_pattern(pattern)
        for match in compiled_pattern.finditer(text):
            start = max(0, match.start() - context_window)
            end = min(len(text), match.end() + context_window)
            context = text[start:end].strip()
            findings.append((match.group(), context, match.start()))
    return findings


def calculate_pattern_confidence(
    text: str,
    primary_patterns: list[PatternLike],
    supporting_patterns: list[PatternLike] | None = None,
    negation_patterns: list[PatternLike] | None = None,
) -> float:
    r"""
    Calculate confidence score based on pattern matches.

    Confidence scoring logic:
    - Base: 0.5 if primary pattern matches
    - Supporting: +0.1 per supporting pattern (max +0.4)
    - Negation: -0.3 per negation pattern

    Args:
        text: Text to analyze
        primary_patterns: Main patterns that must match
        supporting_patterns: Optional patterns that increase confidence
        negation_patterns: Patterns that decrease confidence (e.g., "no intubation")

    Returns:
        Confidence score between 0.0 and 1.0

    Example:
        text = "Patient intubated with video laryngoscopy"
        primary = [r"intubat"]
        supporting = [r"video\s+laryngosc"]
        confidence = calculate_pattern_confidence(text, primary, supporting)
        # Returns: 0.6 (base 0.5 + supporting 0.1)
    """
    if not primary_patterns:
        return 0.0

    if not any(_coerce_pattern(pattern).search(text) for pattern in primary_patterns):
        return 0.0

    confidence = 0.5

    if supporting_patterns:
        supporting_matches = sum(
            1
            for pattern in supporting_patterns
            if _coerce_pattern(pattern).search(text)
        )
        confidence += min(supporting_matches * 0.1, 0.4)

    if negation_patterns:
        negation_matches = sum(
            1
            for pattern in negation_patterns
            if _coerce_pattern(pattern).search(text)
        )
        confidence -= negation_matches * 0.3

    return max(0.0, min(1.0, confidence))


def remove_duplicates_preserve_order(items: list) -> list:
    """
    Remove duplicates from a list while preserving order.

    Args:
        items: List with potential duplicates

    Returns:
        List with duplicates removed, order preserved

    Example:
        items = ["ETT", "DL", "ETT", "VL", "DL"]
        remove_duplicates_preserve_order(items)
        # Returns: ["ETT", "DL", "VL"]
    """
    seen = set()
    unique = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique
