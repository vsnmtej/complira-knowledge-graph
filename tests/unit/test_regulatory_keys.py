"""
Unit tests for RegulatoryKeyGenerator (DRY principle).

Tests consistent key generation across all frameworks.

Run:
    pytest tests/unit/test_regulatory_keys.py -v
"""

import pytest
from complira_graph.utils.regulatory_keys import RegulatoryKeyGenerator as KeyGen


class TestRegulatoryKeyGenerator:
    """Test suite for key generation utilities."""

    def test_cra_keys(self):
        """Test CRA (EU Cyber Resilience Act) key generation."""
        # Annex I keys
        assert KeyGen.cra(annex="I", section=1) == "CRA_I_1"
        assert KeyGen.cra(annex="I", section=1, subpara="a") == "CRA_I_1_a"
        assert KeyGen.cra(annex="I", section=2, paragraph=1) == "CRA_I_2_1"

        # Article keys
        assert KeyGen.cra(article=13, paragraph=1) == "CRA_13_1"
        assert KeyGen.cra(article=14, paragraph=2, subpara="b") == "CRA_14_2_b"

        # Mixed annex and section
        assert KeyGen.cra(annex="II", section=3) == "CRA_II_3"

    def test_fda_524b_keys(self):
        """Test FDA Section 524B key generation."""
        assert KeyGen.fda_524b("V", "A", 1) == "FDA_524B_V_A_1"
        assert KeyGen.fda_524b("V", "C", 2) == "FDA_524B_V_C_2"
        assert KeyGen.fda_524b("VI", "B") == "FDA_524B_VI_B"

    def test_iec_62304_keys(self):
        """Test IEC 62304 key generation."""
        # Clause keys
        assert KeyGen.iec_62304(5, 1, 1) == "IEC_62304_5_1_1"
        assert KeyGen.iec_62304(5, 5, 3) == "IEC_62304_5_5_3"
        assert KeyGen.iec_62304(7, 2) == "IEC_62304_7_2"

        # Safety class keys
        assert KeyGen.iec_62304_class("A") == "IEC_62304_CLASS_A"
        assert KeyGen.iec_62304_class("B") == "IEC_62304_CLASS_B"
        assert KeyGen.iec_62304_class("C") == "IEC_62304_CLASS_C"
        assert KeyGen.iec_62304_class("c") == "IEC_62304_CLASS_C"  # Case insensitive

    def test_iso_21434_keys(self):
        """Test ISO 21434 (Automotive) key generation."""
        assert KeyGen.iso_21434(9, 1) == "ISO_21434_9_1"
        assert KeyGen.iso_21434(9, 4, 2) == "ISO_21434_9_4_2"
        assert KeyGen.iso_21434(10) == "ISO_21434_10"

    def test_nist_ssdf_keys(self):
        """Test NIST SSDF key generation."""
        assert KeyGen.nist_ssdf("PO", 1) == "NIST_SSDF_PO_1"
        assert KeyGen.nist_ssdf("PW", 1, 3) == "NIST_SSDF_PW_1_3"
        assert KeyGen.nist_ssdf("RV", 2) == "NIST_SSDF_RV_2"

    def test_nist_800_53_keys(self):
        """Test NIST 800-53 control key generation."""
        assert KeyGen.nist_800_53("AC", 1) == "NIST_800_53_AC_1"
        assert KeyGen.nist_800_53("SI", 2, 1) == "NIST_800_53_SI_2_1"
        assert KeyGen.nist_800_53("RA", 5) == "NIST_800_53_RA_5"

    def test_dora_keys(self):
        """Test DORA (Digital Operational Resilience Act) key generation."""
        assert KeyGen.dora(8, 1) == "DORA_8_1"
        assert KeyGen.dora(8, 2, "a") == "DORA_8_2_a"
        assert KeyGen.dora(10) == "DORA_10"

    def test_nis2_keys(self):
        """Test NIS2 Directive key generation."""
        assert KeyGen.nis2(21, 1) == "NIS2_21_1"
        assert KeyGen.nis2(21, 2, "b") == "NIS2_21_2_b"

    def test_key_validation(self):
        """Test key validation."""
        # Valid keys
        assert KeyGen.validate_key("CRA_I_1_a") is True
        assert KeyGen.validate_key("FDA_524B_V_A_1") is True
        assert KeyGen.validate_key("IEC_62304_5_5_3") is True
        assert KeyGen.validate_key("NIST_SSDF_PW_1_3") is True

        # Invalid keys
        assert KeyGen.validate_key("cra-i-1-a") is False  # Wrong separator
        assert KeyGen.validate_key("CRA_I_1 a") is False  # Space
        assert KeyGen.validate_key("UNKNOWN_1_2") is False  # Unknown framework
        assert KeyGen.validate_key("") is False  # Empty
        assert KeyGen.validate_key(None) is False  # None

    def test_framework_extraction(self):
        """Test framework extraction from keys."""
        assert KeyGen.extract_framework("CRA_I_1_a") == "CRA"
        assert KeyGen.extract_framework("FDA_524B_V_A_1") == "FDA_524B"
        assert KeyGen.extract_framework("IEC_62304_5_5_3") == "IEC_62304"
        assert KeyGen.extract_framework("ISO_21434_9_1") == "ISO_21434"
        assert KeyGen.extract_framework("NIST_SSDF_PW_1_3") == "NIST_SSDF"
        assert KeyGen.extract_framework("NIST_800_53_AC_1") == "NIST_800_53"
        assert KeyGen.extract_framework("DORA_8_1") == "DORA"
        assert KeyGen.extract_framework("NIS2_21_1") == "NIS2"

        # Invalid keys
        assert KeyGen.extract_framework("UNKNOWN_1") is None
        assert KeyGen.extract_framework("") is None
        assert KeyGen.extract_framework(None) is None

    def test_prefix_normalization(self):
        """Test that common prefixes are removed."""
        # "Annex " should be removed
        key = KeyGen.generate("CRA", "Annex I", 1)
        assert key == "CRA_I_1"

        # "Article " should be removed
        key = KeyGen.generate("CRA", "Article 13", 1)
        assert key == "CRA_13_1"

        # "Clause " should be removed
        key = KeyGen.generate("IEC_62304", "Clause 5", 1)
        assert key == "IEC_62304_5_1"

    def test_none_values_handled(self):
        """Test that None values are skipped."""
        key = KeyGen.cra(annex="I", section=1, paragraph=None, subpara=None)
        assert key == "CRA_I_1"

        key = KeyGen.fda_524b("V", "A", None)
        assert key == "FDA_524B_V_A"

    def test_special_characters_normalized(self):
        """Test that special characters are normalized."""
        # Spaces become underscores
        key = KeyGen.generate("TEST", "Part I", "Section 1")
        assert key == "TEST_I_1"

        # Hyphens become underscores
        key = KeyGen.generate("TEST", "1-2", "3-4")
        assert key == "TEST_1_2_3_4"

        # Parentheses removed
        key = KeyGen.generate("TEST", "(a)", "(1)")
        assert key == "TEST_a_1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
