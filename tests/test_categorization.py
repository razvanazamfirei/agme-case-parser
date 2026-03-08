"""Tests for procedure categorization and approach detection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from case_parser.domain import ProcedureCategory
from case_parser.patterns.approach_patterns import (
    detect_approach,
    detect_intracerebral_pathology,
)
from case_parser.patterns.categorization import (
    _apply_rule_category,
    _fallback_categories_from_text,
    _normalize_services,
    categorize_cardiac,
    categorize_intracerebral,
    categorize_obgyn,
    categorize_procedure,
    categorize_vascular,
)


class TestDetectApproach:
    def test_returns_unknown_for_none(self):
        assert detect_approach(None) == "unknown"

    def test_returns_unknown_for_empty_string(self):
        assert detect_approach("") == "unknown"

    def test_detects_endovascular_keyword(self):
        assert detect_approach("ENDOVASCULAR REPAIR AAA") == "endovascular"

    def test_detects_percutaneous_keyword(self):
        assert detect_approach("PERCUTANEOUS INTERVENTION") == "endovascular"

    def test_detects_open_keyword(self):
        assert detect_approach("OPEN AORTIC REPAIR") == "open"

    def test_endovascular_wins_when_both_present_with_explicit_keyword(self):
        # "ENDOVASCULAR" explicit + "REPAIR" in OPEN_KEYWORDS → endovascular wins
        assert detect_approach("ENDOVASCULAR REPAIR") == "endovascular"

    def test_returns_unknown_when_both_present_without_explicit(self):
        # "STENT" (endovascular, not the explicit "ENDOVASCULAR"/"PERCUTANEOUS") + "OPEN" → unknown
        assert detect_approach("OPEN STENT PLACEMENT") == "unknown"


class TestDetectIntracerebralPathology:
    def test_returns_unknown_for_none(self):
        assert detect_intracerebral_pathology(None) == "unknown"

    def test_returns_vascular_for_vascular_keywords(self):
        assert detect_intracerebral_pathology("AVM CLIPPING") == "vascular"

    def test_returns_nonvascular_for_tumor(self):
        assert detect_intracerebral_pathology("TUMOR RESECTION") == "nonvascular"

    def test_returns_unknown_for_both_keywords(self):
        # Both "ANEURYSM" (vascular) and "TUMOR" (nonvascular) → unknown
        assert detect_intracerebral_pathology("ANEURYSM WITH TUMOR") == "unknown"

    def test_returns_unknown_for_neither(self):
        assert detect_intracerebral_pathology("BRAIN SURGERY") == "unknown"


class TestCategorizeCardiac:
    def test_defaults_to_with_cpb_when_ambiguous(self):
        assert categorize_cardiac("HEART SURGERY") == ProcedureCategory.CARDIAC_WITH_CPB

    def test_detects_without_cpb_keywords(self):
        assert (
            categorize_cardiac("OFF PUMP CORONARY")
            == ProcedureCategory.CARDIAC_WITHOUT_CPB
        )

    def test_with_cpb_keyword(self):
        assert (
            categorize_cardiac("CORONARY ARTERY BYPASS")
            == ProcedureCategory.CARDIAC_WITH_CPB
        )

    def test_no_cpb_wins_when_both_present(self):
        # "OFF-PUMP" is a no-CPB keyword; "BYPASS" is a CPB keyword — no-CPB takes precedence
        assert (
            categorize_cardiac("OFF-PUMP BYPASS")
            == ProcedureCategory.CARDIAC_WITHOUT_CPB
        )


class TestCategorizeVascular:
    def test_endovascular_approach(self):
        assert (
            categorize_vascular("ENDOVASCULAR REPAIR AAA")
            == ProcedureCategory.MAJOR_VESSELS_ENDOVASCULAR
        )

    def test_open_approach(self):
        assert (
            categorize_vascular("OPEN AORTIC REPAIR")
            == ProcedureCategory.MAJOR_VESSELS_OPEN
        )

    def test_unknown_approach_defaults_to_open(self):
        assert (
            categorize_vascular("VASCULAR SURGERY")
            == ProcedureCategory.MAJOR_VESSELS_OPEN
        )


class TestCategorizeIntracerebral:
    def test_endovascular_approach(self):
        assert (
            categorize_intracerebral("ENDOVASCULAR COILING ANEURYSM")
            == ProcedureCategory.INTRACEREBRAL_ENDOVASCULAR
        )

    def test_open_vascular(self):
        # CRANIOTOMY (open) + ANEURYSM (vascular pathology)
        assert (
            categorize_intracerebral("CRANIOTOMY FOR ANEURYSM CLIPPING")
            == ProcedureCategory.INTRACEREBRAL_VASCULAR_OPEN
        )

    def test_open_nonvascular(self):
        # CRANIOTOMY (open) + TUMOR (nonvascular pathology)
        assert (
            categorize_intracerebral("CRANIOTOMY FOR TUMOR RESECTION")
            == ProcedureCategory.INTRACEREBRAL_NONVASCULAR_OPEN
        )

    def test_open_unknown_pathology_defaults_to_vascular(self):
        # CRANIOTOMY (open) + no pathology keywords → defaults to INTRACEREBRAL_VASCULAR_OPEN
        assert (
            categorize_intracerebral("CRANIOTOMY BRAIN SURGERY")
            == ProcedureCategory.INTRACEREBRAL_VASCULAR_OPEN
        )

    def test_unknown_approach_defaults_to_nonvascular_open(self):
        # No open or endovascular keywords → unknown approach → INTRACEREBRAL_NONVASCULAR_OPEN
        assert (
            categorize_intracerebral("BRAIN SURGERY")
            == ProcedureCategory.INTRACEREBRAL_NONVASCULAR_OPEN
        )


class TestCategorizeObgyn:
    def test_cesarean_detection(self):
        assert categorize_obgyn("C-SECTION DELIVERY") == ProcedureCategory.CESAREAN

    def test_vaginal_delivery(self):
        assert (
            categorize_obgyn("VAGINAL DELIVERY") == ProcedureCategory.VAGINAL_DELIVERY
        )

    def test_labor_epidural_returns_vaginal_delivery(self):
        # "LABOR EPIDURAL" is in vaginal_keywords → VAGINAL_DELIVERY
        assert categorize_obgyn("LABOR EPIDURAL") == ProcedureCategory.VAGINAL_DELIVERY

    def test_null_input_returns_other(self):
        assert categorize_obgyn("") == ProcedureCategory.OTHER


class TestFallbackCategoriesFromText:
    def test_first_matching_rule_wins(self):
        # "CARDIAC" matches the cardiac rule first
        categories = _fallback_categories_from_text("CARDIAC SURGERY")
        assert len(categories) == 1
        assert categories[0] == ProcedureCategory.CARDIAC_WITH_CPB

    def test_exclusion_prevents_match(self):
        # "NEURO" matches Intracerebral rule but "SPINE" is an exclude_keyword → rule skipped
        # No other rule matches "NEUROSPINE FUSION" → categorize_obgyn → OTHER → empty list
        categories = _fallback_categories_from_text("NEUROSURGERY SPINE FUSION")
        assert categories == []

    def test_falls_back_to_obgyn_when_no_rule_matches(self):
        # No PROCEDURE_RULES keyword matches "LABOR EPIDURAL"
        # → categorize_obgyn("LABOR EPIDURAL") → VAGINAL_DELIVERY
        categories = _fallback_categories_from_text("LABOR EPIDURAL")
        assert len(categories) == 1
        assert categories[0] == ProcedureCategory.VAGINAL_DELIVERY

    def test_returns_empty_when_nothing_matches(self):
        categories = _fallback_categories_from_text("ROUTINE CHECKUP")
        assert categories == []


class TestCategorizeProcedure:
    def test_none_procedure_returns_other(self):
        category, warnings = categorize_procedure(None, [])
        assert category == ProcedureCategory.OTHER
        assert warnings == []

    def test_service_match_wins(self):
        category, warnings = categorize_procedure("Heart surgery", ["CARDIAC"])
        assert category == ProcedureCategory.CARDIAC_WITH_CPB
        assert warnings == []

    def test_multiple_categories_generates_warning(self):
        _category, warnings = categorize_procedure(
            "Complex surgery", ["CARDIAC", "VASC"]
        )
        assert len(warnings) == 1
        assert "Multiple procedure categories" in warnings[0]

    def test_single_match_no_warning(self):
        category, warnings = categorize_procedure("Lung surgery", ["THOR"])
        assert category == ProcedureCategory.INTRATHORACIC_NON_CARDIAC
        assert warnings == []

    def test_no_match_falls_back_to_other(self):
        category, _warnings = categorize_procedure(
            "Something random", ["UNKNOWN_SERVICE"]
        )
        assert category == ProcedureCategory.OTHER

    def test_non_ob_service_does_not_create_obgyn_warning(self):
        category, warnings = categorize_procedure(
            "Heart surgery", ["CARDIAC", "OBSERVATION"]
        )
        assert category == ProcedureCategory.CARDIAC_WITH_CPB
        assert warnings == []

    def test_apply_rule_category_cardiac(self):
        result = _apply_rule_category("Cardiac", "OFF PUMP CABG")
        assert result == ProcedureCategory.CARDIAC_WITHOUT_CPB

    def test_apply_rule_category_vascular(self):
        result = _apply_rule_category("Procedures Major Vessels", "OPEN REPAIR")
        assert result == ProcedureCategory.MAJOR_VESSELS_OPEN

    def test_apply_rule_category_intracerebral(self):
        result = _apply_rule_category("Intracerebral", "ENDOVASCULAR COILING")
        assert result == ProcedureCategory.INTRACEREBRAL_ENDOVASCULAR

    def test_apply_rule_category_intrathoracic(self):
        result = _apply_rule_category("Intrathoracic non-cardiac", "LUNG RESECTION")
        assert result == ProcedureCategory.INTRATHORACIC_NON_CARDIAC


def test_normalize_services_skips_null_and_string_sentinels():
    assert _normalize_services(["cardiac", None, np.nan, pd.NA, "nan", "None", "<NA>"]) == (
        "CARDIAC",
    )
