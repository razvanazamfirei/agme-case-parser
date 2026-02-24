"""Tests for CSV v2 format I/O operations."""

import pandas as pd
import pytest

from case_parser.io import (
    CsvHandler,
    discover_csv_pairs,
    join_case_and_procedures,
)
from case_parser.models import ColumnMap


def test_discover_csv_pairs_finds_matching_files(tmp_path):
    """Test discovery of matching CaseList and ProcedureList files."""
    # Create test files
    (tmp_path / "ASTEAK, MATTHEW.Supervised.CaseList.csv").touch()
    (tmp_path / "ASTEAK, MATTHEW.Supervised.ProcedureList.csv").touch()

    pairs = discover_csv_pairs(tmp_path)

    assert len(pairs) == 1
    case_file, proc_file = pairs[0]
    assert case_file.name == "ASTEAK, MATTHEW.Supervised.CaseList.csv"
    assert proc_file.name == "ASTEAK, MATTHEW.Supervised.ProcedureList.csv"


def test_discover_csv_pairs_multiple_pairs(tmp_path):
    """Test discovery of multiple matching pairs."""
    (tmp_path / "DOCTOR1.CaseList.csv").touch()
    (tmp_path / "DOCTOR1.ProcedureList.csv").touch()
    (tmp_path / "DOCTOR2.CaseList.csv").touch()
    (tmp_path / "DOCTOR2.ProcedureList.csv").touch()

    pairs = discover_csv_pairs(tmp_path)

    assert len(pairs) == 2
    prefixes = {p[0].name.replace(".CaseList.csv", "") for p in pairs}
    assert prefixes == {"DOCTOR1", "DOCTOR2"}


def test_discover_csv_pairs_no_pairs_raises_error(tmp_path):
    """Test error when no matching pairs found."""
    with pytest.raises(ValueError, match="No matching CSV pairs found"):
        discover_csv_pairs(tmp_path)


def test_discover_csv_pairs_unpaired_files_warns(tmp_path, caplog):
    """Test warning when unpaired files found."""
    (tmp_path / "DOCTOR1.CaseList.csv").touch()
    (tmp_path / "DOCTOR2.ProcedureList.csv").touch()

    with pytest.raises(ValueError, match="No matching CSV pairs found"):
        discover_csv_pairs(tmp_path)

    assert "unpaired" in caplog.text.lower()


def test_normalize_csv_columns_populates_procedure_notes_from_airway_type():
    """CSV v2 airway value should be available for downstream airway extraction."""
    csv_df = pd.DataFrame(
        {
            "MPOG_Case_ID": ["abc-123"],
            "AIMS_Scheduled_DT": ["2025-01-01 08:00:00"],
            "AIMS_Patient_Age_Years": [42],
            "ASA_Status": [2],
            "AIMS_Actual_Procedure_Text": ["Appendectomy"],
            "Airway_Type": ["Intubation routine"],
            "AnesAttendings": ["DOE, JANE@2025-01-01 08:00:00"],
        }
    )
    column_map = ColumnMap()

<<<<<<< HEAD
    result = CsvHandler(column_map).normalize_columns(csv_df)
||||||| parent of 8cb903d (refactor: consolidate csv_io into io.py and introduce CsvHandler class)
    result = map_csv_to_standard_columns(csv_df, column_map)
=======
    result = CsvHandler(column_map)._normalize_columns(csv_df)
>>>>>>> 8cb903d (refactor: consolidate csv_io into io.py and introduce CsvHandler class)

    assert result.loc[0, column_map.final_anesthesia_type] == "Intubation routine"
    assert result.loc[0, column_map.procedure_notes] == "Intubation routine"


# --- join_case_and_procedures orphan detection ---


def _make_case_df(*case_ids):
    """Build a minimal CaseList DataFrame with the given MPOG_Case_IDs."""
    return pd.DataFrame({"MPOG_Case_ID": list(case_ids)})


def _make_proc_df(*rows):
    """Build a ProcedureList DataFrame from (MPOG_Case_ID, ProcedureName) pairs."""
    return pd.DataFrame(rows, columns=["MPOG_Case_ID", "ProcedureName"])


def test_join_returns_no_orphans_when_all_matched():
    case_df = _make_case_df("C1", "C2")
    proc_df = _make_proc_df(("C1", "Intubation routine"), ("C2", "Epidural"))

    joined, orphans = join_case_and_procedures(case_df, proc_df)

    assert len(joined) == 2
    assert orphans.empty


def test_join_detects_orphan_procedures():
    case_df = _make_case_df("C1")
    proc_df = _make_proc_df(
        ("C1", "Intubation routine"),
        ("ORPHAN-1", "Labor Epidural"),
        ("ORPHAN-2", "Peripheral nerve block"),
    )

    joined, orphans = join_case_and_procedures(case_df, proc_df)

    assert len(joined) == 1
    assert len(orphans) == 2
    assert set(orphans["MPOG_Case_ID"]) == {"ORPHAN-1", "ORPHAN-2"}
    assert set(orphans["ProcedureName"]) == {"Labor Epidural", "Peripheral nerve block"}


def test_join_with_empty_proc_df():
    case_df = _make_case_df("C1")
    proc_df = pd.DataFrame(columns=["MPOG_Case_ID", "ProcedureName"])

    joined, orphans = join_case_and_procedures(case_df, proc_df)

    assert len(joined) == 1
    assert orphans.empty


# --- normalize_orphan_columns ---

<<<<<<< HEAD

||||||| parent of 8cb903d (refactor: consolidate csv_io into io.py and introduce CsvHandler class)
def test_map_orphan_procedures_maps_required_columns():
=======
>>>>>>> 8cb903d (refactor: consolidate csv_io into io.py and introduce CsvHandler class)
def test_normalize_orphan_columns_maps_required_columns():
    column_map = ColumnMap()
    orphan_df = _make_proc_df(
        ("ORPHAN-1", "Labor Epidural"),
        ("ORPHAN-2", "Peripheral nerve block"),
    )

<<<<<<< HEAD
    result = CsvHandler(column_map).normalize_orphan_columns(orphan_df)
||||||| parent of 8cb903d (refactor: consolidate csv_io into io.py and introduce CsvHandler class)
    result = map_orphan_procedures(orphan_df, column_map)
=======
    result = CsvHandler(column_map)._normalize_orphan_columns(orphan_df)
>>>>>>> 8cb903d (refactor: consolidate csv_io into io.py and introduce CsvHandler class)

    assert list(result[column_map.episode_id]) == ["ORPHAN-1", "ORPHAN-2"]
    assert list(result[column_map.procedure]) == [
        "Labor Epidural",
        "Peripheral nerve block",
    ]
    assert list(result[column_map.final_anesthesia_type]) == [
        "Labor Epidural",
        "Peripheral nerve block",
    ]
    assert list(result[column_map.procedure_notes]) == [
        "Labor Epidural",
        "Peripheral nerve block",
    ]


def test_normalize_orphan_columns_fills_na_for_demographics():
    column_map = ColumnMap()
    orphan_df = _make_proc_df(("ORPHAN-1", "Labor Epidural"))

<<<<<<< HEAD
    result = CsvHandler(column_map).normalize_orphan_columns(orphan_df)
||||||| parent of 8cb903d (refactor: consolidate csv_io into io.py and introduce CsvHandler class)
    result = map_orphan_procedures(orphan_df, column_map)
=======
    result = CsvHandler(column_map)._normalize_orphan_columns(orphan_df)
>>>>>>> 8cb903d (refactor: consolidate csv_io into io.py and introduce CsvHandler class)

    assert pd.isna(result.loc[0, column_map.date])
    assert pd.isna(result.loc[0, column_map.age])
    assert pd.isna(result.loc[0, column_map.asa])
