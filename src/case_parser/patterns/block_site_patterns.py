"""Canonical mappings for peripheral and neuraxial block-site locations."""

from __future__ import annotations

import re
from typing import Final

PERIPHERAL_BLOCK_SITE_TERMS: tuple[str, ...] = (
    "Adductor Canal",
    "Ankle",
    "Axillary",
    "Erector Spinae Plane",
    "Femoral",
    "Infraclavicular",
    "Interscalene",
    "Lumbar Plexus",
    "Paravertebral",
    "Popliteal",
    "Quadratus Lumborum",
    "Retrobulbar",
    "Saphenous",
    "Sciatic",
    "Supraclavicular",
    "Transverse Abdominal Plane",
    "Other - peripheral nerve blockade site",
)

NEURAXIAL_BLOCK_SITE_TERMS: tuple[str, ...] = (
    "Caudal",
    "Cervical",
    "Lumbar",
    "T 1-7",
    "T 8-12",
)

_OTHER_PERIPHERAL_SITE: Final[str] = "Other - peripheral nerve blockade site"

_PERIPHERAL_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "Adductor Canal",
        (
            re.compile(r"\badductor\s+canal\b", flags=re.IGNORECASE),
            re.compile(r"\bacb\b", flags=re.IGNORECASE),
        ),
    ),
    ("Ankle", (re.compile(r"\bankle\b", flags=re.IGNORECASE),)),
    ("Axillary", (re.compile(r"\baxillary\b", flags=re.IGNORECASE),)),
    (
        "Erector Spinae Plane",
        (
            re.compile(r"\berector\s+spinae\s+plane\b", flags=re.IGNORECASE),
            re.compile(r"\besp\b", flags=re.IGNORECASE),
        ),
    ),
    ("Femoral", (re.compile(r"\bfemoral\b", flags=re.IGNORECASE),)),
    ("Infraclavicular", (re.compile(r"\binfraclavicular\b", flags=re.IGNORECASE),)),
    (
        "Interscalene",
        (
            re.compile(r"\binterscalene\b", flags=re.IGNORECASE),
            re.compile(r"\bisb\b", flags=re.IGNORECASE),
        ),
    ),
    (
        "Lumbar Plexus",
        (
            re.compile(r"\blumbar\s+plexus\b", flags=re.IGNORECASE),
            re.compile(r"\bpsoas\s+compartment\b", flags=re.IGNORECASE),
        ),
    ),
    ("Paravertebral", (re.compile(r"\bparavertebral\b", flags=re.IGNORECASE),)),
    ("Popliteal", (re.compile(r"\bpopliteal\b", flags=re.IGNORECASE),)),
    (
        "Quadratus Lumborum",
        (
            re.compile(r"\bquadratus\s+lumborum\b", flags=re.IGNORECASE),
            re.compile(r"\bql\b", flags=re.IGNORECASE),
        ),
    ),
    ("Retrobulbar", (re.compile(r"\bretrobulbar\b", flags=re.IGNORECASE),)),
    ("Saphenous", (re.compile(r"\bsaphenous\b", flags=re.IGNORECASE),)),
    ("Sciatic", (re.compile(r"\bsciatic\b", flags=re.IGNORECASE),)),
    ("Supraclavicular", (re.compile(r"\bsupraclavicular\b", flags=re.IGNORECASE),)),
    (
        "Transverse Abdominal Plane",
        (
            re.compile(
                r"\btransvers(?:e|us)\s+abdom(?:inal|inis)\s+plane\b",
                flags=re.IGNORECASE,
            ),
            re.compile(r"\btap\b", flags=re.IGNORECASE),
        ),
    ),
)

_NEURAXIAL_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "Caudal",
        (
            re.compile(r"\bcaudal\b", flags=re.IGNORECASE),
            re.compile(r"\bsacral\b", flags=re.IGNORECASE),
        ),
    ),
    ("Cervical", (re.compile(r"\bcervical\b", flags=re.IGNORECASE),)),
    ("Lumbar", (re.compile(r"\blumbar\b", flags=re.IGNORECASE),)),
)

_PERIPHERAL_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bperipheral\b", flags=re.IGNORECASE),
    re.compile(r"\bpnb\b", flags=re.IGNORECASE),
    re.compile(r"\bnerve\s+block(?:ade)?\b", flags=re.IGNORECASE),
    re.compile(r"\bbrachial\s+plexus\b", flags=re.IGNORECASE),
)

_THORACIC_EXPLICIT_HIGH = re.compile(r"\bt\s*1\s*-\s*7\b", flags=re.IGNORECASE)
_THORACIC_EXPLICIT_LOW = re.compile(r"\bt\s*8\s*-\s*12\b", flags=re.IGNORECASE)
_THORACIC_LEVEL_RANGE = re.compile(
    r"\b(?:t|thoracic)\s*(?P<start>[1-9]|1[0-2])\s*(?:-|to)\s*"
    r"(?:t|thoracic)?\s*(?P<end>[1-9]|1[0-2])\b",
    flags=re.IGNORECASE,
)
_THORACIC_LEVEL_SINGLE = re.compile(
    r"\b(?:t|thoracic)\s*(?P<level>[1-9]|1[0-2])\b",
    flags=re.IGNORECASE,
)
_THORACIC_UPPER = re.compile(r"\bupper\s+thoracic\b", flags=re.IGNORECASE)
_THORACIC_LOWER = re.compile(r"\blower\s+thoracic\b", flags=re.IGNORECASE)
_THORACIC_GENERIC = re.compile(r"\bthoracic\b", flags=re.IGNORECASE)
_SPINAL_CONTEXT = re.compile(r"\bspinal\b", flags=re.IGNORECASE)
_LABOR_EPIDURAL_CONTEXT = re.compile(r"\blabor\s+epidural\b", flags=re.IGNORECASE)


def normalize_block_site_terms(
    primary_block: str | None,
    *,
    procedure_name: str | None = None,
    procedure_notes: str | None = None,
) -> str | None:
    """Normalize free-text block site strings to canonical term values.

    The returned value is a semicolon-delimited list when multiple canonical
    terms are detected. Peripheral sites and neuraxial locations both map to
    their fixed term sets.
    """
    primary_text = _clean_optional_text(primary_block)
    procedure_text = _clean_optional_text(procedure_name)
    notes_text = _clean_optional_text(procedure_notes)

    if not (primary_text or procedure_text or notes_text):
        return None

    # Only use free-text notes as a supplement when a primary block value exists.
    # This avoids matching anatomical words from unrelated surgical note text.
    include_notes = bool(primary_text)
    search_text = " ".join(
        part
        for part in (
            primary_text,
            procedure_text,
            notes_text if include_notes else "",
        )
        if part
    )
    if not search_text:
        return None

    peripheral_matches = _match_canonical_terms(search_text, _PERIPHERAL_PATTERNS)
    neuraxial_matches = _match_canonical_terms(search_text, _NEURAXIAL_PATTERNS)
    neuraxial_matches.update(_match_thoracic_terms(search_text))

    # Spinals and labor epidurals are lumbar by default when no location is given.
    if not neuraxial_matches and (
        _SPINAL_CONTEXT.search(search_text)
        or _LABOR_EPIDURAL_CONTEXT.search(search_text)
    ):
        neuraxial_matches.add("Lumbar")

    if not peripheral_matches and _has_pattern_match(
        search_text, _PERIPHERAL_CONTEXT_PATTERNS
    ):
        peripheral_matches.add(_OTHER_PERIPHERAL_SITE)

    if not peripheral_matches and not neuraxial_matches:
        return primary_text or None

    ordered_terms = [
        term for term in PERIPHERAL_BLOCK_SITE_TERMS if term in peripheral_matches
    ]
    ordered_terms.extend(
        term for term in NEURAXIAL_BLOCK_SITE_TERMS if term in neuraxial_matches
    )
    return "; ".join(ordered_terms)


def _clean_optional_text(value: str | None) -> str:
    """Normalize optional text values to a plain string or empty string."""
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", "<NA>", "nan", "NaN", "None"}:
        return ""
    return text


def _match_canonical_terms(
    text: str, pattern_sets: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]
) -> set[str]:
    """Return canonical terms whose regex patterns are found in text."""
    found: set[str] = set()
    for canonical, patterns in pattern_sets:
        if any(pattern.search(text) for pattern in patterns):
            found.add(canonical)
    return found


def _has_pattern_match(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    """Return True if any regex in patterns matches text."""
    return any(pattern.search(text) for pattern in patterns)


def _match_thoracic_terms(text: str) -> set[str]:
    """Map thoracic location text to canonical T 1-7 / T 8-12 terms."""
    matches: set[str] = set()

    if _THORACIC_EXPLICIT_HIGH.search(text):
        matches.add("T 1-7")
    if _THORACIC_EXPLICIT_LOW.search(text):
        matches.add("T 8-12")

    for range_match in _THORACIC_LEVEL_RANGE.finditer(text):
        start = int(range_match.group("start"))
        end = int(range_match.group("end"))
        lo, hi = sorted((start, end))
        if lo <= 7:
            matches.add("T 1-7")
        if hi >= 8:
            matches.add("T 8-12")

    for single_match in _THORACIC_LEVEL_SINGLE.finditer(text):
        level = int(single_match.group("level"))
        if level <= 7:
            matches.add("T 1-7")
        else:
            matches.add("T 8-12")

    if _THORACIC_UPPER.search(text):
        matches.add("T 1-7")
    if _THORACIC_LOWER.search(text):
        matches.add("T 8-12")

    # If thoracic is specified without levels, capture both canonical thoracic bands.
    if not matches and _THORACIC_GENERIC.search(text):
        matches.update({"T 1-7", "T 8-12"})

    return matches
