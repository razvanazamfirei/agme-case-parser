"""Tests for optimized ML training helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from ml_training import train_optimized


def test_extract_training_arrays_errors_on_missing_requested_service_column():
    df = pd.DataFrame({
        "procedure": ["CABG"],
        "category": ["Cardiac With CPB"],
    })

    with pytest.raises(ValueError, match="Service column not found: missing_services"):
        train_optimized._extract_training_arrays(
            df,
            label_column="category",
            service_column="missing_services",
        )
