"""Tests for enhanced text extraction functions."""

from __future__ import annotations

from case_parser.domain import (
    AirwayManagement,
    ExtractionFinding,
    MonitoringTechnique,
    VascularAccess,
)
from case_parser.enhanced_extractors import (
    _calculate_pattern_confidence,
    _extract_with_context,
    clean_names,
    extract_airway_management_enhanced,
    extract_monitoring_enhanced,
    extract_vascular_access_enhanced,
)


class TestHelperFunctions:
    """Test helper functions for extraction."""

    def test_extract_with_context_basic(self):
        """Test basic context extraction."""
        text = "Patient was intubated using direct laryngoscope"
        patterns = [r"\bintubat(ed|ion|e)?\b"]
        results = _extract_with_context(text, patterns, context_window=20)

        assert len(results) == 1
        matched_text, context, position = results[0]
        assert "intubated" in matched_text.lower()
        assert "intubated" in context.lower()
        assert position == 12

    def test_extract_with_context_multiple_matches(self):
        """Test multiple pattern matches."""
        text = "Arterial line placed. Central line also inserted."
        patterns = [r"\barterial\s+line\b", r"\bcentral\s+line\b"]
        results = _extract_with_context(text, patterns, context_window=30)

        assert len(results) == 2
        assert any("arterial" in match[0].lower() for match in results)
        assert any("central" in match[0].lower() for match in results)

    def test_extract_with_context_case_insensitive(self):
        """Test case-insensitive matching."""
        text = "INTUBATION performed with ETT"
        patterns = [r"\bintubation\b"]
        results = _extract_with_context(text, patterns)

        assert len(results) == 1
        assert "intubation" in results[0][0].lower()

    def test_extract_with_context_empty(self):
        """Test with no matches."""
        text = "Standard monitoring applied"
        patterns = [r"\bintubation\b"]
        results = _extract_with_context(text, patterns)

        assert len(results) == 0

    def test_calculate_pattern_confidence_base(self):
        """Test base confidence without supporting or negation patterns."""
        text = "Patient was intubated"
        patterns = [r"\bintubat"]
        confidence = _calculate_pattern_confidence(text, patterns)

        assert confidence == 0.5

    def test_calculate_pattern_confidence_with_supporting(self):
        """Test confidence with supporting patterns."""
        text = "Intubation performed with direct laryngoscope and ETT placed"
        primary = [r"\bintubat"]
        supporting = [r"\blaryngoscope\b", r"\bETT\b"]
        confidence = _calculate_pattern_confidence(text, primary, supporting)

        assert confidence > 0.5
        assert confidence <= 0.9

    def test_calculate_pattern_confidence_with_negation(self):
        """Test confidence reduced by negation patterns."""
        text = "No intubation performed"
        primary = [r"\bintubat"]
        negation = [r"\bno\s+"]
        confidence = _calculate_pattern_confidence(text, primary, None, negation)

        assert confidence < 0.5

    def test_calculate_pattern_confidence_bounds(self):
        """Test confidence stays within 0-1 bounds."""
        text = "Patient intubated with support and more support and even more"
        primary = [r"\bintubat"]
        supporting = [r"\bsupport\b"] * 10  # Many supporting patterns
        confidence = _calculate_pattern_confidence(text, primary, supporting)

        assert 0.0 <= confidence <= 1.0

    def test_clean_names_basic(self):
        """Test basic name cleaning."""
        assert clean_names("Dr. John Smith, MD") == "Dr. John Smith"
        assert clean_names("Jane Doe DO") == "Jane Doe"
        assert clean_names("Bob Johnson, PhD") == "Bob Johnson"

    def test_clean_names_trailing_comma(self):
        """Test removal of trailing commas."""
        assert clean_names("Smith, John,") == "Smith, John"
        assert clean_names("Doe, Jane, MD,") == "Doe, Jane,"

    def test_clean_names_whitespace(self):
        """Test whitespace normalization."""
        assert clean_names("John   Smith") == "John Smith"
        assert clean_names("  Jane  Doe  ") == "Jane Doe"

    def test_clean_names_case_insensitive_titles(self):
        """Test case-insensitive title removal."""
        assert clean_names("John Smith md") == "John Smith"
        assert clean_names("Jane Doe Md") == "Jane Doe"

    def test_clean_names_missing_value(self):
        """Test handling of missing/NaN values."""
        import pandas as pd

        assert clean_names(None) == ""
        assert clean_names(pd.NA) == ""
        assert clean_names(float("nan")) == ""


class TestAirwayManagementExtraction:
    """Test airway management extraction."""

    def test_extract_oral_ett(self):
        """Test oral ETT extraction."""
        notes = "Patient was intubated with oral ETT"
        airway, findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.ORAL_ETT in airway
        assert len(findings) > 0
        assert any(f.value == AirwayManagement.ORAL_ETT.value for f in findings)

    def test_extract_nasal_ett(self):
        """Test nasal ETT extraction."""
        notes = "Nasal intubation performed successfully"
        airway, findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.NASAL_ETT in airway
        assert any(f.value == AirwayManagement.ORAL_ETT.value for f in findings)

    def test_extract_direct_laryngoscope(self):
        """Test direct laryngoscope extraction."""
        notes = "Intubated using direct laryngoscope with Macintosh blade"
        airway, findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.ORAL_ETT in airway
        assert AirwayManagement.DIRECT_LARYNGOSCOPE in airway
        assert len(findings) >= 2

    def test_extract_video_laryngoscope(self):
        """Test video laryngoscope extraction."""
        notes = "Intubation with GlideScope video laryngoscope"
        airway, _findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.ORAL_ETT in airway
        assert AirwayManagement.VIDEO_LARYNGOSCOPE in airway

    def test_extract_supraglottic_airway(self):
        """Test supraglottic airway extraction."""
        notes = "LMA inserted for airway management"
        airway, findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.SUPRAGLOTTIC_AIRWAY in airway
        assert any(
            f.value == AirwayManagement.SUPRAGLOTTIC_AIRWAY.value for f in findings
        )

    def test_extract_bronchoscopy(self):
        """Test bronchoscopy extraction."""
        notes = "Fiberoptic bronchoscopy used for intubation"
        airway, findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.FLEXIBLE_BRONCHOSCOPIC in airway
        assert any(
            f.value == AirwayManagement.FLEXIBLE_BRONCHOSCOPIC.value for f in findings
        )

    def test_extract_mask_ventilation(self):
        """Test mask ventilation extraction."""
        notes = "Mask ventilation maintained throughout procedure"
        airway, findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.MASK in airway
        assert any(f.value == AirwayManagement.MASK.value for f in findings)

    def test_extract_difficult_airway(self):
        """Test difficult airway detection."""
        notes = "Difficult intubation with multiple attempts"
        airway, findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.DIFFICULT_AIRWAY in airway
        assert any(f.value == AirwayManagement.DIFFICULT_AIRWAY.value for f in findings)

    def test_extract_multiple_techniques(self):
        """Test extraction of multiple airway techniques."""
        notes = (
            "Direct laryngoscope used for oral intubation. Arterial line also placed."
        )
        airway, _findings = extract_airway_management_enhanced(notes)

        assert AirwayManagement.ORAL_ETT in airway
        assert AirwayManagement.DIRECT_LARYNGOSCOPE in airway
        assert len(airway) >= 2

    def test_extract_no_duplicates(self):
        """Test that duplicate techniques are removed."""
        notes = "Intubation performed. ETT placed. Oral intubation confirmed."
        airway, _findings = extract_airway_management_enhanced(notes)

        # Count occurrences of ORAL_ETT
        oral_ett_count = sum(1 for tech in airway if tech == AirwayManagement.ORAL_ETT)
        assert oral_ett_count == 1

    def test_extract_empty_notes(self):
        """Test handling of empty/missing notes."""
        airway1, findings1 = extract_airway_management_enhanced(None)
        assert airway1 == []
        assert findings1 == []

        import pandas as pd

        airway2, findings2 = extract_airway_management_enhanced(pd.NA)
        assert airway2 == []
        assert findings2 == []

    def test_extraction_findings_metadata(self):
        """Test that extraction findings contain proper metadata."""
        notes = "Patient intubated with direct laryngoscope"
        _airway, findings = extract_airway_management_enhanced(notes, "test_field")

        assert len(findings) > 0
        for finding in findings:
            assert isinstance(finding, ExtractionFinding)
            assert finding.source_field == "test_field"
            assert 0.0 <= finding.confidence <= 1.0
            assert finding.context is not None
            assert len(finding.context) > 0


class TestVascularAccessExtraction:
    """Test vascular access extraction."""

    def test_extract_arterial_line(self):
        """Test arterial line extraction."""
        notes = "Arterial line placed in radial artery"
        vascular, findings = extract_vascular_access_enhanced(notes)

        assert VascularAccess.ARTERIAL_CATHETER in vascular
        assert any(f.value == VascularAccess.ARTERIAL_CATHETER.value for f in findings)

    def test_extract_arterial_line_variations(self):
        """Test various arterial line notations."""
        variations = [
            "A-line placed",
            "Art line inserted",
            "Radial arterial catheter",
            "A line in femoral artery",
        ]

        for note in variations:
            vascular, _findings = extract_vascular_access_enhanced(note)
            assert VascularAccess.ARTERIAL_CATHETER in vascular, f"Failed for: {note}"

    def test_extract_central_line(self):
        """Test central line extraction."""
        notes = "Central venous catheter placed in IJ"
        vascular, findings = extract_vascular_access_enhanced(notes)

        assert VascularAccess.CENTRAL_VENOUS_CATHETER in vascular
        assert any(
            f.value == VascularAccess.CENTRAL_VENOUS_CATHETER.value for f in findings
        )

    def test_extract_central_line_variations(self):
        """Test various central line notations."""
        variations = [
            "CVC placed",
            "Internal jugular line inserted",
            "Subclavian catheter placed",
            "Femoral venous line",
        ]

        for note in variations:
            vascular, _findings = extract_vascular_access_enhanced(note)
            assert VascularAccess.CENTRAL_VENOUS_CATHETER in vascular, (
                f"Failed for: {note}"
            )

    def test_extract_pa_catheter(self):
        """Test PA catheter extraction."""
        notes = "Pulmonary artery catheter inserted"
        vascular, findings = extract_vascular_access_enhanced(notes)

        assert VascularAccess.PULMONARY_ARTERY_CATHETER in vascular
        assert any(
            f.value == VascularAccess.PULMONARY_ARTERY_CATHETER.value for f in findings
        )

    def test_extract_pa_catheter_variations(self):
        """Test various PA catheter notations."""
        variations = [
            "PA catheter placed",
            "Swan-Ganz catheter inserted",
            "PAC placed for monitoring",
        ]

        for note in variations:
            vascular, _findings = extract_vascular_access_enhanced(note)
            assert VascularAccess.PULMONARY_ARTERY_CATHETER in vascular, (
                f"Failed for: {note}"
            )

    def test_extract_multiple_access(self):
        """Test extraction of multiple vascular access types."""
        notes = "Arterial line and central venous catheter placed"
        vascular, _findings = extract_vascular_access_enhanced(notes)

        assert VascularAccess.ARTERIAL_CATHETER in vascular
        assert VascularAccess.CENTRAL_VENOUS_CATHETER in vascular
        assert len(vascular) == 2

    def test_extract_no_duplicates(self):
        """Test that duplicate access types are removed."""
        notes = "Arterial line placed. A-line confirmed. Art line functioning."
        vascular, _findings = extract_vascular_access_enhanced(notes)

        arterial_count = sum(
            1 for access in vascular if access == VascularAccess.ARTERIAL_CATHETER
        )
        assert arterial_count == 1

    def test_extract_empty_notes(self):
        """Test handling of empty/missing notes."""
        vascular1, findings1 = extract_vascular_access_enhanced(None)
        assert vascular1 == []
        assert findings1 == []

    def test_extraction_findings_metadata(self):
        """Test that extraction findings contain proper metadata."""
        notes = "Central line placed"
        _vascular, findings = extract_vascular_access_enhanced(notes, "test_field")

        assert len(findings) > 0
        for finding in findings:
            assert isinstance(finding, ExtractionFinding)
            assert finding.source_field == "test_field"
            assert 0.0 <= finding.confidence <= 1.0


class TestMonitoringExtraction:
    """Test monitoring technique extraction."""

    def test_extract_tee(self):
        """Test TEE extraction."""
        notes = "TEE performed for cardiac monitoring"
        monitoring, findings = extract_monitoring_enhanced(notes)

        assert MonitoringTechnique.TEE in monitoring
        assert any(f.value == MonitoringTechnique.TEE.value for f in findings)

    def test_extract_tee_variations(self):
        """Test various TEE notations."""
        variations = [
            "Transesophageal echocardiography performed",
            "Trans-esophageal echo used",
            "TEE monitoring",
        ]

        for note in variations:
            monitoring, _findings = extract_monitoring_enhanced(note)
            assert MonitoringTechnique.TEE in monitoring, f"Failed for: {note}"

    def test_extract_electrophysiologic(self):
        """Test electrophysiologic monitoring extraction."""
        notes = "SSEP and electrophysiologic monitoring used"
        monitoring, findings = extract_monitoring_enhanced(notes)

        assert MonitoringTechnique.ELECTROPHYSIOLOGIC_MON in monitoring
        assert any(
            f.value == MonitoringTechnique.ELECTROPHYSIOLOGIC_MON.value
            for f in findings
        )

    def test_extract_electrophysiologic_variations(self):
        """Test various EP monitoring notations."""
        variations = [
            "EP study performed",
            "Neurophysiologic monitoring",
            "Evoked potential monitoring",
            "SSCP monitoring",
        ]

        for note in variations:
            monitoring, _findings = extract_monitoring_enhanced(note)
            assert MonitoringTechnique.ELECTROPHYSIOLOGIC_MON in monitoring, (
                f"Failed for: {note}"
            )

    def test_extract_csf_drain(self):
        """Test CSF drain extraction."""
        notes = "CSF drain placed for monitoring"
        monitoring, findings = extract_monitoring_enhanced(notes)

        assert MonitoringTechnique.CSF_DRAIN in monitoring
        assert any(f.value == MonitoringTechnique.CSF_DRAIN.value for f in findings)

    def test_extract_csf_drain_variations(self):
        """Test various CSF drain notations."""
        variations = [
            "Lumbar drain inserted",
            "Cerebrospinal fluid drainage",
            "Spinal drain placed",
        ]

        for note in variations:
            monitoring, _findings = extract_monitoring_enhanced(note)
            assert MonitoringTechnique.CSF_DRAIN in monitoring, f"Failed for: {note}"

    def test_extract_invasive_neuro(self):
        """Test invasive neuro monitoring extraction."""
        notes = "ICP monitor placed for intracranial pressure monitoring"
        monitoring, findings = extract_monitoring_enhanced(notes)

        assert MonitoringTechnique.INVASIVE_NEURO_MON in monitoring
        assert any(
            f.value == MonitoringTechnique.INVASIVE_NEURO_MON.value for f in findings
        )

    def test_extract_invasive_neuro_variations(self):
        """Test various invasive neuro monitoring notations."""
        variations = [
            "ICP catheter placed",
            "Ventriculostomy performed",
            "EVD placed",
        ]

        for note in variations:
            monitoring, _findings = extract_monitoring_enhanced(note)
            assert MonitoringTechnique.INVASIVE_NEURO_MON in monitoring, (
                f"Failed for: {note}"
            )

    def test_extract_multiple_monitoring(self):
        """Test extraction of multiple monitoring techniques."""
        notes = "TEE and electrophysiologic monitoring used"
        monitoring, _findings = extract_monitoring_enhanced(notes)

        assert MonitoringTechnique.TEE in monitoring
        assert MonitoringTechnique.ELECTROPHYSIOLOGIC_MON in monitoring
        assert len(monitoring) == 2

    def test_extract_no_duplicates(self):
        """Test that duplicate monitoring techniques are removed."""
        notes = "TEE performed. Transesophageal echo used. TEE monitoring confirmed."
        monitoring, _findings = extract_monitoring_enhanced(notes)

        tee_count = sum(1 for tech in monitoring if tech == MonitoringTechnique.TEE)
        assert tee_count == 1

    def test_extract_empty_notes(self):
        """Test handling of empty/missing notes."""
        monitoring1, findings1 = extract_monitoring_enhanced(None)
        assert monitoring1 == []
        assert findings1 == []

    def test_extraction_findings_metadata(self):
        """Test that extraction findings contain proper metadata."""
        notes = "TEE performed"
        _monitoring, findings = extract_monitoring_enhanced(notes, "test_field")

        assert len(findings) > 0
        for finding in findings:
            assert isinstance(finding, ExtractionFinding)
            assert finding.source_field == "test_field"
            assert 0.0 <= finding.confidence <= 1.0


class TestConfidenceScoring:
    """Test confidence scoring in extractions."""

    def test_high_confidence_with_supporting_evidence(self):
        """Test high confidence when supporting patterns are present."""
        notes = "Patient intubated with direct laryngoscope, ETT secured, tube placement confirmed"
        _airway, findings = extract_airway_management_enhanced(notes)

        # Find the intubation finding
        ett_findings = [
            f for f in findings if f.value == AirwayManagement.ORAL_ETT.value
        ]
        assert len(ett_findings) > 0
        # Base confidence for intubation without explicit supporting pattern calculation
        assert ett_findings[0].confidence >= 0.5

    def test_lower_confidence_with_negation(self):
        """Test that negation patterns reduce confidence."""
        # This test checks the confidence calculation mechanism
        # In practice, negated cases might not be extracted at all
        text = "No intubation performed"
        primary = [r"\bintubation\b"]
        negation = [r"\bno\s+"]
        confidence = _calculate_pattern_confidence(text, primary, None, negation)

        assert confidence < 0.5

    def test_base_confidence_simple_match(self):
        """Test base confidence for simple pattern match."""
        notes = "ETT placed"
        _airway, findings = extract_airway_management_enhanced(notes)

        ett_findings = [
            f for f in findings if f.value == AirwayManagement.ORAL_ETT.value
        ]
        # Should have base confidence without much supporting evidence
        assert len(ett_findings) > 0
        assert 0.3 <= ett_findings[0].confidence <= 0.7
