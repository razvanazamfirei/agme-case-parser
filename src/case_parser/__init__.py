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
from .enhanced_processor import EnhancedCaseProcessor
from .export_service import ExportService
from .io import ExcelHandler
from .models import AgeRange, ColumnMap, ProcedureRule
from .processors import CaseProcessor
from .typescript_generator import TypeScriptGenerator
from .validation import ValidationReport

__version__ = "0.1.0"
__all__ = [
    "AgeCategory",
    "AgeRange",
    "AirwayManagement",
    "AnesthesiaType",
    "CaseProcessor",
    "ColumnMap",
    "EnhancedCaseProcessor",
    "ExcelHandler",
    "ExportService",
    "MonitoringTechnique",
    "ParsedCase",
    "ProcedureCategory",
    "ProcedureRule",
    "TypeScriptGenerator",
    "ValidationReport",
    "VascularAccess",
    "main",
]

