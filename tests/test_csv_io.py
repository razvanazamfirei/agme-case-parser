"""Tests for CSV v2 format I/O operations."""

import pandas as pd
import pytest

from case_parser.io import (
    CsvHandler,
    discover_csv_pairs,
    join_case_and_procedures,
    select_primary_technique,
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
    csv_df = pd.DataFrame({
        "MPOG_Case_ID": ["abc-123"],
        "AIMS_Scheduled_DT": ["2025-01-01 08:00:00"],
        "AIMS_Patient_Age_Years": [42],
        "ASA_Status": [2],
        "AIMS_Actual_Procedure_Text": ["Appendectomy"],
        "Airway_Type": ["Intubation routine"],
        "AnesAttendings": ["DOE, JANE@2025-01-01 08:00:00"],
    })
    column_map = ColumnMap()

    result = CsvHandler(column_map).normalize_columns(csv_df)

    assert result.loc[0, column_map.final_anesthesia_type] == "Intubation routine"
    assert result.loc[0, column_map.procedure_notes] == "Intubation routine"


# --- join_case_and_procedures orphan detection ---


def _make_case_df(*case_ids):
    """Build a minimal CaseList DataFrame with the given MPOG_Case_IDs."""
    return pd.DataFrame({"MPOG_Case_ID": list(case_ids)})


def _make_proc_df(*rows):
    """Build a ProcedureList DataFrame from (MPOG_Case_ID, ProcedureName) pairs.

    Remaining ProcedureList columns are left as NaN to keep test fixtures minimal.
    """
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


def _make_full_proc_df(*rows):
    """Build a ProcedureList DataFrame with the full MPOG column schema.

    Each row should be a positional tuple matching the schema column order.
    Short rows are padded with ``NaN`` by pandas.
    """
    columns = [
        "MPOG_Case_ID",
        "AIMS_Scheduled_DT",
        "ASA_Status",
        "Emergency",
        "ProcedureName",
        "PrimaryBlock",
        "Comment",
        "Details",
        "AIMS_Actual_Procedure_Text",
        "AnesAttendingNames",
    ]
    return pd.DataFrame(rows, columns=columns)


def test_normalize_orphan_columns_maps_required_columns():
    """Procedure type and ID map correctly from ProcedureList columns."""
    column_map = ColumnMap()
    orphan_df = _make_full_proc_df(
        (
            "ORPHAN-1",
            "2024-03-01 08:00",
            2,
            0,
            "Labor Epidural",
            pd.NA,
            pd.NA,
            "performing provider details",
            "LABOR, SPONTANEOUS",
            "SMITH, JANE",
        ),
        (
            "ORPHAN-2",
            "2024-03-02 09:00",
            1,
            0,
            "Peripheral nerve block",
            "Femoral nerve block",
            pd.NA,
            pd.NA,
            "KNEE REPLACEMENT",
            "DOE, JOHN",
        ),
    )

    result = CsvHandler(column_map).normalize_orphan_columns(orphan_df)

    assert list(result[column_map.episode_id]) == ["ORPHAN-1", "ORPHAN-2"]
    # ProcedureName maps to anesthesia type hint
    assert list(result[column_map.final_anesthesia_type]) == [
        "Labor Epidural",
        "Peripheral nerve block",
    ]
    # AIMS_Actual_Procedure_Text maps to procedure
    assert list(result[column_map.procedure]) == [
        "LABOR, SPONTANEOUS",
        "KNEE REPLACEMENT",
    ]
    # PrimaryBlock maps to nerve block type
    assert pd.isna(result.loc[0, column_map.nerve_block_type])
    assert result.loc[1, column_map.nerve_block_type] == "Femoral nerve block"
    # Details maps to procedure notes
    assert result.loc[0, column_map.procedure_notes] == "performing provider details"
    assert pd.isna(result.loc[1, column_map.procedure_notes])


def test_normalize_orphan_columns_extracts_asa_date_and_attending():
    """ASA, date, and attending are populated from ProcedureList columns."""
    column_map = ColumnMap()
    orphan_df = _make_full_proc_df(
        (
            "ORPHAN-1",
            "2024-03-01 08:00",
            2,
            0,
            "Epidural",
            pd.NA,
            pd.NA,
            pd.NA,
            "LABOR",
            "SMITH, JANE",
        ),
    )

    result = CsvHandler(column_map).normalize_orphan_columns(orphan_df)

    assert result.loc[0, column_map.asa] == 2
    assert result.loc[0, column_map.date] == "2024-03-01 08:00"
    assert result.loc[0, column_map.anesthesiologist] == "SMITH, JANE"


def test_normalize_orphan_columns_fills_na_for_demographics():
    """Age is always NA (not in ProcedureList); date/asa/attending populate from CSV."""
    column_map = ColumnMap()
    # Minimal fixture with only required columns (as produced by _make_proc_df)
    orphan_df = _make_proc_df(("ORPHAN-1", "Labor Epidural"))

    result = CsvHandler(column_map).normalize_orphan_columns(orphan_df)

    # Age is never in ProcedureList
    assert pd.isna(result.loc[0, column_map.age])
    # With minimal fixture, date and asa are NA (columns absent)
    assert pd.isna(result.loc[0, column_map.date])
    assert pd.isna(result.loc[0, column_map.asa])


# --- select_primary_technique ---


def test_select_primary_technique_empty_procedures():
    """All-NaN ProcedureName column returns Airway_Type=None."""
    df = pd.DataFrame({"ProcedureName": [pd.NA, pd.NA]})
    result = select_primary_technique(df)
    assert result["Airway_Type"] is None


def test_select_primary_technique_unknown_rank():
    """Unknown technique gets rank 0; known technique with higher rank wins."""
    df = pd.DataFrame({"ProcedureName": ["Unknown Technique", "LMA"]})
    result = select_primary_technique(df)
    # LMA has rank 2, "Unknown Technique" has rank 0 → LMA wins
    assert result["Airway_Type"] == "LMA"


def test_select_primary_technique_tie_is_deterministic():
    """Two techniques with the same rank return a stable result."""
    df = pd.DataFrame({"ProcedureName": ["Unknown A", "Unknown B"]})
    result1 = select_primary_technique(df)
    result2 = select_primary_technique(df)
    assert result1["Airway_Type"] == result2["Airway_Type"]


def test_normalize_columns_fills_missing_optional_columns():
    """Missing AnesAttendings column is filled with NA by normalize_columns."""
    csv_df = pd.DataFrame({
        "MPOG_Case_ID": ["abc-123"],
        "AIMS_Scheduled_DT": ["2025-01-01"],
        "AIMS_Patient_Age_Years": [42],
        "ASA_Status": [2],
        "AIMS_Actual_Procedure_Text": ["Appendectomy"],
        "Airway_Type": ["Intubation routine"],
        # No "AnesAttendings" column
    })
    column_map = ColumnMap()

    result = CsvHandler(column_map).normalize_columns(csv_df)

    assert column_map.anesthesiologist in result.columns
    assert pd.isna(result.loc[0, column_map.anesthesiologist])


def test_normalize_orphan_columns_empty_df():
    """Empty orphan DataFrame returns empty result without error."""
    column_map = ColumnMap()
    orphan_df = pd.DataFrame(columns=["MPOG_Case_ID", "ProcedureName"])

    result = CsvHandler(column_map).normalize_orphan_columns(orphan_df)

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0
    assert column_map.episode_id in result.columns
