"""CSV v2 format I/O operations for case and procedure matching."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from pandas import DataFrame

from .models import ColumnMap

logger = logging.getLogger(__name__)


def discover_csv_pairs(directory: Path) -> list[tuple[Path, Path]]:
    """
    Discover matching CaseList and ProcedureList CSV file pairs.

    Args:
        directory: Directory to search for CSV files

    Returns:
        List of (case_file, procedure_file) path tuples

    Raises:
        ValueError: If no matching pairs found
    """
    directory = Path(directory)

    # Find all CaseList and ProcedureList files
    case_files = {
        f.name.replace(".CaseList.csv", ""): f for f in directory.glob("*.CaseList.csv")
    }
    proc_files = {
        f.name.replace(".ProcedureList.csv", ""): f
        for f in directory.glob("*.ProcedureList.csv")
    }

    # Find matching pairs
    common_prefixes = set(case_files.keys()) & set(proc_files.keys())

    # Warn about unpaired files
    unpaired_case = set(case_files.keys()) - common_prefixes
    unpaired_proc = set(proc_files.keys()) - common_prefixes

    if unpaired_case or unpaired_proc:
        logger.warning(
            "Found unpaired files - CaseList: %s, ProcedureList: %s",
            list(unpaired_case),
            list(unpaired_proc),
        )

    if not common_prefixes:
        raise ValueError(
            f"No matching CSV pairs found in {directory}. "
            "Expected files matching pattern: <PREFIX>.CaseList.csv and <PREFIX>.ProcedureList.csv"
        )

    # Create sorted list of pairs
    pairs = [(case_files[prefix], proc_files[prefix]) for prefix in sorted(common_prefixes)]

    logger.info("Discovered %d CSV pair(s)", len(pairs))
    return pairs


# Airway management ranking (higher rank = more invasive)
AIRWAY_RANK = {
    "Intubation complex": 6,
    "Intubation routine": 5,
    "Spinal": 4,
    "Epidural": 3,
    "LMA": 2,
    "Peripheral nerve block": 1,
}


def _aggregate_procedures(proc_group: pd.DataFrame) -> pd.Series:
    """
    Aggregate multiple procedures for one case.

    Args:
        proc_group: DataFrame of procedures for one MPOG_Case_ID

    Returns:
        Series with aggregated airway type (most invasive)
    """
    # Extract all procedure names
    airway_types = proc_group["ProcedureName"].dropna()

    if airway_types.empty:
        return pd.Series({"Airway_Type": None})

    # Find most invasive airway
    ranked = [(AIRWAY_RANK.get(a, 0), a) for a in airway_types]
    most_invasive = max(ranked, key=lambda x: x[0])[1] if ranked else None

    return pd.Series({"Airway_Type": most_invasive})


def join_case_and_procedures(case_df: DataFrame, proc_df: DataFrame) -> DataFrame:
    """
    Join case and procedure DataFrames, aggregating multiple procedures per case.

    Args:
        case_df: CaseList DataFrame with MPOG_Case_ID
        proc_df: ProcedureList DataFrame with MPOG_Case_ID

    Returns:
        Joined DataFrame with aggregated procedure information
    """
    # Group procedures by case ID and aggregate
    if not proc_df.empty:
        proc_agg = (
            proc_df.groupby("MPOG_Case_ID").apply(_aggregate_procedures).reset_index()
        )
    else:
        proc_agg = pd.DataFrame(columns=["MPOG_Case_ID", "Airway_Type"])

    # Left join cases to aggregated procedures
    result = case_df.merge(proc_agg, on="MPOG_Case_ID", how="left")

    logger.info(
        "Joined %d cases with procedures (%d cases without procedures)",
        len(result),
        result["Airway_Type"].isna().sum(),
    )

    return result


def _clean_attending_names(value: str) -> str:
    """
    Clean attending names by removing timestamps.

    Args:
        value: Raw attending string like "DOE, JOHN@2023-01-01 08:00:00"

    Returns:
        Cleaned string with timestamps removed
    """
    if pd.isna(value):
        return ""

    # Split on semicolon for multiple attendings
    parts = str(value).split(";")

    # Remove timestamp portion (everything after @)
    cleaned = [part.split("@")[0].strip() for part in parts]

    return "; ".join(cleaned)


def map_csv_to_standard_columns(csv_df: DataFrame, column_map: ColumnMap) -> DataFrame:
    """
    Map CSV v2 columns to standard ColumnMap field names.

    Args:
        csv_df: DataFrame from CSV v2 with joined case/procedure data
        column_map: Target column mapping

    Returns:
        DataFrame with renamed columns matching ColumnMap
    """
    result = csv_df.copy()

    # Create mapping from CSV columns to standard columns
    rename_map = {
        "MPOG_Case_ID": column_map.episode_id,
        "AIMS_Scheduled_DT": column_map.date,
        "AIMS_Patient_Age_Years": column_map.age,
        "ASA_Status": column_map.asa,
        "AIMS_Actual_Procedure_Text": column_map.procedure,
        "Airway_Type": column_map.final_anesthesia_type,
    }

    # Rename columns
    result = result.rename(columns=rename_map)

    # Clean and map attending names
    if "AnesAttendings" in csv_df.columns:
        result[column_map.anesthesiologist] = csv_df["AnesAttendings"].apply(
            _clean_attending_names
        )

    # CSV v2 doesn't have Services column - will derive from procedure text
    # Add empty services column for compatibility
    result[column_map.services] = ""

    logger.info("Mapped CSV columns to standard format")

    return result


def read_csv_v2(
    directory: Path, add_source: bool = False, column_map: ColumnMap | None = None
) -> DataFrame:
    """
    Read and join CSV v2 format files.

    Args:
        directory: Directory containing CaseList and ProcedureList CSV files
        add_source: If True, add 'Source File' column with file prefix
        column_map: Target column mapping (default: standard ColumnMap)

    Returns:
        Joined DataFrame with standard column names
    """
    directory = Path(directory)
    column_map = column_map or ColumnMap()

    # Discover CSV pairs
    pairs = discover_csv_pairs(directory)

    # Read and join each pair
    all_dfs = []
    for case_file, proc_file in pairs:
        logger.info("Reading pair: %s, %s", case_file.name, proc_file.name)

        # Read CSVs
        case_df = pd.read_csv(case_file)
        proc_df = pd.read_csv(proc_file)

        # Join
        joined = join_case_and_procedures(case_df, proc_df)

        # Add source column if requested (before mapping)
        if add_source:
            prefix = case_file.name.replace(".CaseList.csv", "")
            joined["Source File"] = prefix

        all_dfs.append(joined)

    # Combine all pairs
    combined = pd.concat(all_dfs, ignore_index=True)

    # Map to standard columns
    result = map_csv_to_standard_columns(combined, column_map)

    # Preserve source column if added
    if add_source and "Source File" in combined.columns:
        result["Source File"] = combined["Source File"]

    logger.info("Read total of %d cases from %d file pair(s)", len(result), len(pairs))

    return result
