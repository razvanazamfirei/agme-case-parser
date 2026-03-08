"""
Procedure Categorization Rules.

This file contains rules for categorizing procedures based on service keywords
found in the case data.

FIELDS EXTRACTED:
- Procedure Category (Cardiac, Intracerebral, Intrathoracic, Major Vessels, etc.)

MODIFICATION GUIDE:
Rules are evaluated in order from top to bottom. The first matching rule wins.
To modify categorization:
1. Edit keywords in existing ProcedureRule entries
2. Add new ProcedureRule entries in the desired priority position
3. Use exclude_keywords to prevent false matches

SPECIAL CASES:
- OB/GYN procedures are handled separately in processors.py with cesarean detection
- More specific rules should come before general ones
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcedureRule:
    """Rule for categorizing procedures based on service keywords."""

    keywords: tuple[str, ...]
    category: str
    exclude_keywords: tuple[str, ...] = ()


OBGYN_SERVICE_KEYWORDS = ("OBGYN", "OB/GYN", "OBSTET", "GYN")
CARDIAC_SERVICE_HINT_KEYWORDS = ("CARD", "CARDSURG", "CARDIAC")
NEURO_SERVICE_HINT_KEYWORDS = ("NEURO",)
VASCULAR_SERVICE_HINT_KEYWORDS = ("VASC",)
SPINE_EXCLUDE_KEYWORDS = (
    "SPINE",
    "SPINAL",
    "VERTEBR",
    "INTERBODY",
    "ARTHRODESIS",
    "LAMINECTOMY",
    "LAMINOTOMY",
    "DISCECTOMY",
    "FUSION",
)
CARDIAC_SERVICE_RULE_KEYWORDS = (
    "CARDIAC",
    "CARDSURG",
    "CARDIOTHORACIC",
    "CARDVASC",
    "CABG",
    "CORONARY ARTERY BYPASS",
    "VALVE REPLACEMENT",
    "VALVE REPAIR",
    "AORTIC VALVE",
    "MITRAL VALVE",
    "TRICUSPID VALVE",
    "PULMONARY VALVE",
    "AVR",
    "MVR",
    "TVR",
    "MAZE PROCEDURE",
    "ATRIAL SEPTAL DEFECT",
    "ASD REPAIR",
    "VSD REPAIR",
    "VENTRICULAR SEPTAL DEFECT",
    "HEART TRANSPLANT",
    "CARDIAC TRANSPLANT",
    "LUNG TRANSPLANT",
    "TAVR",
    "TAVI",
    "LVAD",
    "ECMO",
    "INTRACARDIAC",
    "VENTRICULAR ASSIST DEVICE",
)
CARDIAC_TEXT_RULE_KEYWORDS = (
    "CARDIAC",
    "CABG",
    "CORONARY ARTERY BYPASS",
    "CARDIOPULMONARY BYPASS",
    "TAVR",
    "TAVI",
    "TRANSCATHETER AORTIC VALVE REPLACEMENT",
    "VALVULOPLASTY",
    "AORTIC VALVE",
    "MITRAL VALVE",
    "TRICUSPID VALVE",
    "PULMONARY VALVE",
    "LVAD",
    "VENTRICULAR ASSIST DEVICE",
    "ECMO",
    "HEART TRANSPLANT",
    "CARDIAC TRANSPLANT",
    "LUNG TRANSPLANT",
)
INTRACEREBRAL_TEXT_RULE_KEYWORDS = (
    "CRANIOTOMY",
    "CRANIECTOMY",
    "BURR HOLE",
    "INTRACRANIAL",
    "CNS",
    "ANEURYSM",
    "AVM",
    "ARTERIOVENOUS",
    "CLIPPING",
    "EMBOLIZATION",
    "EMBOLIZE",
    "VENTRICULOSTOMY",
    "ENCEPHALOCELE",
)
THORACIC_TEXT_RULE_KEYWORDS = (
    "THORACOTOMY",
    "LOBECTOMY",
    "PNEUMONECTOMY",
    "WEDGE RESECTION",
    "VATS",
    "VIDEO-ASSISTED THORACOSCOP",
    "MEDIASTINOSCOPY",
    "PLEURODESIS",
    "THYMECTOMY",
    "ESOPHAGECTOMY",
    "CHEST WALL RESECTION",
    "LUNG RESECTION",
)
THORACIC_TEXT_EXCLUDE_KEYWORDS = (
    "EPIDURAL",
    "SUBARACHNOID",
    "THORACENTESIS",
    "BRONCHOSCOPY",
    "INTERBODY",
    "VERTEBR",
    "SPINE",
)
VASCULAR_TEXT_RULE_KEYWORDS = (
    "ENDARTERECTOMY",
    "CAROTID",
    "AAA",
    "AORTIC ANEURYSM",
    "AORTA",
    "AORTIC",
    "EVAR",
    "TEVAR",
    "FEVAR",
    "AXILLOFEMORAL",
    "AORTOBIFEMORAL",
    "FEMORAL-POPLITEAL",
    "FEMORAL POPLITEAL",
    "POPLITEAL",
    "ILIAC",
    "THROMBECTOMY",
    "EMBOLECTOMY",
    "BYPASS GRAFT",
    "ARTERIAL BYPASS",
    "ANGIOGRAPHY",
    "ANGIOGRAM",
)
VASCULAR_TEXT_EXCLUDE_KEYWORDS = (
    "PACEMAKER",
    "DEFIBRILLATOR",
    "ICD",
    "ELECTROPHYSIOLOG",
    "EP ",
    "VASC ACCESS",
    "LYMPHANGIOGRAPHY",
    "MICROVASCULAR",
    "CUTANEOUS VASCULAR",
    "VASCULAR FLOW FLAP",
    "CT ANGIO",
)
THORACIC_SERVICE_RULE_KEYWORDS = ("THOR",)
THORACIC_SERVICE_EXCLUDE_KEYWORDS = ("CARD",)
VASCULAR_SERVICE_RULE_KEYWORDS = (
    "VASC",
    "VASCSURG",
    "ANGIOGRAPHY",
    "ANGIOGRAM",
)
THORACIC_FEATURE_KEYWORDS = (
    "THORACOTOMY",
    "LOBECTOMY",
    "PNEUMONECTOMY",
    "WEDGE RESECTION",
    "MEDIASTINOSCOPY",
    "VATS",
)
VASCULAR_FEATURE_KEYWORDS = (
    "AORT",
    "CAROTID",
    "ENDARTERECTOMY",
    "EVAR",
    "TEVAR",
    "FEVAR",
    "POPLITEAL",
    "ILIAC",
    "EMBOLECTOMY",
    "THROMBECTOMY",
)
ELECTROPHYSIOLOGY_FEATURE_KEYWORDS = (
    "PACEMAKER",
    "DEFIBRILLATOR",
    "ICD",
    "ELECTROPHYSIOLOG",
    "ABLATION",
)
BRONCHOSCOPY_FEATURE_KEYWORDS = ("BRONCHOSCOPY", "THORACENTESIS")
NEURAXIAL_FEATURE_KEYWORDS = ("EPIDURAL", "SUBARACHNOID", "INTRATHECAL", "CSE")


# ============================================================================
# PROCEDURE CATEGORIZATION RULES
# ============================================================================
# Rules are evaluated in priority order (first match wins)
PROCEDURE_RULES = [
    # Cardiac procedures
    ProcedureRule(
        keywords=CARDIAC_SERVICE_RULE_KEYWORDS,
        category="Cardiac",
    ),
    # Intracerebral/neurosurgery procedures (exclude spine procedures)
    ProcedureRule(
        keywords=("NEURO",),
        category="Intracerebral",
        exclude_keywords=SPINE_EXCLUDE_KEYWORDS,
    ),
    # Intrathoracic non-cardiac (exclude cardiac thoracic cases)
    ProcedureRule(
        keywords=THORACIC_SERVICE_RULE_KEYWORDS,
        category="Intrathoracic non-cardiac",
        exclude_keywords=THORACIC_SERVICE_EXCLUDE_KEYWORDS,
    ),
    # Major vascular procedures
    ProcedureRule(
        keywords=VASCULAR_SERVICE_RULE_KEYWORDS,
        category="Procedures Major Vessels",
    ),
    # Transplant procedures
    ProcedureRule(
        keywords=("TRANSPLANT",),
        category="Other (procedure cat)",
    ),
    # OB/GYN - Special handling in processors.py
    # Cesarean deliveries are detected by searching procedure text for:
    # "CESAREAN", "C-SECTION", or "C SECTION"
    # and categorized separately as "Cesarean del"
    # Other OB/GYN procedures fall into "Other (procedure cat)"
]

# Default category when no rules match
DEFAULT_PROCEDURE_CATEGORY = "Other (procedure cat)"


# ============================================================================
# PROCEDURE TEXT FALLBACK RULES
# ============================================================================
# These are intentionally narrower than PROCEDURE_RULES because they operate on
# raw procedure text rather than controlled service names.
PROCEDURE_TEXT_RULES = [
    ProcedureRule(
        keywords=CARDIAC_TEXT_RULE_KEYWORDS,
        category="Cardiac",
    ),
    ProcedureRule(
        keywords=INTRACEREBRAL_TEXT_RULE_KEYWORDS,
        category="Intracerebral",
        exclude_keywords=SPINE_EXCLUDE_KEYWORDS,
    ),
    ProcedureRule(
        keywords=THORACIC_TEXT_RULE_KEYWORDS,
        category="Intrathoracic non-cardiac",
        exclude_keywords=THORACIC_TEXT_EXCLUDE_KEYWORDS,
    ),
    ProcedureRule(
        keywords=VASCULAR_TEXT_RULE_KEYWORDS,
        category="Procedures Major Vessels",
        exclude_keywords=VASCULAR_TEXT_EXCLUDE_KEYWORDS,
    ),
]
