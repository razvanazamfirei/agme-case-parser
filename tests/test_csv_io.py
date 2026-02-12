"""Tests for CSV v2 format I/O operations."""

from pathlib import Path
import pytest
from case_parser.csv_io import discover_csv_pairs


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

    with pytest.raises(ValueError):
        discover_csv_pairs(tmp_path)

    assert "unpaired" in caplog.text.lower()
