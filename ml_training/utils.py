"""Shared utilities for ML training tools."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

from case_parser.domain import ProcedureCategory

# Canonical category order used in labeling/review tools.
CATEGORIES = [
    ProcedureCategory.CARDIAC_WITH_CPB.value,
    ProcedureCategory.CARDIAC_WITHOUT_CPB.value,
    ProcedureCategory.MAJOR_VESSELS_ENDOVASCULAR.value,
    ProcedureCategory.MAJOR_VESSELS_OPEN.value,
    ProcedureCategory.INTRACEREBRAL_ENDOVASCULAR.value,
    ProcedureCategory.INTRACEREBRAL_VASCULAR_OPEN.value,
    ProcedureCategory.INTRACEREBRAL_NONVASCULAR_OPEN.value,
    ProcedureCategory.CESAREAN.value,
    ProcedureCategory.VAGINAL_DELIVERY.value,
    ProcedureCategory.INTRATHORACIC_NON_CARDIAC.value,
    ProcedureCategory.OTHER.value,
]

CATEGORY_MAP = {str(i + 1): cat for i, cat in enumerate(CATEGORIES)}


def normalize_category_label(category: str | None) -> str:
    """Normalize category labels to canonical enum values.

    Args:
        category: Input category label to normalize, or None for unknown/other.
    Returns:
        Canonical category string from ProcedureCategory enum values.
    """
    if category is None:
        return ProcedureCategory.OTHER.value
    normalized = category.strip()
    if normalized.startswith("ProcedureCategory."):
        member_name = normalized.split(".", 1)[1]
        if member_name in ProcedureCategory.__members__:
            return ProcedureCategory[member_name].value
    return normalized


def get_category_from_input(user_input: str) -> str | None:
    """Convert user input to category.

    Args:
        user_input: User input (number or category name)

    Returns:
        Category string or None if invalid
    """
    normalized_input = normalize_category_label(user_input)

    # Try as number first
    if user_input in CATEGORY_MAP:
        return CATEGORY_MAP[user_input]

    # Try as full category name
    if normalized_input in CATEGORIES:
        return normalized_input

    return None


def run_python_script(script_path: Path, argv: list[str]) -> int:
    """Run a Python script in-process and return its exit code.

    Args:
        script_path: Path to the Python script to execute.
        argv: Command-line arguments to pass to the script.

    Returns:
        Exit code from the script's SystemExit, or 0 if the script completes
        without raising SystemExit.
    """
    original_argv = sys.argv[:]
    sys.argv = [str(script_path), *argv]
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return 0 if exc.code is None else 1
    finally:
        sys.argv = original_argv
    return 0


PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CASE_DIR = PROJECT_ROOT / "Output-Supervised" / "case-list"
DEFAULT_PREPARED_DATA = PROJECT_ROOT / "ml_training_data" / "batch_prepared.csv"
DEFAULT_SEEN_DATA = PROJECT_ROOT / "ml_training_data" / "seen_train.csv"
DEFAULT_UNSEEN_DATA = PROJECT_ROOT / "ml_training_data" / "unseen_eval.csv"
DEFAULT_MODEL_OUTPUT = PROJECT_ROOT / "ml_models" / "procedure_classifier.pkl"
