"""Data processing functions for case log transformation."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .extractors import (
    clean_names,
    extract_airway_management,
    extract_monitoring,
    extract_vascular_access,
)
from .models import (
    AGE_RANGES,
    ANESTHESIA_MAPPING,
    OUTPUT_COLUMNS,
    PROCEDURE_RULES,
    ColumnMap,
)

logger = logging.getLogger(__name__)


class CaseProcessor:
    """Main processor for transforming anesthesia case data."""

    def __init__(self, column_map: ColumnMap, default_year: int = 2025):
        """Initialize the processor with column mapping and default year."""
        self.column_map = column_map
        self.default_year = default_year

    def parse_date(self, value: Any) -> pd.Timestamp:
        """Parse date with fallback to default year."""
        if pd.isna(value):
            logger.warning(
                "Missing date value, using default year %s", {self.default_year}
            )
            return pd.Timestamp(year=self.default_year, month=1, day=1)

        # Try standard parsing first
        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.notna(timestamp):
            return timestamp

        # Try specific format
        timestamp = pd.to_datetime(str(value), format="%m/%d/%Y", errors="coerce")
        if pd.notna(timestamp):
            return timestamp

        # Fallback to default
        logger.warning(
            "Could not parse date %s, using default year %s", value, self.default_year
        )
        return pd.Timestamp(year=self.default_year, month=1, day=1)

    @staticmethod
    def determine_age_category(age: Any) -> str:
        """Categorize age using structured age ranges."""
        if age is None or (isinstance(age, float) and pd.isna(age)):
            return ""

        try:
            age_float = float(age)
        except (ValueError, TypeError):
            logger.warning("Invalid age value: %s", age)
            return ""

        # Find first range where age is below upper bound
        return next(
            (
                range_.category
                for range_ in AGE_RANGES
                if age_float < range_.upper_bound
            ),
            "",
        )

    @staticmethod
    def map_anesthesia_type(anesthesia_input: Any) -> str:
        """Map anesthesia description to standardized type."""
        if anesthesia_input is None or (
            isinstance(anesthesia_input, float) and pd.isna(anesthesia_input)
        ):
            return ""

        input_str = str(anesthesia_input).strip().upper()

        # Return first matching anesthesia type
        for keyword, anesthesia_type in ANESTHESIA_MAPPING.items():
            if keyword in input_str:
                return anesthesia_type

        # Return original if no mapping found
        return str(anesthesia_input).strip()

    @staticmethod
    def determine_procedure_category(procedure: Any, services: Any) -> str:
        """Determine procedure category based on services and procedure text."""
        service_text = "" if pd.isna(services) else str(services).upper()
        procedure_text = "" if pd.isna(procedure) else str(procedure).upper()

        # Check standard rules first
        for rule in PROCEDURE_RULES:
            if any(keyword in service_text for keyword in rule.keywords):
                # Check exclusions
                if rule.exclude_keywords and any(
                    excl in service_text for excl in rule.exclude_keywords
                ):
                    continue
                return rule.category

        # Special handling for OB/GYN with cesarean detection
        if any(keyword in service_text for keyword in ("GYN", "OB", "OBSTET")):
            if any(
                keyword in procedure_text
                for keyword in ("CESAREAN", "C-SECTION", "C SECTION")
            ):
                return "Cesarean del"
            return "Other (procedure cat)"

        return "Other (procedure cat)"

    @staticmethod
    def normalize_emergent_flag(value: Any) -> bool:
        """Convert various emergent flag formats to boolean."""
        if pd.isna(value):
            return False

        return str(value).strip().upper() in {"E", "Y", "YES", "TRUE", "1"}

    def process_row(self, row: pd.Series) -> dict[str, Any]:
        """Process a single row into case log format."""
        try:
            # Parse date
            timestamp = self.parse_date(row.get(self.column_map.date))
            date_str = timestamp.strftime("%m/%d/%Y")

            # Handle ASA with emergent flag
            raw_asa = row.get(self.column_map.asa)
            asa_str = "" if pd.isna(raw_asa) else str(raw_asa)
            emergent = self.normalize_emergent_flag(row.get(self.column_map.emergent))
            if asa_str and "E" not in asa_str.upper() and emergent:
                asa_str = f"{asa_str}E"

            notes = row.get(self.column_map.procedure_notes)

            return {
                "Case ID": ""
                if pd.isna(row.get(self.column_map.episode_id))
                else str(row.get(self.column_map.episode_id)),
                "Case Date": date_str,
                "Supervisor": ""
                if pd.isna(row.get(self.column_map.anesthesiologist))
                else str(clean_names(row.get(self.column_map.anesthesiologist))),
                "Age": self.determine_age_category(row.get(self.column_map.age)),
                "Original Procedure": ""
                if pd.isna(row.get(self.column_map.procedure))
                else str(row.get(self.column_map.procedure)),
                "ASA Physical Status": asa_str,
                "Anesthesia Type": self.map_anesthesia_type(
                    row.get(self.column_map.final_anesthesia_type)
                ),
                "Airway Management": extract_airway_management(notes),
                "Procedure Category": self.determine_procedure_category(
                    row.get(self.column_map.procedure),
                    row.get(self.column_map.services),
                ),
                "Specialized Vascular Access": extract_vascular_access(notes),
                "Specialized Monitoring Techniques": extract_monitoring(notes),
            }
        except Exception as e:
            logger.error("Error processing row: %s", e)
            # Return a row with empty values to maintain structure
            return dict.fromkeys(OUTPUT_COLUMNS, "")

    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform input dataframe to case log format."""
        logger.info("Processing %s rows of data", {len(df)})

        # Validate required columns exist
        required_columns = [
            self.column_map.date,
            self.column_map.episode_id,
            self.column_map.anesthesiologist,
            self.column_map.age,
            self.column_map.asa,
            self.column_map.final_anesthesia_type,
            self.column_map.procedure_notes,
            self.column_map.procedure,
            self.column_map.services,
        ]

        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.warning("Missing columns in input data: %s", missing_columns)

        # Process all rows
        processed_rows = [self.process_row(row) for _, row in df.iterrows()]
        result_df = pd.DataFrame(processed_rows)

        # Ensure column order
        return result_df[OUTPUT_COLUMNS]
