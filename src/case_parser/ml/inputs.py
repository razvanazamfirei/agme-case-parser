"""Shared feature-input helpers for ML training and inference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .config import SERVICE_COLUMN_CANDIDATES


@dataclass(frozen=True)
class FeatureInput:
    """Normalized ML feature input used across training and inference."""

    procedure_text: str
    service_text: str = ""
    rule_category: str = ""
    rule_warning_count: int = 0


def coerce_text(value: Any) -> str:
    """Convert optional scalar values to stable strings."""
    if value is None:
        return ""

    text = str(value).strip()
    if text in {"", "<NA>", "nan", "NaN", "None"}:
        return ""
    return text


def coerce_service_text(value: Any) -> str:
    """Normalize service inputs to a newline-separated string."""
    if isinstance(value, list):
        normalized_items = [coerce_text(item) for item in value]
        return "\n".join(item for item in normalized_items if item)
    return coerce_text(value)


def parse_int(value: Any, default: int = 0) -> int:
    """Safely normalize optional integer-like values."""
    if value is None:
        return default
    if isinstance(value, str):
        text = coerce_text(value)
        if text == "":
            return default
        try:
            return int(text)
        except ValueError:
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_service_alias_value(item: Mapping[str, Any]) -> str:
    """Return the first non-empty service alias from a raw input mapping."""
    for candidate in SERVICE_COLUMN_CANDIDATES:
        if candidate not in item:
            continue
        service_text = coerce_service_text(item.get(candidate))
        if service_text:
            return service_text
    return ""


def feature_input_from_raw(item: Any) -> FeatureInput:
    """Normalize one raw item into the shared FeatureInput schema."""
    if isinstance(item, FeatureInput):
        return item

    if isinstance(item, Mapping):
        return FeatureInput(
            procedure_text=coerce_text(
                item.get("procedure_text", item.get("procedure", ""))
            ),
            service_text=_coerce_service_alias_value(item),
            rule_category=coerce_text(item.get("rule_category", "")),
            rule_warning_count=parse_int(item.get("rule_warning_count", 0)),
        )

    return FeatureInput(procedure_text=coerce_text(item))


def normalize_feature_inputs(items: Sequence[Any]) -> list[FeatureInput]:
    """Normalize raw ML feature inputs into a consistent internal structure."""
    return [feature_input_from_raw(item) for item in items]


def build_feature_inputs(
    procedure_texts: Sequence[Any],
    services_list: Sequence[Any] | None = None,
    rule_categories: Sequence[Any] | None = None,
    rule_warning_counts: Sequence[Any] | None = None,
) -> list[FeatureInput]:
    """Build batched FeatureInput objects from parallel procedure metadata."""
    expected_length = len(procedure_texts)
    services_seq = _normalize_parallel_values(
        name="services_list",
        values=services_list,
        default_value="",
        expected_length=expected_length,
    )
    categories_seq = _normalize_parallel_values(
        name="rule_categories",
        values=rule_categories,
        default_value="",
        expected_length=expected_length,
    )
    warnings_seq = _normalize_parallel_values(
        name="rule_warning_counts",
        values=rule_warning_counts,
        default_value=0,
        expected_length=expected_length,
    )

    return [
        FeatureInput(
            procedure_text=coerce_text(procedure_text),
            service_text=coerce_service_text(service_text),
            rule_category=coerce_text(rule_category),
            rule_warning_count=parse_int(rule_warning_count),
        )
        for procedure_text, service_text, rule_category, rule_warning_count in zip(
            procedure_texts,
            services_seq,
            categories_seq,
            warnings_seq,
            strict=False,
        )
    ]


def resolve_service_column(
    columns_source: Any,
    requested_column: str | None = None,
) -> str | None:
    """Return the configured service column name when available."""
    columns = getattr(columns_source, "columns", columns_source)

    if requested_column:
        return requested_column if requested_column in columns else None

    for candidate in SERVICE_COLUMN_CANDIDATES:
        if candidate in columns:
            return candidate
    return None


def _normalize_parallel_values(
    *,
    name: str,
    values: Sequence[Any] | None,
    default_value: Any,
    expected_length: int,
) -> Sequence[Any]:
    """Validate optional parallel metadata sequences against procedure count."""
    if values is None:
        return [default_value for _ in range(expected_length)]
    if len(values) != expected_length:
        raise ValueError(f"{name} must match procedure_texts length")
    return values
