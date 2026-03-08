"""Tests for ML batch preparation helpers."""

from __future__ import annotations

import pandas as pd

from case_parser.domain import ProcedureCategory
from ml_training import batch_prepare


def test_process_single_file_uses_exported_service_text_for_rule_categorization(
    tmp_path,
    monkeypatch,
):
    csv_path = tmp_path / "cases.csv"
    pd.DataFrame([
        {
            "AIMS_Actual_Procedure_Text": "CABG",
            "service_text": "CARDIAC\nTHOR",
        }
    ]).to_csv(csv_path, index=False)

    captured: dict[str, object] = {}

    def fake_categorize_procedure(procedure, services):
        """
        Test helper that records the provided procedure and services, and returns a fixed cardiac category with no additional data.
        
        Parameters:
            procedure: The procedure text passed for categorization; recorded in the outer `captured` dict under "procedure".
            services: The list of service strings passed for categorization; recorded in the outer `captured` dict under "services".
        
        Returns:
            tuple: (`ProcedureCategory.CARDIAC_WITH_CPB`, `[]`)
        """
        captured["procedure"] = procedure
        captured["services"] = services
        return ProcedureCategory.CARDIAC_WITH_CPB, []

    monkeypatch.setattr(
        batch_prepare,
        "categorize_procedure",
        fake_categorize_procedure,
    )

    result = batch_prepare.process_single_file(csv_path)

    assert result["valid_cases"] == 1
    assert captured == {
        "procedure": "CABG",
        "services": ["CARDIAC", "THOR"],
    }
    assert result["cases"][0]["service_text"] == "CARDIAC\nTHOR"
    assert result["cases"][0]["rule_category"] == (
        ProcedureCategory.CARDIAC_WITH_CPB.value
    )
