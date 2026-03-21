"""
Unit tests for CycloneDX parser.

Tests:
- GHSA identifier validation
- Enriched severity format (direct severity field)
- Standard severity format (ratings array)
- Root component extraction (metadata.component)
- Dependency component extraction (components[])
- Both old tool format (tools: []) and new format (tools: {components: []})
"""

import pytest
from api.parsers.cyclonedx import CycloneDXParser


class TestCycloneDXParser:
    """Test CycloneDX parser functionality."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return CycloneDXParser()

    @pytest.fixture
    def minimal_sbom(self):
        """Minimal valid CycloneDX SBOM."""
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "timestamp": "2025-01-15T10:30:00Z",
                "tools": {
                    "components": [
                        {
                            "name": "syft",
                            "version": "v1.31.0"
                        }
                    ]
                },
                "component": {
                    "type": "application",
                    "name": "test-app",
                    "version": "1.0.0",
                    "purl": "pkg:pypi/test-app@1.0.0"
                }
            },
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0"
                }
            ]
        }

    def test_validate_valid_sbom(self, parser, minimal_sbom):
        """Test validation of valid CycloneDX SBOM."""
        assert parser.validate(minimal_sbom) is True
        assert len(parser.errors) == 0

    def test_validate_missing_bom_format(self, parser, minimal_sbom):
        """Test validation fails when bomFormat is missing."""
        del minimal_sbom["bomFormat"]
        assert parser.validate(minimal_sbom) is False
        assert "Missing bomFormat" in parser.errors

    def test_validate_invalid_bom_format(self, parser, minimal_sbom):
        """Test validation fails when bomFormat is not 'CycloneDX'."""
        minimal_sbom["bomFormat"] = "SPDX"
        assert parser.validate(minimal_sbom) is False
        assert any("Invalid bomFormat" in err for err in parser.errors)

    def test_validate_missing_spec_version(self, parser, minimal_sbom):
        """Test validation fails when specVersion is missing."""
        del minimal_sbom["specVersion"]
        assert parser.validate(minimal_sbom) is False
        assert "Missing specVersion" in parser.errors

    def test_extract_root_component(self, parser, minimal_sbom):
        """Test extraction of root component from metadata.component."""
        result = parser.parse(minimal_sbom)

        # Should extract both root component (1) + dependency components (1) = 2 total
        assert len(result.components) == 2

        # First component should be root component
        root_component = result.components[0]
        assert root_component["name"] == "test-app"
        assert root_component["version"] == "1.0.0"
        assert root_component["type"] == "application"
        assert root_component["purl"] == "pkg:pypi/test-app@1.0.0"

    def test_extract_dependency_components(self, parser, minimal_sbom):
        """Test extraction of dependency components from components[]."""
        result = parser.parse(minimal_sbom)

        # Second component should be dependency
        dependency = result.components[1]
        assert dependency["name"] == "requests"
        assert dependency["version"] == "2.31.0"
        assert dependency["type"] == "library"
        assert dependency["purl"] == "pkg:pypi/requests@2.31.0"

    def test_extract_tool_info_new_format(self, parser, minimal_sbom):
        """Test extraction of tool info from new format (tools: {components: []})."""
        result = parser.parse(minimal_sbom)

        assert result.tool_name == "syft"
        assert result.tool_version == "v1.31.0"

    def test_extract_tool_info_old_format(self, parser, minimal_sbom):
        """Test extraction of tool info from old format (tools: [])."""
        # Change to old format
        minimal_sbom["metadata"]["tools"] = [
            {
                "name": "trivy",
                "version": "0.48.0"
            }
        ]

        result = parser.parse(minimal_sbom)

        assert result.tool_name == "trivy"
        assert result.tool_version == "0.48.0"

    def test_parse_cve_vulnerability_with_enriched_severity(self, parser, minimal_sbom):
        """Test parsing CVE vulnerability with enriched severity format (direct severity field)."""
        # Add vulnerability with enriched severity format
        minimal_sbom["components"][0]["vulnerabilities"] = [
            {
                "id": "CVE-2024-1234",
                "severity": "critical",  # Direct severity field (enriched format)
                "description": "Critical vulnerability in requests"
            }
        ]

        result = parser.parse(minimal_sbom)

        assert len(result.findings) == 1
        finding = result.findings[0]
        assert finding.cve_id == "CVE-2024-1234"
        assert finding.severity == "CRITICAL"  # Normalized to uppercase
        assert finding.description == "Critical vulnerability in requests"
        assert finding.location == "pkg:pypi/requests@2.31.0"
        assert finding.tool_name == "syft"

    def test_parse_cve_vulnerability_with_standard_severity(self, parser, minimal_sbom):
        """Test parsing CVE vulnerability with standard severity format (ratings array)."""
        # Add vulnerability with standard severity format
        minimal_sbom["components"][0]["vulnerabilities"] = [
            {
                "id": "CVE-2024-5678",
                "ratings": [
                    {
                        "severity": "high",
                        "method": "CVSSv3"
                    }
                ],
                "description": "High severity vulnerability"
            }
        ]

        result = parser.parse(minimal_sbom)

        assert len(result.findings) == 1
        finding = result.findings[0]
        assert finding.cve_id == "CVE-2024-5678"
        assert finding.severity == "HIGH"  # Normalized to uppercase
        assert finding.description == "High severity vulnerability"

    def test_parse_ghsa_vulnerability(self, parser, minimal_sbom):
        """Test parsing GHSA vulnerability identifier."""
        # Add GHSA vulnerability
        minimal_sbom["components"][0]["vulnerabilities"] = [
            {
                "id": "GHSA-v8gr-m533-ghj9",
                "severity": "medium",
                "description": "GitHub Security Advisory"
            }
        ]

        result = parser.parse(minimal_sbom)

        assert len(result.findings) == 1
        finding = result.findings[0]
        assert finding.cve_id == "GHSA-v8gr-m533-ghj9"
        assert finding.severity == "MEDIUM"
        assert finding.description == "GitHub Security Advisory"

    def test_parse_root_level_vulnerabilities(self, parser, minimal_sbom):
        """Test parsing vulnerabilities from root-level vulnerabilities array (CycloneDX 1.5)."""
        # Add root-level vulnerability
        minimal_sbom["vulnerabilities"] = [
            {
                "id": "CVE-2024-9999",
                "severity": "low",
                "description": "Low severity issue",
                "affects": [
                    {
                        "ref": "pkg:pypi/requests@2.31.0"
                    }
                ]
            }
        ]

        result = parser.parse(minimal_sbom)

        assert len(result.findings) == 1
        finding = result.findings[0]
        assert finding.cve_id == "CVE-2024-9999"
        assert finding.severity == "LOW"
        assert finding.location == "pkg:pypi/requests@2.31.0"

    def test_parse_multiple_vulnerabilities_mixed_formats(self, parser, minimal_sbom):
        """Test parsing multiple vulnerabilities with mixed CVE/GHSA identifiers."""
        # Component-level CVE
        minimal_sbom["components"][0]["vulnerabilities"] = [
            {
                "id": "CVE-2024-1111",
                "severity": "critical",
                "description": "CVE in component"
            }
        ]

        # Root-level GHSA
        minimal_sbom["vulnerabilities"] = [
            {
                "id": "GHSA-xxxx-yyyy-zzzz",
                "ratings": [{"severity": "high"}],
                "description": "GHSA at root level",
                "affects": [{"ref": "pkg:pypi/test-app@1.0.0"}]
            }
        ]

        result = parser.parse(minimal_sbom)

        assert len(result.findings) == 2

        # Verify CVE finding
        cve_finding = next(f for f in result.findings if f.cve_id.startswith("CVE-"))
        assert cve_finding.cve_id == "CVE-2024-1111"
        assert cve_finding.severity == "CRITICAL"

        # Verify GHSA finding
        ghsa_finding = next(f for f in result.findings if f.cve_id.startswith("GHSA-"))
        assert ghsa_finding.cve_id == "GHSA-xxxx-yyyy-zzzz"
        assert ghsa_finding.severity == "HIGH"

    def test_severity_mapping(self, parser):
        """Test severity mapping from CycloneDX to normalized format."""
        test_cases = [
            ("critical", "CRITICAL"),
            ("high", "HIGH"),
            ("medium", "MEDIUM"),
            ("low", "LOW"),
            ("info", "INFO"),
            ("none", "NONE"),
            ("unknown", "UNKNOWN"),
            ("CRITICAL", "CRITICAL"),  # Already uppercase
            ("invalid", "UNKNOWN"),  # Invalid maps to UNKNOWN
        ]

        for cyclonedx_severity, expected_normalized in test_cases:
            normalized = parser._map_severity(cyclonedx_severity)
            assert normalized == expected_normalized, \
                f"Severity '{cyclonedx_severity}' should map to '{expected_normalized}', got '{normalized}'"

    def test_parse_component_without_purl(self, parser, minimal_sbom):
        """Test parsing component without PURL (should use name@version as location)."""
        # Remove PURL from component
        del minimal_sbom["components"][0]["purl"]

        # Add vulnerability to component without PURL
        minimal_sbom["components"][0]["vulnerabilities"] = [
            {
                "id": "CVE-2024-0000",
                "severity": "medium",
                "description": "Vulnerability in component without PURL"
            }
        ]

        result = parser.parse(minimal_sbom)

        finding = result.findings[0]
        # Should fall back to name@version format
        assert finding.location == "requests@2.31.0"

    def test_parse_sbom_without_root_component(self, parser, minimal_sbom):
        """Test parsing SBOM without metadata.component (only dependencies)."""
        # Remove root component
        del minimal_sbom["metadata"]["component"]

        result = parser.parse(minimal_sbom)

        # Should only extract dependency components
        assert len(result.components) == 1
        assert result.components[0]["name"] == "requests"

    def test_parse_empty_sbom(self, parser, minimal_sbom):
        """Test parsing SBOM with no components or vulnerabilities."""
        # Remove components
        minimal_sbom["components"] = []
        del minimal_sbom["metadata"]["component"]

        result = parser.parse(minimal_sbom)

        assert len(result.components) == 0
        assert len(result.findings) == 0

    def test_extract_metadata(self, parser, minimal_sbom):
        """Test extraction of SBOM metadata."""
        result = parser.parse(minimal_sbom)

        assert result.metadata["bom_format"] == "CycloneDX"
        assert result.metadata["spec_version"] == "1.5"
        assert "metadata" in result.metadata
        assert result.metadata["metadata"]["timestamp"] == "2025-01-15T10:30:00Z"
