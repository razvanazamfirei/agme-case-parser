"""Tests for batch_process CLI defaults."""

from __future__ import annotations

import sys
from dataclasses import dataclass

import batch_process


def test_parse_args_defaults_to_ml(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["batch_process.py"])

    args = batch_process._parse_args()

    assert args.use_ml is True


def test_parse_args_no_ml_disables_ml(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["batch_process.py", "--no-ml"])

    args = batch_process._parse_args()

    assert args.use_ml is False


def test_get_worker_processor_caches_per_column_map(monkeypatch):
    created_columns: list[batch_process.ColumnMap] = []

    @dataclass
    class _DummyProcessor:
        columns: batch_process.ColumnMap
        default_year: int
        use_ml: bool

        def __init__(
            self,
            columns: batch_process.ColumnMap,
            default_year: int,
            use_ml: bool,
        ) -> None:
            self.columns = columns
            self.default_year = default_year
            self.use_ml = use_ml
            created_columns.append(columns)

    batch_process._WORKER_PROCESSORS.clear()
    monkeypatch.setattr(batch_process, "CaseProcessor", _DummyProcessor)
    monkeypatch.setattr(batch_process.os, "getpid", lambda: 4242)

    first_columns = batch_process.ColumnMap(procedure="Procedure A")
    second_columns = batch_process.ColumnMap(procedure="Procedure B")

    first = batch_process._get_worker_processor(first_columns, use_ml=True)
    first_again = batch_process._get_worker_processor(first_columns, use_ml=True)
    second = batch_process._get_worker_processor(second_columns, use_ml=True)

    assert first is first_again
    assert second is not first
    assert created_columns == [first_columns, second_columns]
    batch_process._WORKER_PROCESSORS.clear()
