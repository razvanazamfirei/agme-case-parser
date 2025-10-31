"""Custom exceptions for the case parser."""

from __future__ import annotations


class CaseParserError(Exception):
    """Base exception for case parser errors."""

    pass


class DataValidationError(CaseParserError):
    """Raised when input data validation fails."""

    pass


class FileProcessingError(CaseParserError):
    """Raised when file processing fails."""

    pass


class ConfigurationError(CaseParserError):
    """Raised when configuration is invalid."""

    pass

