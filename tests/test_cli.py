"""Tests for standalone orphan splitting logic in CLI flow."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from case_parser.cli import (
    _ProcessingOptions,
    main,
    process_csv,
    split_standalone_cases,
)
from case_parser.domain import ParsedCase
from case_parser.models import ColumnMap


def _standalone_case(  # noqa: PLR0913
    *,
    case_id: str,
    procedure_name: str | None,
    procedure: str | None = None,
    notes: str | None = None,
    block: str | None = None,
    raw_block: str | None = None,
    unmatched_block_source: str | None = None,
) -> ParsedCase:
    return ParsedCase(
        raw_date="2025-01-01",
        episode_id=case_id,
        raw_age=30.0,
        raw_asa="2",
        emergent=False,
        raw_anesthesia_type=procedure_name,
        services=[],
        procedure=procedure,
        procedure_notes=notes,
        responsible_provider="SMITH, JANE",
        nerve_block_type=block,
        raw_nerve_block_type=raw_block,
        unmatched_block_source=unmatched_block_source,
        case_date=date(2025, 1, 1),
    )


def test_split_standalone_cases_routes_blocks_and_neuraxial():
    cases = [
        _standalone_case(case_id="B1", procedure_name="Peripheral nerve block"),
        _standalone_case(case_id="N1", procedure_name="Labor Epidural"),
        _standalone_case(case_id="N2", procedure_name="CSE"),
    ]

    block_cases, neuraxial_cases = split_standalone_cases(cases)

    assert [c.episode_id for c in block_cases] == ["B1"]
    assert [c.episode_id for c in neuraxial_cases] == ["N1", "N2"]


def test_split_standalone_cases_treats_block_site_only_as_block():
    cases = [
        _standalone_case(
            case_id="B2",
            procedure_name="Unknown Procedure",
            block="Femoral",
        ),
    ]

    block_cases, neuraxial_cases = split_standalone_cases(cases)

    assert [c.episode_id for c in block_cases] == ["B2"]
    assert neuraxial_cases == []


def test_split_standalone_cases_defaults_unknown_to_neuraxial_bucket():
    cases = [
        _standalone_case(case_id="X1", procedure_name="Unknown Procedure"),
    ]

    block_cases, neuraxial_cases = split_standalone_cases(cases)

    assert block_cases == []
    assert [c.episode_id for c in neuraxial_cases] == ["X1"]


def test_split_standalone_cases_routes_canonical_neuraxial_sites_correctly():
    cases = [
        _standalone_case(
            case_id="N3",
            procedure_name="Unknown Procedure",
            block="Lumbar",
        ),
    ]

    block_cases, neuraxial_cases = split_standalone_cases(cases)

    assert block_cases == []
    assert [c.episode_id for c in neuraxial_cases] == ["N3"]


def test_split_standalone_cases_uses_preserved_raw_block_text():
    cases = [
        _standalone_case(
            case_id="B3",
            procedure_name="Unknown Procedure",
            unmatched_block_source="Serratus plane block",
        ),
    ]

    block_cases, neuraxial_cases = split_standalone_cases(cases)

    assert [c.episode_id for c in block_cases] == ["B3"]
    assert neuraxial_cases == []


def test_split_standalone_cases_prefers_normalized_peripheral_block_over_text_hint():
    cases = [
        _standalone_case(
            case_id="B4",
            procedure_name="Unknown Procedure",
            notes="Lumbar plexus block",
            block="Lumbar Plexus",
        ),
    ]

    block_cases, neuraxial_cases = split_standalone_cases(cases)

    assert [c.episode_id for c in block_cases] == ["B4"]
    assert neuraxial_cases == []


def test_process_csv_returns_standalone_case_count(tmp_path: Path):
    columns = ColumnMap()
    options = _ProcessingOptions(
        default_year=2025,
        sheet_name=None,
        use_ml=False,
        ml_threshold=0.7,
        workers=1,
    )
    processor = Mock()
    orphan_cases = [
        _standalone_case(case_id="B5", procedure_name="Peripheral nerve block"),
        _standalone_case(case_id="N5", procedure_name="Labor Epidural"),
    ]
    processor.process_dataframe.side_effect = [[], orphan_cases]
    processor.cases_to_dataframe.return_value = pd.DataFrame()

    with (
        patch(
            "case_parser.cli.CsvHandler.read",
            return_value=(pd.DataFrame(), pd.DataFrame([{"orphan": True}])),
        ),
        patch("case_parser.cli._build_processor", return_value=processor),
        patch(
            "case_parser.cli.split_standalone_cases",
            return_value=([orphan_cases[0]], [orphan_cases[1]]),
        ),
        patch("case_parser.cli._write_standalone_output") as write_standalone,
    ):
        all_cases, output_df, standalone_case_count = process_csv(
            input_path=tmp_path,
            output_path=tmp_path / "out.xlsx",
            columns=columns,
            excel_handler=Mock(),
            options=options,
        )

    assert all_cases == []
    assert output_df.empty
    assert standalone_case_count == 2
    assert write_standalone.call_count == 2


def test_main_uses_standalone_signal_when_no_main_cases(tmp_path: Path):
    args = SimpleNamespace(
        input_file=str(tmp_path),
        output_file=str(tmp_path / "out.xlsx"),
        default_year=2025,
        sheet=None,
        no_ml=True,
        ml_threshold=0.7,
        workers=1,
        v2=True,
        validation_report=None,
        log_level="INFO",
        verbose=False,
    )
    parser = Mock()
    parser.parse_args.return_value = args

    with (
        patch("case_parser.cli.build_arg_parser", return_value=parser),
        patch("case_parser.cli.setup_logging"),
        patch("case_parser.cli.validate_arguments"),
        patch("case_parser.cli.columns_from_args", return_value=ColumnMap()),
        patch("case_parser.cli.ExcelHandler", return_value=Mock()),
        patch(
            "case_parser.cli.process_csv",
            return_value=([], pd.DataFrame(), 2),
        ),
        patch("case_parser.cli.console.print") as console_print,
    ):
        result = main()

    printed_messages = [
        " ".join(str(arg) for arg in call.args) for call in console_print.call_args_list
    ]
    assert result is None
    assert any("standalone orphan outputs were written" in msg for msg in printed_messages)
    assert not any("No cases to process" in msg for msg in printed_messages)
