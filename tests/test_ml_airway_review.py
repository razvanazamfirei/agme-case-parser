"""Tests for airway/anesthesia review-set generation."""

from __future__ import annotations

from datetime import date

import pandas as pd

from case_parser.domain import (
    AirwayManagement,
    AnesthesiaType,
    ParsedCase,
    ProcedureCategory,
)
from ml_training import airway_review


def _parsed_case(**overrides) -> ParsedCase:
    base = ParsedCase(
        raw_date="2025-01-01",
        episode_id="CASE-1",
        raw_age=55.0,
        raw_asa="3",
        emergent=False,
        raw_anesthesia_type="Intubation routine",
        services=["THORACIC"],
        procedure="VATS lobectomy",
        procedure_notes="Left double lumen tube placed",
        responsible_provider="SMITH, JANE",
        case_date=date(2025, 1, 1),
        anesthesia_type=AnesthesiaType.GENERAL,
        procedure_category=ProcedureCategory.INTRATHORACIC_NON_CARDIAC,
        airway_management=[
            AirwayManagement.DOUBLE_LUMEN_ETT,
            AirwayManagement.ORAL_ETT,
        ],
        parsing_warnings=[
            "Inferred general anesthesia from airway management findings"
        ],
    )
    return base.model_copy(update=overrides)


def test_assess_case_for_review_scores_all_requested_targets():
    case = _parsed_case()

    assessment = airway_review.assess_case_for_review(case, source_file="pair.csv")

    assert assessment.scores["double_lumen"] > 0
    assert assessment.scores["tube_route"] > 0
    assert assessment.scores["ga_mac"] > 0
    assert "double_lumen" in assessment.review_targets
    assert "tube_route" in assessment.review_targets
    assert "ga_mac" in assessment.review_targets


def test_build_review_record_exposes_blank_label_columns():
    case = _parsed_case()
    assessment = airway_review.assess_case_for_review(case, source_file="pair.csv")

    record = airway_review.build_review_record(
        case,
        source_file="pair.csv",
        assessment=assessment,
    )

    assert record["predicted_has_double_lumen_tube"] == "Yes"
    assert record["predicted_tube_route"] == "Oral"
    assert record["predicted_ga_mac"] == "GA"
    assert record["label_has_double_lumen_tube"] == ""
    assert record["label_ga_mac"] == ""
    assert record["label_tube_route"] == ""


def test_assess_case_for_review_does_not_treat_ldlt_as_dlt():
    case = _parsed_case(
        procedure="Liver LDLT recipient",
        procedure_category=ProcedureCategory.OTHER,
        airway_management=[],
        procedure_notes="",
        parsing_warnings=[],
    )

    assessment = airway_review.assess_case_for_review(case, source_file="pair.csv")

    assert assessment.scores["double_lumen"] == 0
    assert "explicit_double_lumen_text" not in assessment.review_reasons


def test_assess_case_for_review_does_not_use_generic_lobectomy_as_thoracic():
    case = _parsed_case(
        procedure="Total thyroid lobectomy",
        procedure_category=ProcedureCategory.INTRATHORACIC_NON_CARDIAC,
        airway_management=[],
        procedure_notes="",
        parsing_warnings=[],
    )

    assessment = airway_review.assess_case_for_review(case, source_file="pair.csv")

    assert assessment.scores["double_lumen"] == 0
    assert "thoracic_procedure_hint" not in assessment.review_reasons


def test_stable_fraction_is_strictly_less_than_one(monkeypatch):
    class _FakeHash:
        def hexdigest(self) -> str:
            return "ffffffff" + ("0" * 56)

    monkeypatch.setattr(airway_review.hashlib, "sha256", lambda _value: _FakeHash())

    assert airway_review._stable_fraction("case-key") < 1.0


def test_review_bucket_limits_sum_to_max_cases():
    limits = airway_review._review_bucket_limits(1)

    assert sum(limits.values()) == 1
    assert limits == {
        "double_lumen": 1,
        "tube_route": 0,
        "ga_mac": 0,
        "control": 0,
    }


def test_select_records_handles_zero_capacity_bucket_limits():
    bucket_limits = airway_review._review_bucket_limits(2)
    heap_limits = {
        bucket: max(limit * 4, limit)
        for bucket, limit in bucket_limits.items()
    }
    heaps = {bucket: [] for bucket in airway_review.BUCKET_ORDER}

    airway_review._push_candidate(
        heaps,
        heap_limits=heap_limits,
        record={"case_key": "CASE-A", "priority_bucket": "", "priority_score": 0.0},
        assessment=airway_review.CaseAssessment(
            scores={
                "double_lumen": 10.0,
                "tube_route": 9.0,
                "ga_mac": 8.0,
                "control": 0.0,
            },
            review_targets=("double_lumen", "tube_route", "ga_mac"),
            review_reasons=("multi_bucket_case",),
        ),
        sequence=0,
    )
    airway_review._push_candidate(
        heaps,
        heap_limits=heap_limits,
        record={"case_key": "CASE-B", "priority_bucket": "", "priority_score": 0.0},
        assessment=airway_review.CaseAssessment(
            scores={
                "double_lumen": 6.0,
                "tube_route": 0.0,
                "ga_mac": 0.0,
                "control": 0.0,
            },
            review_targets=("double_lumen",),
            review_reasons=("backfill_candidate",),
        ),
        sequence=1,
    )

    selected = airway_review._select_records(
        heaps,
        bucket_limits=bucket_limits,
        max_cases=2,
    )

    assert bucket_limits == {
        "double_lumen": 1,
        "tube_route": 1,
        "ga_mac": 0,
        "control": 0,
    }
    assert [record["case_key"] for record in selected] == ["CASE-A", "CASE-B"]
    assert selected[0]["priority_bucket"] == "double_lumen"
    assert selected[1]["priority_bucket"] == "double_lumen"


def test_select_records_can_backfill_from_zero_quota_bucket():
    bucket_limits = airway_review._review_bucket_limits(2)
    heap_limits = {
        bucket: max(limit * 4, 2 if limit == 0 else limit)
        for bucket, limit in bucket_limits.items()
    }
    heaps = {bucket: [] for bucket in airway_review.BUCKET_ORDER}

    airway_review._push_candidate(
        heaps,
        heap_limits=heap_limits,
        record={"case_key": "CASE-GA-1", "priority_bucket": "", "priority_score": 0.0},
        assessment=airway_review.CaseAssessment(
            scores={
                "double_lumen": 0.0,
                "tube_route": 0.0,
                "ga_mac": 9.0,
                "control": 0.0,
            },
            review_targets=("ga_mac",),
            review_reasons=("ga_only_candidate",),
        ),
        sequence=0,
    )
    airway_review._push_candidate(
        heaps,
        heap_limits=heap_limits,
        record={"case_key": "CASE-GA-2", "priority_bucket": "", "priority_score": 0.0},
        assessment=airway_review.CaseAssessment(
            scores={
                "double_lumen": 0.0,
                "tube_route": 0.0,
                "ga_mac": 8.0,
                "control": 0.0,
            },
            review_targets=("ga_mac",),
            review_reasons=("ga_only_candidate",),
        ),
        sequence=1,
    )

    selected = airway_review._select_records(
        heaps,
        bucket_limits=bucket_limits,
        max_cases=2,
    )

    assert bucket_limits["ga_mac"] == 0
    assert [record["case_key"] for record in selected] == [
        "CASE-GA-1",
        "CASE-GA-2",
    ]
    assert [record["priority_bucket"] for record in selected] == [
        "ga_mac",
        "ga_mac",
    ]


def test_build_airway_review_dataframe_from_supervised_pair(tmp_path):
    base_dir = tmp_path / "Output-Supervised"
    case_dir = base_dir / "case-list"
    proc_dir = base_dir / "procedure-list"
    case_dir.mkdir(parents=True)
    proc_dir.mkdir(parents=True)

    case_df = pd.DataFrame({
        "MPOG_Case_ID": ["CASE-1"],
        "AIMS_Scheduled_DT": ["2025-01-01 07:30:00"],
        "AIMS_Patient_Age_Years": [55],
        "ASA_Status": [3],
        "AIMS_Actual_Procedure_Text": ["VATS lobectomy"],
        "AnesAttendings": ["SMITH, JANE@2025-01-01 07:30:00"],
    })
    proc_df = pd.DataFrame({
        "MPOG_Case_ID": ["CASE-1"],
        "ProcedureName": ["Intubation routine"],
        "Comment": [pd.NA],
        "Details": ["Left double lumen tube placed"],
    })

    case_df.to_csv(case_dir / "TEST.Supervised.CaseList.csv", index=False)
    proc_df.to_csv(proc_dir / "TEST.Supervised.ProcedureList.csv", index=False)

    df = airway_review.build_airway_review_dataframe(
        base_dir=base_dir,
        max_cases=10,
    )

    assert len(df) == 1
    assert df.loc[0, "predicted_has_double_lumen_tube"] == "Yes"
    assert df.loc[0, "predicted_tube_route"] == "Oral"
    review_targets = str(df.loc[0, "review_targets"])
    assert "double_lumen" in review_targets
    assert df.loc[0, "label_has_double_lumen_tube"] == ""
