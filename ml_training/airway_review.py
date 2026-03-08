#!/usr/bin/env python3
"""Build a focused manual-review set for airway and anesthesia targets."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from case_parser.domain import (
    AirwayTubeRoute,
    ParsedCase,
    ProcedureCategory,
)
from case_parser.io import CsvHandler, join_case_and_procedures
from case_parser.models import ColumnMap
from case_parser.patterns.anesthesia_patterns import (
    GA_NOTE_KEYWORDS,
    MAC_NOTE_KEYWORDS,
    MAC_WITHOUT_AIRWAY_PROCEDURE_KEYWORDS,
)
from case_parser.processor import CaseProcessor

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_SUPERVISED_DIR = PROJECT_ROOT / "Output-Supervised"
DEFAULT_OUTPUT = PROJECT_ROOT / "ml_training_data" / "airway_review_candidates.csv"
BUCKET_ORDER = ("double_lumen", "tube_route", "ga_mac", "control")
THORACIC_REVIEW_HINTS = (
    "THORAC",
    "PNEUMONECTOMY",
    "ESOPHAGECTOMY",
    "VATS",
    "MEDIASTIN",
    "LUNG",
    "CHEST",
    "WEDGE RESECTION",
    "THYMECTOMY",
)
NASAL_ROUTE_HINTS = (
    "NASAL",
    "NASOTRACHEAL",
    "SINUS",
    "SEPT",
    "RHINO",
    "MAXILLO",
    "LEFORT",
    "ORTHOGNATH",
    "ADENOID",
)
DOUBLE_LUMEN_HINTS = (
    "DOUBLE LUMEN",
    "DOUBLE-LUMEN",
    "BRONCHIAL BLOCKER",
)
ORAL_ROUTE_HINTS = (
    "ORAL ETT",
    "ORAL INTUB",
    "OROTRACHEAL",
)
MAC_WARNING_HINTS = (
    "INFERRED MAC FROM NOTE TEXT",
    "INFERRED MAC FROM PROCEDURE TYPE",
)
GA_WARNING_HINTS = (
    "INFERRED GENERAL ANESTHESIA FROM NOTE TEXT",
    "INFERRED GENERAL ANESTHESIA FROM AIRWAY MANAGEMENT FINDINGS",
)
DOUBLE_LUMEN_PATTERNS = (
    re.compile(r"\bDOUBLE[- ]LUMEN(\s+(TUBE|ETT))?\b"),
    re.compile(r"\bDLT\b"),
    re.compile(r"\bBRONCHIAL\s+BLOCKER\b"),
)
NASAL_ROUTE_PATTERNS = (
    re.compile(r"\bNASAL\b"),
    re.compile(r"\bNASOTRACHEAL\b"),
)
ORAL_ROUTE_PATTERNS = (
    re.compile(r"\bORAL\s+ETT\b"),
    re.compile(r"\bORAL\s+INTUB"),
    re.compile(r"\bOROTRACHEAL\b"),
)
REVIEW_COLUMNS = [
    "case_key",
    "source_file",
    "source_case_id",
    "case_date",
    "procedure",
    "procedure_category",
    "raw_anesthesia_type",
    "procedure_notes",
    "predicted_anesthesia_type",
    "predicted_ga_mac",
    "predicted_tube_route",
    "predicted_has_double_lumen_tube",
    "predicted_airway_management",
    "review_targets",
    "priority_bucket",
    "priority_score",
    "review_reasons",
    "parsing_warnings",
    "label_has_double_lumen_tube",
    "label_ga_mac",
    "label_tube_route",
    "reviewer_notes",
]


@dataclass(frozen=True)
class CaseAssessment:
    """Scored review metadata for one parsed case."""

    scores: dict[str, float]
    review_targets: tuple[str, ...]
    review_reasons: tuple[str, ...]


def _stable_fraction(text: str) -> float:
    """Return a deterministic pseudo-random fraction in [0, 1)."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0x100000000


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _matches_any_pattern(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _build_case_key(source_file: str, case: ParsedCase) -> str:
    case_id = case.episode_id or "missing-case-id"
    procedure = case.procedure or ""
    return f"{source_file}:{case_id}:{procedure[:80]}"


def _combined_case_text(case: ParsedCase) -> str:
    parts = [
        case.procedure or "",
        case.procedure_notes or "",
        case.raw_anesthesia_type or "",
    ]
    return "\n".join(part for part in parts if part).upper()


def _review_bucket_limits(max_cases: int) -> dict[str, int]:
    """Return default bucket quotas for a review run."""
    limits = dict.fromkeys(BUCKET_ORDER, 0)
    if max_cases <= 0:
        return limits

    if max_cases >= len(BUCKET_ORDER):
        for bucket in BUCKET_ORDER:
            limits[bucket] = 1
        remaining = max_cases - len(BUCKET_ORDER)
    else:
        remaining = max_cases

    weights = {
        "double_lumen": 0.3,
        "tube_route": 0.3,
        "ga_mac": 0.3,
        "control": 0.1,
    }
    exact_extras = {
        bucket: remaining * weights[bucket] for bucket in BUCKET_ORDER
    }

    for bucket in BUCKET_ORDER:
        extra = int(exact_extras[bucket])
        limits[bucket] += extra
        remaining -= extra

    bucket_priority = sorted(
        BUCKET_ORDER,
        key=lambda bucket: (
            -(exact_extras[bucket] - int(exact_extras[bucket])),
            BUCKET_ORDER.index(bucket),
        ),
    )
    for bucket in bucket_priority[:remaining]:
        limits[bucket] += 1

    return limits


def assess_case_for_review(  # noqa: PLR0912, PLR0915
    case: ParsedCase,
    *,
    source_file: str,
) -> CaseAssessment:
    """Score one parsed case for the airway/anesthesia review set."""
    text_upper = _combined_case_text(case)
    warnings_upper = "\n".join(case.parsing_warnings).upper()
    case_key = _build_case_key(source_file, case)

    scores = dict.fromkeys(BUCKET_ORDER, 0.0)
    reasons: list[str] = []
    thoracic_text_hint = _contains_any(text_upper, THORACIC_REVIEW_HINTS)

    if case.has_double_lumen_tube:
        scores["double_lumen"] += 12
        reasons.append("predicted_double_lumen")
    if _matches_any_pattern(text_upper, DOUBLE_LUMEN_PATTERNS):
        scores["double_lumen"] += 10
        reasons.append("explicit_double_lumen_text")
    if (
        case.procedure_category == ProcedureCategory.INTRATHORACIC_NON_CARDIAC
        and thoracic_text_hint
    ):
        scores["double_lumen"] += 6
        reasons.append("thoracic_category")
    if thoracic_text_hint:
        scores["double_lumen"] += 4
        reasons.append("thoracic_procedure_hint")

    if case.tube_route == AirwayTubeRoute.NASAL:
        scores["tube_route"] += 12
        reasons.append("predicted_nasal_route")
    elif case.tube_route == AirwayTubeRoute.ORAL:
        scores["tube_route"] += 5
        reasons.append("predicted_oral_route")
    if _matches_any_pattern(text_upper, NASAL_ROUTE_PATTERNS) or _contains_any(
        text_upper,
        NASAL_ROUTE_HINTS,
    ):
        scores["tube_route"] += 8
        reasons.append("nasal_route_text")
    if _matches_any_pattern(text_upper, ORAL_ROUTE_PATTERNS):
        scores["tube_route"] += 3
        reasons.append("oral_route_text")

    if case.ga_mac_inference is not None:
        if case.ga_mac_inference.value == "MAC":
            scores["ga_mac"] += 10
            reasons.append("predicted_mac")
        else:
            scores["ga_mac"] += 5
            reasons.append("predicted_ga")
    if _contains_any(text_upper, MAC_NOTE_KEYWORDS):
        scores["ga_mac"] += 8
        reasons.append("mac_note_text")
    if _contains_any(text_upper, GA_NOTE_KEYWORDS):
        scores["ga_mac"] += 4
        reasons.append("ga_note_text")
    if _contains_any(warnings_upper, MAC_WARNING_HINTS):
        scores["ga_mac"] += 4
        reasons.append("mac_inference_warning")
    if _contains_any(warnings_upper, GA_WARNING_HINTS):
        scores["ga_mac"] += 3
        reasons.append("ga_inference_warning")
    if _contains_any(text_upper, MAC_WITHOUT_AIRWAY_PROCEDURE_KEYWORDS):
        scores["ga_mac"] += 3
        reasons.append("mac_procedure_hint")
    if not case.raw_anesthesia_type and case.ga_mac_inference is not None:
        scores["ga_mac"] += 3
        reasons.append("context_only_ga_mac_inference")

    if any(score > 0 for bucket, score in scores.items() if bucket != "control"):
        review_targets = tuple(
            bucket for bucket in BUCKET_ORDER[:-1] if scores[bucket] > 0
        )
    elif case.ga_mac_inference is not None or case.airway_management:
        scores["control"] = 1 + _stable_fraction(case_key)
        review_targets = ("control",)
        reasons.append("negative_control")
    else:
        review_targets = ()

    return CaseAssessment(
        scores=scores,
        review_targets=review_targets,
        review_reasons=tuple(dict.fromkeys(reasons)),
    )


def build_review_record(
    case: ParsedCase,
    *,
    source_file: str,
    assessment: CaseAssessment,
) -> dict[str, Any]:
    """Build one review CSV row from a parsed case."""
    case_key = _build_case_key(source_file, case)
    return {
        "case_key": case_key,
        "source_file": source_file,
        "source_case_id": case.episode_id or "",
        "case_date": case.case_date.isoformat(),
        "procedure": case.procedure or "",
        "procedure_category": case.procedure_category.value,
        "raw_anesthesia_type": case.raw_anesthesia_type or "",
        "procedure_notes": case.procedure_notes or "",
        "predicted_anesthesia_type": case.anesthesia_type.value
        if case.anesthesia_type is not None
        else "",
        "predicted_ga_mac": case.ga_mac_inference.value
        if case.ga_mac_inference is not None
        else "",
        "predicted_tube_route": case.tube_route.value if case.tube_route else "",
        "predicted_has_double_lumen_tube": "Yes"
        if case.has_double_lumen_tube
        else "No",
        "predicted_airway_management": "; ".join(
            airway.value for airway in case.airway_management
        ),
        "review_targets": "; ".join(assessment.review_targets),
        "priority_bucket": "",
        "priority_score": 0.0,
        "review_reasons": "; ".join(assessment.review_reasons),
        "parsing_warnings": "; ".join(case.parsing_warnings),
        "label_has_double_lumen_tube": "",
        "label_ga_mac": "",
        "label_tube_route": "",
        "reviewer_notes": "",
    }


def _push_candidate(
    heaps: dict[str, list[tuple[float, int, dict[str, Any]]]],
    *,
    heap_limits: dict[str, int],
    record: dict[str, Any],
    assessment: CaseAssessment,
    sequence: int,
) -> None:
    for bucket, score in assessment.scores.items():
        if score <= 0:
            continue
        if heap_limits[bucket] <= 0:
            continue
        heap = heaps[bucket]
        item = (score, sequence, record)
        if len(heap) < heap_limits[bucket]:
            heapq.heappush(heap, item)
            continue
        if score > heap[0][0]:
            heapq.heapreplace(heap, item)


def _select_records(
    heaps: dict[str, list[tuple[float, int, dict[str, Any]]]],
    *,
    bucket_limits: dict[str, int],
    max_cases: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    sorted_heaps = {
        bucket: sorted(items, key=lambda item: (-item[0], item[1]))
        for bucket, items in heaps.items()
    }

    for bucket in BUCKET_ORDER:
        bucket_count = 0
        for score, _sequence, record in sorted_heaps[bucket]:
            if bucket_count >= bucket_limits[bucket]:
                break
            if record["case_key"] in seen_keys:
                continue
            selected_record = dict(record)
            selected_record["priority_bucket"] = bucket
            selected_record["priority_score"] = round(score, 4)
            selected.append(selected_record)
            seen_keys.add(record["case_key"])
            bucket_count += 1

    if len(selected) >= max_cases:
        return selected[:max_cases]

    combined: dict[str, tuple[float, int, dict[str, Any], str]] = {}
    for bucket, items in sorted_heaps.items():
        for score, sequence, record in items:
            existing = combined.get(record["case_key"])
            if existing is None or score > existing[0]:
                combined[record["case_key"]] = (score, sequence, record, bucket)

    for score, _sequence, record, bucket in sorted(
        combined.values(),
        key=lambda item: (-item[0], item[1]),
    ):
        if len(selected) >= max_cases:
            break
        if record["case_key"] in seen_keys:
            continue
        selected_record = dict(record)
        selected_record["priority_bucket"] = bucket
        selected_record["priority_score"] = round(score, 4)
        selected.append(selected_record)
        seen_keys.add(record["case_key"])

    return selected


def _discover_pair_paths(base_dir: Path) -> list[tuple[Path, Path]]:
    case_dir = base_dir / "case-list"
    proc_dir = base_dir / "procedure-list"
    if not case_dir.exists() or not proc_dir.exists():
        raise ValueError(
            f"Expected {base_dir} to contain case-list/ and procedure-list/ subdirs"
        )

    case_files = {
        path.name.replace(".Supervised.CaseList.csv", ""): path
        for path in case_dir.glob("*.CaseList.csv")
    }
    proc_files = {
        path.name.replace(".Supervised.ProcedureList.csv", ""): path
        for path in proc_dir.glob("*.ProcedureList.csv")
    }
    common = sorted(set(case_files) & set(proc_files))
    return [(case_files[name], proc_files[name]) for name in common]


def build_airway_review_dataframe(  # noqa: PLR0914
    *,
    base_dir: Path,
    max_cases: int,
    default_year: int = 2025,
) -> pd.DataFrame:
    """Build the review dataframe from supervised case/procedure exports."""
    column_map = ColumnMap()
    csv_handler = CsvHandler(column_map)
    processor = CaseProcessor(column_map, default_year=default_year, use_ml=False)

    bucket_limits = _review_bucket_limits(max_cases)
    heap_limits = {
        bucket: max(limit * 4, limit)
        for bucket, limit in bucket_limits.items()
    }
    heaps = {bucket: [] for bucket in BUCKET_ORDER}

    pair_paths = _discover_pair_paths(base_dir)
    if not pair_paths:
        raise ValueError(f"No case/procedure pairs found in {base_dir}")

    sequence = 0
    processed_cases = 0
    for case_file, proc_file in pair_paths:
        joined, _orphan_df = join_case_and_procedures(
            pd.read_csv(case_file),
            pd.read_csv(proc_file),
        )
        if joined.empty:
            continue

        normalized = csv_handler.normalize_columns(joined)
        parsed_cases = processor.process_dataframe(normalized, workers=1)
        processed_cases += len(parsed_cases)

        for case in parsed_cases:
            assessment = assess_case_for_review(case, source_file=case_file.name)
            if not assessment.review_targets:
                continue
            record = build_review_record(
                case,
                source_file=case_file.name,
                assessment=assessment,
            )
            _push_candidate(
                heaps,
                heap_limits=heap_limits,
                record=record,
                assessment=assessment,
                sequence=sequence,
            )
            sequence += 1

    selected = _select_records(
        heaps,
        bucket_limits=bucket_limits,
        max_cases=max_cases,
    )
    df = pd.DataFrame(selected)
    if df.empty:
        return pd.DataFrame(columns=REVIEW_COLUMNS)

    console.print(
        "[cyan]Scanned "
        f"{len(pair_paths)} file pair(s) and {processed_cases} cases[/cyan]"
    )
    return df.reindex(columns=REVIEW_COLUMNS)


def write_airway_review_set(
    *,
    base_dir: Path,
    output_path: Path,
    max_cases: int,
    default_year: int = 2025,
) -> pd.DataFrame:
    """Build and write the airway/anesthesia review set."""
    df = build_airway_review_dataframe(
        base_dir=base_dir,
        max_cases=max_cases,
        default_year=default_year,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df


def _print_summary(df: pd.DataFrame, output_path: Path) -> None:
    table = Table(title="Airway Review Set", border_style="cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    table.add_row("Output", str(output_path))
    table.add_row("Rows", str(len(df)))
    if not df.empty:
        for bucket in BUCKET_ORDER:
            count = int(df["priority_bucket"].eq(bucket).sum())
            table.add_row(f"{bucket} rows", str(count))
    console.print(table)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a focused review set for DLT, GA/MAC, and tube route"
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DEFAULT_SUPERVISED_DIR,
        help="Base directory containing case-list/ and procedure-list/",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output CSV path",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=600,
        help="Maximum number of review rows to emit (default: 600)",
    )
    parser.add_argument(
        "--default-year",
        type=int,
        default=2025,
        help="Fallback year for parsed case dates",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    console.print(
        Panel.fit(
            "[bold cyan]Airway/Anesthesia Review Set[/bold cyan]\n"
            f"Base dir: {Path(args.base_dir).resolve()}\n"
            f"Output: {Path(args.output).resolve()}\n"
            f"Max cases: {args.max_cases}",
            border_style="cyan",
        )
    )

    df = write_airway_review_set(
        base_dir=Path(args.base_dir).resolve(),
        output_path=Path(args.output).resolve(),
        max_cases=args.max_cases,
        default_year=args.default_year,
    )
    _print_summary(df, Path(args.output).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
