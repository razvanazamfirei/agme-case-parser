"""Shared configuration constants for the ML categorization pipeline."""

from __future__ import annotations

import os
import warnings
from collections.abc import Mapping
from typing import Any

BASE_DEFAULT_ML_THRESHOLD = 0.45
BASE_DEFAULT_ML_INFERENCE_JOBS = 1
ML_THRESHOLD_ENV_VAR = "CASE_PARSER_ML_THRESHOLD"
ML_INFERENCE_JOBS_ENV_VAR = "CASE_PARSER_ML_INFERENCE_JOBS"
SERVICE_COLUMN_CANDIDATES = (
    "service_text",
    "services",
    "service",
    "Service",
    "Services",
)


def get_default_ml_threshold(environ: Mapping[str, str] | None = None) -> float:
    """Return the configured default ML threshold.

    Reads ``CASE_PARSER_ML_THRESHOLD`` when present. Invalid values fall back to
    the built-in default and emit a warning rather than breaking import-time
    initialization.
    """
    env = os.environ if environ is None else environ
    raw_value = env.get(ML_THRESHOLD_ENV_VAR)
    if raw_value is None or not raw_value.strip():
        return BASE_DEFAULT_ML_THRESHOLD

    try:
        threshold = float(raw_value)
    except ValueError:
        warnings.warn(
            f"Ignoring invalid {ML_THRESHOLD_ENV_VAR} value {raw_value!r}; "
            f"using {BASE_DEFAULT_ML_THRESHOLD:.2f}.",
            stacklevel=2,
        )
        return BASE_DEFAULT_ML_THRESHOLD

    if not 0.0 <= threshold <= 1.0:
        warnings.warn(
            f"Ignoring out-of-range {ML_THRESHOLD_ENV_VAR} value {raw_value!r}; "
            f"using {BASE_DEFAULT_ML_THRESHOLD:.2f}.",
            stacklevel=2,
        )
        return BASE_DEFAULT_ML_THRESHOLD

    return threshold


def get_default_ml_inference_jobs(environ: Mapping[str, str] | None = None) -> int:
    """Return the configured inference-time sklearn ``n_jobs`` value.

    Reads ``CASE_PARSER_ML_INFERENCE_JOBS`` when present. Accepts ``-1`` for
    all available cores or any positive integer. Invalid values fall back to the
    built-in default and emit a warning.
    """
    env = os.environ if environ is None else environ
    return normalize_ml_inference_jobs(
        env.get(ML_INFERENCE_JOBS_ENV_VAR),
        source_name=ML_INFERENCE_JOBS_ENV_VAR,
    )


def normalize_ml_inference_jobs(
    raw_value: Any,
    *,
    source_name: str = ML_INFERENCE_JOBS_ENV_VAR,
) -> int:
    """Normalize a configured sklearn ``n_jobs`` override."""
    if raw_value is None:
        return BASE_DEFAULT_ML_INFERENCE_JOBS

    if isinstance(raw_value, str):
        raw_text = raw_value.strip()
        if not raw_text:
            return BASE_DEFAULT_ML_INFERENCE_JOBS
        candidate_value: Any = raw_text
    else:
        candidate_value = raw_value

    try:
        jobs = int(candidate_value)
    except (TypeError, ValueError):
        warnings.warn(
            f"Ignoring invalid {source_name} value {raw_value!r}; "
            f"using {BASE_DEFAULT_ML_INFERENCE_JOBS}.",
            stacklevel=2,
        )
        return BASE_DEFAULT_ML_INFERENCE_JOBS

    if jobs == 0 or jobs < -1:
        warnings.warn(
            f"Ignoring out-of-range {source_name} value {raw_value!r}; "
            f"using {BASE_DEFAULT_ML_INFERENCE_JOBS}.",
            stacklevel=2,
        )
        return BASE_DEFAULT_ML_INFERENCE_JOBS

    return jobs


DEFAULT_ML_THRESHOLD = get_default_ml_threshold()
DEFAULT_ML_INFERENCE_JOBS = get_default_ml_inference_jobs()
