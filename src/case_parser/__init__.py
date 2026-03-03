"""Case Parser - A tool for processing anesthesia case data from Excel files."""

from .cli import main
from .domain import (
    AgeCategory,
    AirwayManagement,
    AnesthesiaType,
    MonitoringTechnique,
    ParsedCase,
    ProcedureCategory,
    VascularAccess,
)
from .io import ExcelHandler
from .models import ColumnMap
from .patterns.age_patterns import AgeRange
from .patterns.procedure_patterns import ProcedureRule
from .processor import CaseProcessor
from .validation import ValidationReport

__version__ = "0.2.0"
__all__ = [
    "AgeCategory",
    "AgeRange",
    "AirwayManagement",
    "AnesthesiaType",
    "CaseProcessor",
    "ColumnMap",
    "ExcelHandler",
    "MonitoringTechnique",
    "ParsedCase",
    "ProcedureCategory",
    "ProcedureRule",
    "ValidationReport",
    "VascularAccess",
    "main",
]
