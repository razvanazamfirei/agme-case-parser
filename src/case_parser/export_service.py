"""Service for exporting parsed cases to TypeScript/JSON for Chrome extension consumption."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .domain import ParsedCase

logger = logging.getLogger(__name__)


class ExportService:
    """Service for exporting cases to various formats."""

    @staticmethod
    def export_cases_to_json(
        cases: list[ParsedCase],
        output_path: str | Path,
        include_metadata: bool = True,
        include_raw: bool = False,
        pretty: bool = True,
    ) -> None:
        """
        Export cases to a single JSON file for Chrome extension consumption.

        Args:
            cases: List of ParsedCase objects to export
            output_path: Path to output JSON file
            include_metadata: Include parsing warnings, confidence scores, etc.
            include_raw: Include raw/original field values for debugging
            pretty: Pretty-print JSON with indentation

        Raises:
            PermissionError: If output file cannot be written
            IOError: If there's an error writing the file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Exporting %d cases to JSON: %s", len(cases), output_path)

        # Convert all cases to JSON-serializable format
        cases_data = [
            case.to_json_dict(include_metadata=include_metadata, include_raw=include_raw)
            for case in cases
        ]

        # Create export structure
        export_data: dict[str, Any] = {
            "version": "1.0",
            "total_cases": len(cases),
            "cases": cases_data,
        }

        # Add summary statistics if metadata is included
        if include_metadata:
            cases_with_warnings = sum(1 for case in cases if case.has_warnings())
            low_confidence_cases = sum(
                1 for case in cases if case.is_low_confidence()
            )
            avg_confidence = (
                sum(case.confidence_score for case in cases) / len(cases)
                if cases
                else 0.0
            )

            export_data["summary"] = {
                "cases_with_warnings": cases_with_warnings,
                "low_confidence_cases": low_confidence_cases,
                "average_confidence": round(avg_confidence, 3),
            }

        try:
            with output_path.open("w", encoding="utf-8") as f:
                if pretty:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(export_data, f, ensure_ascii=False)

            logger.info("Successfully exported %d cases to %s", len(cases), output_path)
        except PermissionError:
            logger.error("Permission denied writing to %s. Is the file open?", output_path)
            raise
        except Exception as e:
            logger.error("Error writing JSON file %s: %s", output_path, e)
            raise

    @staticmethod
    def export_cases_to_individual_json(
        cases: list[ParsedCase],
        output_dir: str | Path,
        include_metadata: bool = True,
        include_raw: bool = False,
        pretty: bool = True,
        filename_template: str = "{episode_id}.json",
    ) -> list[Path]:
        """
        Export cases to individual JSON files, one per case.

        Args:
            cases: List of ParsedCase objects to export
            output_dir: Directory to write JSON files to
            include_metadata: Include parsing warnings, confidence scores, etc.
            include_raw: Include raw/original field values for debugging
            pretty: Pretty-print JSON with indentation
            filename_template: Template for filenames using case fields (e.g., "{episode_id}.json")

        Returns:
            List of paths to created JSON files

        Raises:
            PermissionError: If output directory cannot be created/written
            IOError: If there's an error writing files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Exporting %d cases to individual JSON files in %s", len(cases), output_dir
        )

        created_files = []

        for case in cases:
            # Generate filename from template
            # Replace {episode_id} with actual episode_id, fallback to index if None
            filename = filename_template.format(
                episode_id=case.episode_id or f"case_{cases.index(case)}",
                **case.to_json_dict(include_metadata=False, include_raw=False),
            )
            output_path = output_dir / filename

            case_data = case.to_json_dict(
                include_metadata=include_metadata, include_raw=include_raw
            )

            try:
                with output_path.open("w", encoding="utf-8") as f:
                    if pretty:
                        json.dump(case_data, f, indent=2, ensure_ascii=False)
                    else:
                        json.dump(case_data, f, ensure_ascii=False)

                created_files.append(output_path)
            except Exception as e:
                logger.error(
                    "Error writing JSON file for case %s to %s: %s",
                    case.episode_id,
                    output_path,
                    e,
                )
                # Continue with other cases even if one fails

        logger.info(
            "Successfully exported %d/%d cases to individual JSON files",
            len(created_files),
            len(cases),
        )
        return created_files

    @staticmethod
    def export_cases_with_typescript_types(
        cases: list[ParsedCase],
        json_output_path: str | Path,
        types_output_path: str | Path | None = None,
        include_metadata: bool = True,
        include_raw: bool = False,
        pretty: bool = True,
    ) -> None:
        """
        Export cases to JSON with TypeScript type definitions.

        Args:
            cases: List of ParsedCase objects to export
            json_output_path: Path to output JSON file
            types_output_path: Path to output TypeScript definition file (default: same as JSON but .d.ts)
            include_metadata: Include parsing warnings, confidence scores, etc.
            include_raw: Include raw/original field values for debugging
            pretty: Pretty-print JSON with indentation

        Raises:
            PermissionError: If output file cannot be written
            IOError: If there's an error writing the file
        """
        # Export JSON first
        ExportService.export_cases_to_json(
            cases,
            json_output_path,
            include_metadata=include_metadata,
            include_raw=include_raw,
            pretty=pretty,
        )

        # Generate TypeScript types
        if types_output_path is None:
            json_path = Path(json_output_path)
            types_output_path = json_path.with_suffix(".d.ts")

        from .typescript_generator import TypeScriptGenerator

        TypeScriptGenerator.generate_type_definitions(types_output_path)

