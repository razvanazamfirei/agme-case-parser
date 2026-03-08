"""Tests for canonical block-site term mapping."""

from __future__ import annotations

from case_parser.patterns.block_site_patterns import normalize_block_site_terms


def test_maps_known_peripheral_term_to_canonical_value():
    assert normalize_block_site_terms("Femoral nerve block") == "Femoral"


def test_maps_multiple_peripheral_terms_in_canonical_order():
    value = "Sciatic and Popliteal with femoral rescue block"
    assert normalize_block_site_terms(value) == "Femoral; Popliteal; Sciatic"


def test_maps_unknown_peripheral_context_to_other():
    result = normalize_block_site_terms(
        "Brachial plexus block",
        procedure_name="Peripheral nerve block",
    )
    assert result == "Other - peripheral nerve blockade site"


def test_maps_neuraxial_lumbar_from_spinal_default():
    result = normalize_block_site_terms(
        None,
        procedure_name="Spinal",
    )
    assert result == "Lumbar"


def test_maps_neuraxial_thoracic_low_band_from_level_range():
    result = normalize_block_site_terms(
        "Thoracic epidural T10-11",
        procedure_name="Epidural",
    )
    assert result == "T 8-12"


def test_maps_neuraxial_thoracic_to_both_bands_when_range_crosses():
    result = normalize_block_site_terms(
        "Thoracic epidural T6-T9",
        procedure_name="Epidural",
    )
    assert result == "T 1-7; T 8-12"


def test_maps_generic_thoracic_to_both_bands():
    result = normalize_block_site_terms(
        "Thoracic epidural",
        procedure_name="Epidural",
    )
    assert result == "T 1-7; T 8-12"


def test_combines_peripheral_and_neuraxial_terms():
    result = normalize_block_site_terms(
        "Femoral block and thoracic epidural T10",
        procedure_name="Peripheral nerve block and epidural",
    )
    assert result == "Femoral; T 8-12"


def test_does_not_map_notes_without_block_context():
    result = normalize_block_site_terms(
        None,
        procedure_name="General",
        procedure_notes="Lumbar drain inserted and femoral line placed",
    )
    assert result is None


def test_returns_raw_primary_block_if_no_context_and_no_term_match():
    assert normalize_block_site_terms("Unclassified value") == "Unclassified value"
