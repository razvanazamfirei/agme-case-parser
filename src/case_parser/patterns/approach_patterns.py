"""
Surgical Approach Detection Patterns.

This file contains keywords for detecting whether a procedure was performed
using an endovascular/percutaneous approach versus an open surgical approach.

These patterns are used to subcategorize procedures like:
- Major vessel procedures: endovascular vs open
- Intracerebral procedures: endovascular vs open
"""

from __future__ import annotations

from functools import lru_cache

# Keywords indicating ENDOVASCULAR/PERCUTANEOUS approach
ENDOVASCULAR_KEYWORDS = (
    "ENDOVASCULAR",
    "PERCUTANEOUS",
    "CATHETER",
    "STENT",
    "COIL",
    "COILING",
    "EMBOLIZATION",
    "EMBOLIZE",
    "ANGIOPLASTY",
    "ANGIOGRAM",
    "ANGIOGRAPHY",
    "THROMBECTOMY",
    "EVAR",  # Endovascular Aneurysm Repair
    "TEVAR",  # Thoracic Endovascular Aneurysm Repair
    "FEVAR",  # Fenestrated EVAR
    "PTA",  # Percutaneous Transluminal Angioplasty
    "INTERVENTION",
    "ENDOGRAFT",
)

# Keywords indicating OPEN surgical approach
OPEN_KEYWORDS = (
    "OPEN",
    "CRANIOTOMY",
    "CRANIECTOMY",
    "CLIPPING",  # Aneurysm clipping
    "BYPASS",
    "GRAFT",
    "ENDARTERECTOMY",
    "CEA",  # Carotid Endarterectomy
    "REPAIR",  # Often indicates open repair vs endovascular
    "RESECTION",
    "EXCISION",
    "DECOMPRESSION",
    "LAPAROTOMY",
    "THORACOTOMY",
    "STERNOTOMY",
)


# Keywords indicating VASCULAR pathology (for intracerebral procedures)
VASCULAR_PATHOLOGY_KEYWORDS = (
    "ANEURYSM",
    "AVM",  # Arteriovenous Malformation
    "ARTERIOVENOUS",
    "VASCULAR MALFORMATION",
    "HEMORRHAGE",
    "BLEED",
    "BLEEDING",
    "STROKE",
    "ISCHEMIA",
    "CAVERNOMA",
    "CAVERNOUS MALFORMATION",
)

# Keywords indicating NONVASCULAR pathology (for intracerebral procedures)
NONVASCULAR_PATHOLOGY_KEYWORDS = (
    "TUMOR",
    "MASS",
    "LESION",
    "CYST",
    "ABSCESS",
    "GLIOMA",
    "MENINGIOMA",
    "NEOPLASM",
    "CANCER",
    "EPILEPSY",
    "SEIZURE",
    "HYDROCEPHALUS",
    "SHUNT",
)


def detect_approach(procedure_text: str | None) -> str:
    """
    Detect surgical approach from procedure text.

    Args:
        procedure_text: The procedure description text

    Returns:
        "endovascular", "open", or "unknown" if cannot be determined
    """
    if not procedure_text:
        return "unknown"
    return _detect_approach_cached(str(procedure_text).upper())


@lru_cache(maxsize=32768)
def _detect_approach_cached(text_upper: str) -> str:  # noqa: PLR0911
    """Cached implementation for approach detection."""
    if not text_upper:
        return "unknown"

    # Check for endovascular keywords
    has_endovascular = any(keyword in text_upper for keyword in ENDOVASCULAR_KEYWORDS)

    # Check for open keywords
    has_open = any(keyword in text_upper for keyword in OPEN_KEYWORDS)

    # If both or neither are found, return unknown
    if has_endovascular and has_open:
        cranial_open_terms = ("CRANIOTOMY", "CRANIECTOMY", "BURR HOLE", "CLIPPING")
        if any(term in text_upper for term in cranial_open_terms):
            return "open"
        # Both mentioned - prefer endovascular if explicitly stated
        if "ENDOVASCULAR" in text_upper or "PERCUTANEOUS" in text_upper:
            return "endovascular"
        return "unknown"

    if has_endovascular:
        return "endovascular"

    if has_open:
        return "open"

    return "unknown"


def detect_intracerebral_pathology(procedure_text: str | None) -> str:
    """
    Detect whether intracerebral procedure is vascular or nonvascular.

    Args:
        procedure_text: The procedure description text

    Returns:
        "vascular", "nonvascular", or "unknown" if cannot be determined
    """
    if not procedure_text:
        return "unknown"
    return _detect_intracerebral_pathology_cached(str(procedure_text).upper())


@lru_cache(maxsize=32768)
def _detect_intracerebral_pathology_cached(text_upper: str) -> str:
    """Cached implementation for intracerebral pathology detection."""
    if not text_upper:
        return "unknown"

    # Check for vascular pathology keywords
    has_vascular = any(keyword in text_upper for keyword in VASCULAR_PATHOLOGY_KEYWORDS)

    # Check for nonvascular pathology keywords
    has_nonvascular = any(
        keyword in text_upper for keyword in NONVASCULAR_PATHOLOGY_KEYWORDS
    )

    # If both or neither are found, return unknown
    if has_vascular and not has_nonvascular:
        return "vascular"

    if has_nonvascular and not has_vascular:
        return "nonvascular"

    if "HEMATOMA" in text_upper and not any(
        keyword in text_upper for keyword in ("ANEURYSM", "AVM", "ARTERIOVENOUS")
    ):
        return "nonvascular"

    return "unknown"
