"""Tests for ML feature extraction behavior."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse import csr_matrix, hstack

from case_parser.domain import ProcedureCategory
from case_parser.ml.features import FeatureExtractor
from case_parser.ml.inputs import FeatureInput, normalize_feature_inputs


def test_transform_preserves_output_when_duplicate_texts_have_distinct_metadata():
    extractor = FeatureExtractor().fit([
        FeatureInput(procedure_text="CABG x3", service_text="CARDIAC"),
        FeatureInput(procedure_text="CABG x4", service_text="CARDIAC"),
        FeatureInput(procedure_text="Craniotomy", service_text="NEURO"),
        FeatureInput(procedure_text="Thoracotomy", service_text="THORACIC"),
    ])
    inputs = [
        FeatureInput(
            procedure_text="CABG x3",
            service_text="CARDIAC",
            rule_category="Other (procedure cat)",
            rule_warning_count=0,
        ),
        FeatureInput(
            procedure_text="CABG x3",
            service_text="CARDIAC",
            rule_category="Cardiac Surgery with CPB",
            rule_warning_count=2,
        ),
        FeatureInput(
            procedure_text="Craniotomy",
            service_text="NEURO",
            rule_category="Intracerebral procedure",
            rule_warning_count=1,
        ),
    ]

    actual = extractor.transform(inputs).toarray()

    normalized_inputs = normalize_feature_inputs(inputs)
    texts = [extractor._compose_text(item) for item in normalized_inputs]
    expected = hstack([
        extractor.tfidf_word.transform(texts),
        extractor.tfidf_char.transform(texts),
        csr_matrix(
            np.array([
                extractor._extract_structured_single_v2_cached(
                    item.procedure_text,
                    item.service_text,
                    item.rule_category,
                    int(item.rule_warning_count),
                )
                for item in normalized_inputs
            ])
        ),
    ]).toarray()

    np.testing.assert_allclose(actual, expected)


def test_dedupe_preserve_order_returns_inverse_indices():
    unique_values, inverse_indices = FeatureExtractor._dedupe_preserve_order([
        "alpha",
        "beta",
        "alpha",
        "gamma",
        "beta",
    ])

    assert unique_values == ["alpha", "beta", "gamma"]
    assert inverse_indices.tolist() == [0, 1, 0, 2, 1]


def test_transform_uses_float32_feature_matrices():
    extractor = FeatureExtractor().fit([
        FeatureInput(procedure_text="CABG x3", service_text="CARDIAC"),
        FeatureInput(procedure_text="Craniotomy", service_text="NEURO"),
        FeatureInput(procedure_text="Thoracotomy", service_text="THORACIC"),
        FeatureInput(procedure_text="Cesarean section", service_text="OB"),
    ])

    matrix = extractor.transform([
        FeatureInput(procedure_text="CABG x3", service_text="CARDIAC"),
        FeatureInput(procedure_text="Craniotomy", service_text="NEURO"),
    ])

    assert matrix.dtype == np.float32


@pytest.mark.parametrize(
    ("rule_category", "feature_index"),
    [
        (ProcedureCategory.INTRACEREBRAL_ENDOVASCULAR.value, -4),
        (ProcedureCategory.MAJOR_VESSELS_ENDOVASCULAR.value, -3),
        (ProcedureCategory.INTRATHORACIC_NON_CARDIAC.value, -2),
        (ProcedureCategory.CESAREAN.value.lower(), -1),
    ],
)
def test_extract_structured_v2_normalizes_rule_category_casing(
    rule_category: str,
    feature_index: int,
):
    features = FeatureExtractor._extract_structured_single_v2_cached(
        "placeholder procedure",
        "",
        rule_category,
        0,
    )

    assert features[feature_index] == 1
