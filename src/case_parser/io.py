"""I/O operations for reading and writing Excel files and CSV v2 format."""

from __future__ import annotations

import logging
import operator
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from openpyxl.utils import get_column_letter
from pandas import DataFrame

from .extractors import extract_attending
from .models import (
    FORMAT_TYPE_CASELOG,
    OUTPUT_FORMAT_VERSION,
    TECHNIQUE_RANK,
    ColumnMap,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excel I/O
# ---------------------------------------------------------------------------


def read_excel(file_path: str | Path, sheet_name: str | int = 0) -> DataFrame:
    """Read an Excel file and return a DataFrame.

    Args:
        file_path: Path to the Excel file
        sheet_name: Sheet name or index to read (default: first sheet)

    Returns:
        DataFrame containing the sheet data

    Raises:
        FileNotFoundError: If the file does not exist at file_path.
        ValueError: If the file extension is not ``.xlsx`` or ``.xls``.
        TypeError: If sheet_name resolves to multiple sheets.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    if file_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(
            f"Unsupported file format: {file_path.suffix}. Expected .xlsx or .xls"
        )

    try:
        logger.info("Reading Excel file: %s", file_path)
        result = pd.read_excel(file_path, sheet_name=sheet_name)
        if isinstance(result, dict):
            raise TypeError(
                "Multiple sheets returned. Please specify a single sheet name or index."
            )
        logger.info("Successfully read %s rows from %s", len(result), file_path)
        return result
    except Exception as e:
        logger.error("Error reading Excel file %s: %s", file_path, e)
        raise


class ExcelHandler:
    """Handles Excel file output operations."""

    def __init__(self, max_width: int = 60):
        """Initialize with maximum column width setting.

        Args:
            max_width: Maximum column width in characters applied during
                auto-sizing. Columns wider than this are capped.
        """
        self.max_width = max_width

    def write_excel(
        self,
        df: pd.DataFrame,
        file_path: str | Path,
        sheet_name: str = "CaseLog",
        fixed_widths: dict[str, int] | None = None,
        format_type: str = FORMAT_TYPE_CASELOG,
        version: str = OUTPUT_FORMAT_VERSION,
    ) -> None:
        """Write DataFrame to Excel file with auto-sized columns.

        Writes the data sheet, a visible Info sheet showing the format type and
        version, and a hidden _meta sheet for machine consumption (e.g. the
        Chrome extension).

        Args:
            df: DataFrame to write.
            file_path: Destination file path. Parent directories are created
                automatically.
            sheet_name: Name of the worksheet to create.
            fixed_widths: Optional mapping of column name to a fixed character
                width, bypassing auto-sizing for those columns.
            format_type: Schema identifier written to Info and _meta sheets
                (e.g. ``FORMAT_TYPE_CASELOG`` or ``FORMAT_TYPE_STANDALONE``).
            version: Schema version string written to Info and _meta sheets.

        Raises:
            PermissionError: If the file is open in another application.
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            logger.info("Writing Excel file: %s", file_path)
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                self._autosize_columns(writer, df, sheet_name, fixed_widths)
                self._write_info_sheet(writer, format_type, version)
                self._write_meta_sheet(writer, format_type, version)
            logger.info("Successfully wrote %d rows to %s", len(df), file_path)
        except PermissionError:
            logger.error(
                "Permission denied writing to %s. Is the file open?", file_path
            )
            raise
        except Exception as e:
            logger.error("Error writing Excel file %s: %s", file_path, e)
            raise

    @staticmethod
    def _write_info_sheet(
        writer: pd.ExcelWriter, format_type: str, version: str
    ) -> None:
        """Write a visible Info sheet with human-readable format metadata.

        This sheet lets anyone opening the file immediately see what schema
        version and format type were used to produce it.

        Args:
            writer: Active ExcelWriter to write the Info sheet into.
            format_type: Schema identifier (e.g. ``caselog`` or ``standalone``).
            version: Schema version string (e.g. ``"1"``).
        """
        info_df = pd.DataFrame({
            "Field": ["Format Type", "Version", "Generated"],
            "Value": [format_type, version, datetime.now(tz=UTC).date().isoformat()],
        })
        info_df.to_excel(writer, sheet_name="Info", index=False)

    @staticmethod
    def _write_meta_sheet(
        writer: pd.ExcelWriter, format_type: str, version: str
    ) -> None:
        """Write a hidden _meta sheet for machine consumption.

        The Chrome extension reads this sheet to determine which column schema
        is in use, allowing seamless processing across format versions.

        Schema:
            key         | value
            ------------+-----------
            version     | 1
            format_type | caselog

        Args:
            writer: Active ExcelWriter to write the _meta sheet into.
            format_type: Schema identifier written alongside the version.
            version: Schema version string.
        """
        meta_df = pd.DataFrame({
            "key": ["version", "format_type"],
            "value": [version, format_type],
        })
        meta_df.to_excel(writer, sheet_name="_meta", index=False)
        writer.sheets["_meta"].sheet_state = "hidden"

    def _autosize_columns(
        self,
        writer: pd.ExcelWriter,
        df: pd.DataFrame,
        sheet_name: str,
        fixed_widths: dict[str, int] | None = None,
    ) -> None:
        """Set column widths based on content length.

        Iterates over every column in the DataFrame and sets the worksheet
        column width to the maximum string length of the header or any cell
        value, capped at self.max_width. Columns listed in fixed_widths receive
        that exact width instead.

        Args:
            writer: Active ExcelWriter with the worksheet already written.
            df: DataFrame whose column data is used to calculate widths.
            sheet_name: Name of the worksheet to resize.
            fixed_widths: Mapping of column name to exact character width.
        """
        worksheet = writer.sheets[sheet_name]
        fixed_widths = fixed_widths or {}

        for idx, column in enumerate(df.columns, start=1):
            col_letter = get_column_letter(idx)
            if column in fixed_widths:
                worksheet.column_dimensions[col_letter].width = fixed_widths[column]
                continue
            content_lengths = [len(column)] + [len(str(cell)) for cell in df[column]]
            max_length = min(max(content_lengths) + 2, self.max_width)
            worksheet.column_dimensions[col_letter].width = max_length


# ---------------------------------------------------------------------------
# CSV v2 I/O (MPOG supervised export format)
# ---------------------------------------------------------------------------


def discover_csv_pairs(directory: Path) -> list[tuple[Path, Path]]:
    """Discover matching CaseList and ProcedureList CSV file pairs.

    Args:
        directory: Directory to search for CSV files

    Returns:
        List of (case_file, procedure_file) path tuples

    Raises:
        ValueError: If no matching pairs found
    """
    directory = Path(directory)

    case_files = {
        f.name.replace(".CaseList.csv", ""): f for f in directory.glob("*.CaseList.csv")
    }
    proc_files = {
        f.name.replace(".ProcedureList.csv", ""): f
        for f in directory.glob("*.ProcedureList.csv")
    }

    common_prefixes = set(case_files.keys()) & set(proc_files.keys())

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
            "Expected files matching pattern: "
            "<PREFIX>.CaseList.csv and <PREFIX>.ProcedureList.csv"
        )

    pairs = [
        (case_files[prefix], proc_files[prefix]) for prefix in sorted(common_prefixes)
    ]
    logger.info("Discovered %d CSV pair(s)", len(pairs))
    return pairs


def select_primary_technique(proc_group: pd.DataFrame) -> pd.Series:
    """Select the primary (most invasive) anesthesia technique for one case.

    Args:
        proc_group: DataFrame of procedures for one MPOG_Case_ID

    Returns:
        Series with the highest-ranked technique as Airway_Type
    """
    techniques = proc_group["ProcedureName"].dropna()
    if techniques.empty:
        return pd.Series({"Airway_Type": None})
    ranked = [(TECHNIQUE_RANK.get(t, 0), t) for t in techniques]
    return pd.Series({"Airway_Type": max(ranked, key=operator.itemgetter(0))[1]})


def join_case_and_procedures(
    case_df: DataFrame, proc_df: DataFrame
) -> tuple[DataFrame, DataFrame]:
    """Join case and procedure DataFrames, aggregating multiple procedures per case.

    Args:
        case_df: CaseList DataFrame with MPOG_Case_ID
        proc_df: ProcedureList DataFrame with MPOG_Case_ID

    Returns:
        Tuple of (joined_df, orphan_procs_df) where orphan_procs_df contains
        procedures whose MPOG_Case_ID has no matching entry in case_df (e.g.,
        standalone labor epidurals, peripheral nerve catheters).
    """
    orphan_procs = pd.DataFrame(columns=proc_df.columns if not proc_df.empty else [])
    if not proc_df.empty:
        case_ids = set(case_df["MPOG_Case_ID"])
        orphan_mask = ~proc_df["MPOG_Case_ID"].isin(case_ids)
        orphan_procs = proc_df[orphan_mask].copy().reset_index(drop=True)
        if not orphan_procs.empty:
            logger.info(
                "Found %d orphan procedure(s) with no matching case", len(orphan_procs)
            )
        matched_procs = proc_df[~orphan_mask]
        proc_agg = (
            matched_procs
            .groupby("MPOG_Case_ID")
            .apply(select_primary_technique)  # type: ignore[no-matching-overload]
            .reset_index()
        )
    else:
        proc_agg = pd.DataFrame(columns=["MPOG_Case_ID", "Airway_Type"])

    result = case_df.merge(proc_agg, on="MPOG_Case_ID", how="left")
    logger.info(
        "Joined %d cases with procedures (%d cases without procedures)",
        len(result),
        result["Airway_Type"].isna().sum(),
    )
    return result, orphan_procs


class CsvHandler:
    """Handles MPOG supervised-export CSV v2 format reading."""

    def __init__(self, column_map: ColumnMap | None = None):
        """Initialize with column mapping.

        Args:
            column_map: Column mapping to use when normalizing CSV columns.
                Defaults to a standard ColumnMap if not provided.
        """
        self.column_map = column_map or ColumnMap()

    def read(self, directory: Path) -> tuple[DataFrame, DataFrame]:
        """Read and join CSV v2 format files from a directory.

        Discovers all CaseList/ProcedureList pairs in the directory, joins
        each pair, and concatenates the results.

        Args:
            directory: Directory containing matching *.CaseList.csv and
                *.ProcedureList.csv file pairs.

        Returns:
            Tuple of (main_df, orphan_df) where orphan_df contains standalone
            procedures (e.g., labor epidurals, peripheral nerve catheters) that
            have no matching case in the CaseList. orphan_df is empty if none found.
        """
        directory = Path(directory)
        pairs = discover_csv_pairs(directory)

        all_dfs: list[DataFrame] = []
        all_orphan_dfs: list[DataFrame] = []
        for case_file, proc_file in pairs:
            logger.info("Reading pair: %s, %s", case_file.name, proc_file.name)
            case_df = pd.read_csv(case_file)
            proc_df = pd.read_csv(proc_file)
            joined, orphan_procs = join_case_and_procedures(case_df, proc_df)
            all_dfs.append(joined)
            if not orphan_procs.empty:
                all_orphan_dfs.append(orphan_procs)

        combined = pd.concat(all_dfs, ignore_index=True)
        result = self.normalize_columns(combined)
        logger.info(
            "Read total of %d cases from %d file pair(s)", len(result), len(pairs)
        )

        if all_orphan_dfs:
            orphan_combined = pd.concat(all_orphan_dfs, ignore_index=True)
            orphan_result = self.normalize_orphan_columns(orphan_combined)
            logger.info("Found %d total orphan procedure(s)", len(orphan_result))
        else:
            orphan_result = pd.DataFrame()

        return result, orphan_result

    def normalize_columns(self, csv_df: DataFrame) -> DataFrame:
        """Map CSV v2 columns to standard ColumnMap field names.

        Renames MPOG export columns to the names expected by downstream
        processors, derives the anesthesiologist field from AnesAttendings,
        copies Airway_Type into procedure_notes for airway extraction, and
        fills any still-missing standard columns with pd.NA.

        Args:
            csv_df: Raw joined DataFrame produced from a CaseList/ProcedureList
                pair before column normalization.

        Returns:
            DataFrame with columns matching self.column_map field values.
        """
        column_map = self.column_map
        result = csv_df.rename(
            columns={
                "MPOG_Case_ID": column_map.episode_id,
                "AIMS_Scheduled_DT": column_map.date,
                "AIMS_Patient_Age_Years": column_map.age,
                "ASA_Status": column_map.asa,
                "AIMS_Actual_Procedure_Text": column_map.procedure,
                "Airway_Type": column_map.final_anesthesia_type,
            }
        )

        if "AnesAttendings" in csv_df.columns:
            result[column_map.anesthesiologist] = csv_df["AnesAttendings"].apply(
                extract_attending
            )

        # CSV v2 airway values carry both anesthesia signal and airway technique hints.
        # Populate procedure notes so airway extraction can run through the normal flow.
        if "Airway_Type" in csv_df.columns:
            result[column_map.procedure_notes] = csv_df["Airway_Type"]

        # CSV v2 has no Services column — derive from procedure text during processing.
        result[column_map.services] = ""

        # Ensure all standard columns exist so downstream consumers have a
        # consistent schema.
        for col in [
            column_map.anesthesiologist,
            column_map.procedure_notes,
            column_map.emergent,
        ]:
            if col not in result.columns:
                result[col] = pd.NA

        logger.info("Mapped CSV columns to standard format")
        return result

    def normalize_orphan_columns(self, orphan_df: DataFrame) -> DataFrame:
        """Map orphan procedure rows to standard column format.

        Orphan procedures are ProcedureList entries whose MPOG_Case_ID has no
        matching case in the CaseList (e.g., standalone labor epidurals, peripheral
        nerve catheters).

        MPOG ProcedureList columns used:
            MPOG_Case_ID             → episode_id
            AIMS_Scheduled_DT        → date
            ASA_Status               → asa
            Emergency                → emergent
            ProcedureName            → final_anesthesia_type (anesthesia type hint)
            PrimaryBlock             → nerve_block_type
            Details                  → procedure_notes
            AIMS_Actual_Procedure_Text → procedure
            AnesAttendingNames       → anesthesiologist

        Age is not present in MPOG ProcedureList exports; that field is left NA.

        Args:
            orphan_df: DataFrame of unmatched ProcedureList rows.

        Returns:
            DataFrame with columns matching self.column_map field values.
        """
        column_map = self.column_map
        result = pd.DataFrame(index=orphan_df.index)

        result[column_map.episode_id] = orphan_df.get("MPOG_Case_ID")
        result[column_map.date] = orphan_df.get("AIMS_Scheduled_DT")
        result[column_map.asa] = orphan_df.get("ASA_Status")
        result[column_map.emergent] = orphan_df.get("Emergency")
        result[column_map.final_anesthesia_type] = orphan_df.get("ProcedureName")
        result[column_map.nerve_block_type] = orphan_df.get("PrimaryBlock")
        result[column_map.procedure_notes] = orphan_df.get("Details")
        result[column_map.procedure] = orphan_df.get("AIMS_Actual_Procedure_Text")
        result[column_map.services] = ""

        if "AnesAttendingNames" in orphan_df.columns:
            result[column_map.anesthesiologist] = orphan_df["AnesAttendingNames"].apply(
                extract_attending
            )
        else:
            result[column_map.anesthesiologist] = pd.NA

        # Age is not exported in MPOG ProcedureList
        result[column_map.age] = pd.NA

        return result.reset_index(drop=True)
