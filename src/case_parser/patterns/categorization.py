"""
Procedure Categorization Logic.

This module contains all the logic for categorizing procedures based on
services and procedure text. Each surgery type has its own categorization
function that encapsulates the specific rules for that type.
"""

from __future__ import annotations

import pandas as pd

from ..domain import ProcedureCategory
from .approach_patterns import detect_approach, detect_intracerebral_pathology
from .procedure_patterns import PROCEDURE_RULES


def categorize_cardiac(procedure_text: str) -> ProcedureCategory:
    """
    Categorize cardiac procedures based on CPB usage.

    Cardiac procedures are split into:
    - Cardiac with CPB: Traditional open-heart surgery with cardiopulmonary bypass
    - Cardiac without CPB: Percutaneous/transcatheter procedures, VAD removal, etc.

    Args:
        procedure_text: Uppercase procedure description

    Returns:
        ProcedureCategory for cardiac subtype
    """
    # Procedures that are always without CPB
    no_cpb_keywords = (
        "TAVR",
        "TAVI",
        "TRANSCATHETER",
        "OFF-PUMP",
        "OFF PUMP",
        "OPCAB",
        "BEATING HEART",
        "REMOVAL VENTRICULAR ASSIST DEVICE",
        "REMOVAL IMPLANT",
        "PERCUTANEOUS",
    )

    # Procedures that use CPB
    cpb_keywords = (
        "BYPASS",
        "CPB",
        "PUMP",
        "ON-PUMP",
        "ON PUMP",
        "CARDIOPULMONARY BYPASS",
    )

    has_no_cpb = any(kw in procedure_text for kw in no_cpb_keywords)
    has_cpb = any(kw in procedure_text for kw in cpb_keywords)

    # No CPB takes precedence (e.g., "OFF-PUMP BYPASS")
    if has_no_cpb:
        return ProcedureCategory.CARDIAC_WITHOUT_CPB
    if has_cpb:
        return ProcedureCategory.CARDIAC_WITH_CPB
    # Default to with CPB for unspecified cardiac procedures
    return ProcedureCategory.CARDIAC_WITH_CPB


def categorize_vascular(procedure_text: str) -> ProcedureCategory:
    """
    Categorize major vessel procedures based on surgical approach.

    Major vessel procedures are split into:
    - Endovascular: Percutaneous, catheter-based interventions
    - Open: Traditional open surgical repair

    Args:
        procedure_text: Procedure description

    Returns:
        ProcedureCategory for vascular subtype
    """
    approach = detect_approach(procedure_text)
    if approach == "endovascular":
        return ProcedureCategory.MAJOR_VESSELS_ENDOVASCULAR
    return ProcedureCategory.MAJOR_VESSELS_OPEN


def categorize_intracerebral(procedure_text: str) -> ProcedureCategory:
    """
    Categorize intracerebral procedures based on approach and pathology.

    Intracerebral procedures are split by:
    1. Approach: endovascular vs open
    2. Pathology (for open): vascular vs nonvascular

    Args:
        procedure_text: Procedure description

    Returns:
        ProcedureCategory for intracerebral subtype
    """
    approach = detect_approach(procedure_text)

    if approach == "endovascular":
        return ProcedureCategory.INTRACEREBRAL_ENDOVASCULAR

    if approach == "open":
        pathology = detect_intracerebral_pathology(procedure_text)
        if pathology == "vascular":
            return ProcedureCategory.INTRACEREBRAL_VASCULAR_OPEN
        if pathology == "nonvascular":
            return ProcedureCategory.INTRACEREBRAL_NONVASCULAR_OPEN
        # Default to vascular if unknown
        return ProcedureCategory.INTRACEREBRAL_VASCULAR_OPEN

    return ProcedureCategory.INTRACEREBRAL_NONVASCULAR_OPEN


def categorize_obgyn(procedure_text: str) -> ProcedureCategory:
    """
    Categorize OB/GYN procedures based on delivery type.

    OB/GYN procedures are split into:
    - Cesarean delivery
    - Vaginal delivery (including labor epidurals)
    - Other GYN procedures

    Args:
        procedure_text: Uppercase procedure description

    Returns:
        ProcedureCategory for OB/GYN subtype
    """
    # Check for cesarean
    cesarean_keywords = ("CESAREAN", "C-SECTION", "C SECTION")
    if any(kw in procedure_text for kw in cesarean_keywords):
        return ProcedureCategory.CESAREAN

    # Check for vaginal delivery / labor
    vaginal_keywords = ("LABOR EPIDURAL", "VAGINAL", "DELIVERY", "LABOR")
    if any(kw in procedure_text for kw in vaginal_keywords):
        return ProcedureCategory.VAGINAL_DELIVERY

    # Other GYN procedures
    return ProcedureCategory.OTHER


def _match_services_to_categories(
    services: list[str], procedure_text: str
) -> list[ProcedureCategory]:
    """Match services against procedure rules and return matched categories."""
    categories = []
    for service in services:
        service_upper = service.upper()

        for rule in PROCEDURE_RULES:
            if not any(keyword in service_upper for keyword in rule.keywords):
                continue
            if rule.exclude_keywords and any(
                excl in service_upper or excl in procedure_text
                for excl in rule.exclude_keywords
            ):
                continue
            category = _apply_rule_category(rule.category, procedure_text)
            if category not in categories:
                categories.append(category)
            break

        if any(keyword in service_upper for keyword in ("GYN", "OB", "OBSTET")):
            obgyn_category = categorize_obgyn(procedure_text)
            if obgyn_category not in categories:
                categories.append(obgyn_category)

    return categories


def _fallback_categories_from_text(procedure_text: str) -> list[ProcedureCategory]:
    """Infer categories directly from procedure text when services are empty."""
    for rule in PROCEDURE_RULES:
        if not any(keyword in procedure_text for keyword in rule.keywords):
            continue
        if rule.exclude_keywords and any(
            excl in procedure_text for excl in rule.exclude_keywords
        ):
            continue
        return [_apply_rule_category(rule.category, procedure_text)]

    obgyn_category = categorize_obgyn(procedure_text)
    if obgyn_category != ProcedureCategory.OTHER:
        return [obgyn_category]

    return []


def categorize_procedure(
    procedure: str | None, services: list[str]
) -> tuple[ProcedureCategory, list[str]]:
    """
    Categorize a procedure based on services and procedure text.

    This is the main entry point for procedure categorization. It:
    1. Checks services against PROCEDURE_RULES
    2. Applies surgery-specific categorization logic
    3. Handles special cases (OB/GYN, labor epidural)
    4. Returns the category and any warnings

    Args:
        procedure: Procedure description text
        services: List of service names

    Returns:
        Tuple of (ProcedureCategory, warnings_list)
    """
    warnings = []
    procedure_text = "" if pd.isna(procedure) else str(procedure).upper()

    categories = _match_services_to_categories(services, procedure_text)

    if not categories and procedure_text:
        categories = _fallback_categories_from_text(procedure_text)

    if (
        not categories or categories == [ProcedureCategory.OTHER]
    ) and "LABOR EPIDURAL" in procedure_text:
        categories = [ProcedureCategory.VAGINAL_DELIVERY]

    if len(categories) > 1:
        warnings.append(
            f"Multiple procedure categories detected for services {services}: "
            f"{[c.value for c in categories]}. Using first: {categories[0].value}"
        )
        return categories[0], warnings

    if len(categories) == 1:
        return categories[0], warnings

    return ProcedureCategory.OTHER, warnings


def _apply_rule_category(rule_category: str, procedure_text: str) -> ProcedureCategory:
    """
    Apply surgery-specific categorization based on rule category.

    This maps rule categories to their specific categorization functions.

    Args:
        rule_category: Category from PROCEDURE_RULES
        procedure_text: Uppercase procedure description

    Returns:
        Specific ProcedureCategory
    """
    if rule_category == "Cardiac":
        return categorize_cardiac(procedure_text)

    if rule_category == "Procedures Major Vessels":
        return categorize_vascular(procedure_text)

    if rule_category == "Intracerebral":
        return categorize_intracerebral(procedure_text)

    # Standard category mapping
    category_map = {
        "Intrathoracic non-cardiac": ProcedureCategory.INTRATHORACIC_NON_CARDIAC,
        "Other (procedure cat)": ProcedureCategory.OTHER,
    }
    return category_map.get(rule_category, ProcedureCategory.OTHER)
