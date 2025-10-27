"""Case Parser - A tool for processing anesthesia case data from Excel files."""

from .cli import main
from .io import ExcelHandler
from .models import AgeRange, ColumnMap, ProcedureRule
from .processors import CaseProcessor

__version__ = "0.1.0"
__all__ = [
    "AgeRange",
    "CaseProcessor",
    "ColumnMap",
    "ExcelHandler",
    "ProcedureRule",
    "main",
]
