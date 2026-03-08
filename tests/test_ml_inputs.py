"""Tests for shared ML feature-input helpers."""

from __future__ import annotations

from collections import UserDict

import pandas as pd
import pytest

from case_parser.ml.inputs import (
    FeatureInput,
    build_feature_inputs,
    feature_input_from_raw,
    resolve_service_column,
)


def test_build_feature_inputs_normalizes_parallel_metadata():
    result = build_feature_inputs(
        ["CABG"],
        services_list=[["CARDIAC", "THORACIC"]],
        rule_categories=["Other (procedure cat)"],
        rule_warning_counts=[2],
    )

    assert result == [
        FeatureInput(
            procedure_text="CABG",
            service_text="CARDIAC\nTHORACIC",
            rule_category="Other (procedure cat)",
            rule_warning_count=2,
        )
    ]


def test_feature_input_from_raw_handles_dict_aliases_and_missing_values():
    result = feature_input_from_raw({
        "procedure": None,
        "services": ["CARDIAC", None],
        "rule_warning_count": "3",
    })

    assert result == FeatureInput(
        procedure_text="",
        service_text="CARDIAC",
        rule_category="",
        rule_warning_count=3,
    )


def test_feature_input_from_raw_uses_service_alias_fallbacks():
    result = feature_input_from_raw({
        "procedure": "CABG",
        "service_text": None,
        "Service": ["CARDIAC", None],
    })

    assert result == FeatureInput(
        procedure_text="CABG",
        service_text="CARDIAC",
        rule_category="",
        rule_warning_count=0,
    )


def test_feature_input_from_raw_handles_mapping_types():
    result = feature_input_from_raw(
        UserDict({"procedure": "CABG", "services": ["CARDIAC", None]})
    )

    assert result == FeatureInput(
        procedure_text="CABG",
        service_text="CARDIAC",
        rule_category="",
        rule_warning_count=0,
    )


def test_rule_warning_count_normalization_falls_back_to_zero():
    raw_result = feature_input_from_raw({
        "procedure": "CABG",
        "rule_warning_count": "",
    })
    batch_result = build_feature_inputs(
        ["CABG"],
        rule_warning_counts=["invalid"],
    )

    assert raw_result.rule_warning_count == 0
    assert batch_result[0].rule_warning_count == 0


def test_resolve_service_column_honors_requested_or_falls_back():
    df = pd.DataFrame(columns=["procedure", "Services", "custom_services"])

    assert resolve_service_column(df, "custom_services") == "custom_services"
    assert resolve_service_column(df, "missing_column") is None
    assert resolve_service_column(df) == "Services"


def test_build_feature_inputs_rejects_mismatched_parallel_metadata():
    with pytest.raises(ValueError, match="services_list must match"):
        build_feature_inputs(["a", "b"], services_list=[["CARDIAC"]])
