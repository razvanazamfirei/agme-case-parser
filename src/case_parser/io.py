"""I/O operations for reading and writing Excel files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.utils import get_column_letter
from pandas import DataFrame

logger = logging.getLogger(__name__)


def read_excel(
    file_path: str | Path, sheet_name: str | int | None = None
) -> dict[str, DataFrame]:
    """Read Excel file and return DataFrame."""
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    if file_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(
            f"Unsupported file format: {file_path.suffix}. Expected .xlsx or .xls"
        )

    try:
        logger.info("Reading Excel file: %s", file_path)
        df = pd.read_excel(file_path, sheet_name=sheet_name or 0)
        logger.info(f"Successfully read {len(df)} rows from {file_path}")  # noqa: G004
        return df
    except Exception as e:
        logger.error("Error reading Excel file %s: %s", file_path, e)
        raise


class ExcelHandler:
    """Handles Excel file input and output operations."""

    def __init__(self, max_width: int = 60):
        """Initialize with maximum column width setting."""
        self.max_width = max_width

    def write_excel(
        self,
        df: pd.DataFrame,
        file_path: str | Path,
        sheet_name: str = "CaseLog",
        fixed_widths: dict[str, int] | None = None,
    ) -> None:
        """Write DataFrame to Excel file with auto-sized columns."""
        file_path = Path(file_path)

        # Ensure output directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            logger.info("Writing Excel file: %s", file_path)
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                self._autosize_columns(writer, df, sheet_name, fixed_widths)
            logger.info(f"Successfully wrote {len(df)} rows to {file_path}")  # noqa: G004
        except PermissionError:
            logger.error(
                "Permission denied writing to %s. Is the file open?", file_path
            )
            raise
        except Exception as e:
            logger.error("Error writing Excel file %s: %s", file_path, e)
            raise

    def _autosize_columns(
        self,
        writer: pd.ExcelWriter,
        df: pd.DataFrame,
        sheet_name: str,
        fixed_widths: dict[str, int] | None = None,
    ) -> None:
        """Set column widths based on content length."""
        worksheet = writer.sheets[sheet_name]
        fixed_widths = fixed_widths or {}

        for idx, column in enumerate(df.columns, start=1):
            if column in fixed_widths:
                worksheet.column_dimensions[
                    get_column_letter(idx)
                ].width = fixed_widths[column]
                continue

            # Calculate max width needed
            content_lengths = [len(column)] + [len(str(cell)) for cell in df[column]]
            max_length = min(max(content_lengths) + 2, self.max_width)
            worksheet.column_dimensions[get_column_letter(idx)].width = max_length

    @staticmethod
    def get_data_summary(df: pd.DataFrame) -> dict[str, Any]:
        """Get summary statistics for the processed data."""
        try:
            dates = pd.to_datetime(df["Case Date"], format="%m/%d/%Y", errors="coerce")
            date_range = "Unavailable"
            if dates.notna().any():
                min_date = dates.min().strftime("%m/%d/%Y")
                max_date = dates.max().strftime("%m/%d/%Y")
                date_range = f"{min_date} to {max_date}"

            return {
                "total_cases": len(df),
                "date_range": date_range,
                "columns": list(df.columns),
                "empty_cases": df["Case ID"].isna().sum(),
                "missing_dates": df["Case Date"].isna().sum(),
            }
        except Exception as e:
            logger.warning("Could not generate data summary: %s", e)
            return {"total_cases": len(df), "date_range": "Unavailable"}
