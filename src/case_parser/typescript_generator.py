"""Generate TypeScript type definitions from domain models."""

from __future__ import annotations

import logging
from pathlib import Path

from .domain import (
    AgeCategory,
    AirwayManagement,
    AnesthesiaType,
    MonitoringTechnique,
    ProcedureCategory,
    VascularAccess,
)

logger = logging.getLogger(__name__)


class TypeScriptGenerator:
    """Generate TypeScript type definitions from Python domain models."""

    @staticmethod
    def generate_type_definitions(output_path: str | Path) -> None:
        """
        Generate TypeScript type definitions for ParsedCase and related types.

        Args:
            output_path: Path to output TypeScript definition file (.d.ts)
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Generating TypeScript type definitions: %s", output_path)

        # Generate enum types
        enums = TypeScriptGenerator._generate_enums()

        # Generate ParsedCase interface
        parsed_case_interface = TypeScriptGenerator._generate_parsed_case_interface()

        # Generate export types
        export_types = TypeScriptGenerator._generate_export_types()

        # Combine all type definitions
        content = f"""/**
 * TypeScript type definitions for Case Parser export format
 * 
 * This file is auto-generated from Python domain models.
 * DO NOT EDIT MANUALLY - regenerate using: case-parser --generate-types
 */

// ============================================================================
// Enum Types
// ============================================================================

{enums}

// ============================================================================
// Core ParsedCase Interface
// ============================================================================

{parsed_case_interface}

// ============================================================================
// Export Format Types
// ============================================================================

{export_types}
"""

        try:
            with output_path.open("w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Successfully generated TypeScript types: %s", output_path)
        except Exception as e:
            logger.error("Error writing TypeScript definitions %s: %s", output_path, e)
            raise

    @staticmethod
    def _generate_enums() -> str:
        """Generate TypeScript enum definitions from Python StrEnum classes."""
        return f"""/**
 * Age category classifications for residency requirements
 */
export type AgeCategory =
  | "{AgeCategory.UNDER_3_MONTHS.value}"
  | "{AgeCategory.THREE_MOS_TO_3_YR.value}"
  | "{AgeCategory.THREE_YR_TO_12_YR.value}"
  | "{AgeCategory.TWELVE_YR_TO_65_YR.value}"
  | "{AgeCategory.OVER_65_YR.value}";

/**
 * Standardized anesthesia type classifications
 */
export type AnesthesiaType =
  | "{AnesthesiaType.GENERAL.value}"
  | "{AnesthesiaType.MAC.value}"
  | "{AnesthesiaType.SPINAL.value}"
  | "{AnesthesiaType.EPIDURAL.value}"
  | "{AnesthesiaType.CSE.value}"
  | "{AnesthesiaType.PERIPHERAL_NERVE_BLOCK.value}";

/**
 * Procedure category classifications
 */
export type ProcedureCategory =
  | "{ProcedureCategory.CARDIAC.value}"
  | "{ProcedureCategory.INTRACEREBRAL.value}"
  | "{ProcedureCategory.INTRATHORACIC_NON_CARDIAC.value}"
  | "{ProcedureCategory.MAJOR_VESSELS.value}"
  | "{ProcedureCategory.CESAREAN.value}"
  | "{ProcedureCategory.OTHER.value}";

/**
 * Airway management techniques
 */
export type AirwayManagement =
  | "{AirwayManagement.ORAL_ETT.value}"
  | "{AirwayManagement.NASAL_ETT.value}"
  | "{AirwayManagement.DIRECT_LARYNGOSCOPE.value}"
  | "{AirwayManagement.VIDEO_LARYNGOSCOPE.value}"
  | "{AirwayManagement.SUPRAGLOTTIC_AIRWAY.value}"
  | "{AirwayManagement.FLEXIBLE_BRONCHOSCOPIC.value}"
  | "{AirwayManagement.MASK.value}"
  | "{AirwayManagement.DIFFICULT_AIRWAY.value}";

/**
 * Specialized vascular access types
 */
export type VascularAccess =
  | "{VascularAccess.ARTERIAL_CATHETER.value}"
  | "{VascularAccess.CENTRAL_VENOUS_CATHETER.value}"
  | "{VascularAccess.PULMONARY_ARTERY_CATHETER.value}";

/**
 * Specialized monitoring techniques
 */
export type MonitoringTechnique =
  | "{MonitoringTechnique.TEE.value}"
  | "{MonitoringTechnique.ELECTROPHYSIOLOGIC_MON.value}"
  | "{MonitoringTechnique.CSF_DRAIN.value}"
  | "{MonitoringTechnique.INVASIVE_NEURO_MON.value}";
"""

    @staticmethod
    def _generate_parsed_case_interface() -> str:
        """Generate TypeScript interface for ParsedCase."""
        return """/**
 * Detailed extraction finding with metadata
 */
export interface ExtractionFinding {
  value: string;
  confidence: number; // 0.0 to 1.0
  context: string | null;
  source_field: string;
}

/**
 * Parsing metadata included with parsed cases
 */
export interface ParsedCaseMetadata {
  confidence_score: number; // 0.0 to 1.0
  has_warnings: boolean;
  warning_count: number;
  warnings: string[];
  extraction_findings?: ExtractionFinding[];
}

/**
 * Raw/original field values from source data
 */
export interface RawCaseData {
  date: string | null;
  age: number | null;
  asa: string | null;
  anesthesia_type: string | null;
}

/**
 * Typed intermediate representation of a parsed anesthesia case
 */
export interface ParsedCase {
  // Core fields
  episode_id: string | null;
  case_date: string; // ISO format date (YYYY-MM-DD)
  responsible_provider: string | null;
  age_category: AgeCategory | null;
  procedure: string | null;
  asa_physical_status: string;
  anesthesia_type: AnesthesiaType | null;
  procedure_category: ProcedureCategory;
  emergent: boolean;

  // List fields (arrays for easier Chrome extension processing)
  airway_management: AirwayManagement[];
  vascular_access: VascularAccess[];
  monitoring: MonitoringTechnique[];
  services: string[];

  // Optional metadata (included by default, can be excluded)
  metadata?: ParsedCaseMetadata;

  // Optional raw data (only included if requested)
  raw?: RawCaseData;
  procedure_notes?: string | null;
}
"""

    @staticmethod
    def _generate_export_types() -> str:
        """Generate TypeScript types for export formats."""
        return """/**
 * Summary statistics for exported cases
 */
export interface ExportSummary {
  cases_with_warnings: number;
  low_confidence_cases: number;
  average_confidence: number;
}

/**
 * Single-file export format (all cases in one JSON file)
 */
export interface CasesExport {
  version: string;
  total_cases: number;
  summary?: ExportSummary;
  cases: ParsedCase[];
}
"""

