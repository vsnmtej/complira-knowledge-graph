"""
CycloneDX SBOM parser.

CycloneDX is used by:
- OWASP Dependency-Check
- Syft
- Grype
- Trivy
- Snyk
- GitHub Dependency Graph
- Many other SCA tools

Spec: https://cyclonedx.org/docs/
"""

from typing import Dict, Any, List
from api.parsers.base import BaseScanParser, ParsedScanData, ParsedFinding


class CycloneDXParser(BaseScanParser):
    """
    CycloneDX 1.4/1.5 SBOM parser.

    Extracts vulnerabilities from CycloneDX components and converts to
    normalized ParsedFinding format.
    """

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """
        Parse CycloneDX 1.4/1.5 payload.

        Args:
            payload: CycloneDX JSON payload (dict)

        Returns:
            ParsedScanData: Normalized scan data

        Raises:
            ValueError: If payload is invalid or parsing fails
        """
        if not self.validate(payload):
            raise ValueError(f"CycloneDX validation failed: {', '.join(self.errors)}")

        try:
            metadata = payload.get("metadata", {})
            tools = metadata.get("tools", [])

            # Handle both old format (tools: []) and new format (tools: {components: []})
            if isinstance(tools, list):
                tool_data = tools[0] if tools else {}
            elif isinstance(tools, dict):
                tool_components = tools.get("components", [])
                tool_data = tool_components[0] if tool_components else {}
            else:
                tool_data = {}

            tool_name = tool_data.get("name", "Unknown")
            tool_version = tool_data.get("version", "Unknown")

            findings = self._extract_findings(payload)
            components = self._extract_components(payload)

            return ParsedScanData(
                tool_name=tool_name,
                tool_version=tool_version,
                scan_timestamp=metadata.get("timestamp", ""),
                findings=findings,
                components=components,
                metadata=self._extract_metadata(payload)
            )

        except Exception as e:
            self._handle_parse_error(e, "CycloneDX parsing")
            raise

    def _extract_findings(self, payload: Dict[str, Any]) -> List[ParsedFinding]:
        """
        Extract vulnerabilities from CycloneDX components.

        CycloneDX 1.4+ supports vulnerabilities array in each component.
        CycloneDX 1.5+ also supports root-level vulnerabilities array.

        Args:
            payload: CycloneDX payload

        Returns:
            list: ParsedFinding objects
        """
        findings = []

        metadata = payload.get("metadata", {})
        tools = metadata.get("tools", [])
        if isinstance(tools, list):
            tool_name = tools[0].get("name", "Unknown") if tools else "Unknown"
        elif isinstance(tools, dict):
            tool_components = tools.get("components", [])
            tool_name = tool_components[0].get("name", "Unknown") if tool_components else "Unknown"
        else:
            tool_name = "Unknown"

        # Extract component-level vulnerabilities (CycloneDX 1.4 style)
        for component in payload.get("components", []):
            component_name = component.get("name", "")
            component_version = component.get("version", "")
            component_purl = component.get("purl", "")

            for vuln in component.get("vulnerabilities", []):
                # Extract CVE ID (try both 'id' and 'cve_id' fields)
                cve_id = vuln.get("cve_id") or vuln.get("id", "")

                # Extract severity (support both standard and enriched formats)
                severity = "UNKNOWN"

                # Try direct severity field first (enriched format)
                if "severity" in vuln and vuln["severity"]:
                    severity = self._map_severity(vuln["severity"])
                # Fall back to ratings array (standard CycloneDX format)
                elif "ratings" in vuln and vuln["ratings"]:
                    rating = vuln["ratings"][0]
                    severity = self._map_severity(rating.get("severity", ""))

                # Extract description
                description = vuln.get("description", "")

                # Build location string
                if component_purl:
                    location = component_purl
                else:
                    location = f"{component_name}@{component_version}"

                finding = ParsedFinding(
                    cve_id=cve_id,
                    severity=severity,
                    description=description,
                    location=location,
                    tool_name=tool_name,
                    scan_type="cyclonedx",
                    raw_data=vuln
                )

                findings.append(finding)

        # Extract root-level vulnerabilities (CycloneDX 1.5 style)
        for vuln in payload.get("vulnerabilities", []):
            # Extract CVE ID (try both 'id' and 'cve_id' fields)
            cve_id = vuln.get("cve_id") or vuln.get("id", "")

            # Extract severity (support both standard and enriched formats)
            severity = "UNKNOWN"

            # Try direct severity field first (enriched format)
            if "severity" in vuln and vuln["severity"]:
                severity = self._map_severity(vuln["severity"])
            # Fall back to ratings array (standard CycloneDX format)
            elif "ratings" in vuln and vuln["ratings"]:
                rating = vuln["ratings"][0]
                severity = self._map_severity(rating.get("severity", ""))

            # Extract description
            description = vuln.get("description", "")

            # Determine location from affects array
            affects = vuln.get("affects", [])
            location = "Unknown"
            if affects:
                # Use first affected reference (ref is usually purl)
                location = affects[0].get("ref", "Unknown")

            finding = ParsedFinding(
                cve_id=cve_id,
                severity=severity,
                description=description,
                location=location,
                tool_name=tool_name,
                scan_type="cyclonedx",
                raw_data=vuln
            )

            findings.append(finding)

        self.logger.debug(
            "Extracted CycloneDX findings",
            findings_count=len(findings),
        )

        return findings

    def _extract_components(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract SBOM components.

        Includes both:
        - metadata.component (root/main component - the application itself)
        - components[] (dependency components)

        Args:
            payload: CycloneDX payload

        Returns:
            list: Component dictionaries
        """
        all_components = []

        # Extract root component from metadata (represents the application/project)
        metadata = payload.get("metadata", {})
        root_component = metadata.get("component")
        if root_component:
            all_components.append(root_component)
            self.logger.debug(
                "Found root component in metadata",
                component_name=root_component.get("name", "Unknown"),
                component_purl=root_component.get("purl", "NO_PURL"),
            )

        # Extract dependency components
        dependency_components = payload.get("components", [])
        all_components.extend(dependency_components)

        self.logger.debug(
            "Extracted CycloneDX components",
            root_component_count=1 if root_component else 0,
            dependency_count=len(dependency_components),
            total_count=len(all_components),
        )

        return all_components

    def _extract_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract CycloneDX metadata.

        Args:
            payload: CycloneDX payload

        Returns:
            dict: Metadata (BOM format, spec version, serial number, etc.)
        """
        return {
            "bom_format": payload.get("bomFormat", "CycloneDX"),
            "spec_version": payload.get("specVersion", "1.4"),
            "serial_number": payload.get("serialNumber", ""),
            "metadata": payload.get("metadata", {})
        }

    def _map_severity(self, cyclonedx_severity: str) -> str:
        """
        Map CycloneDX severity to normalized severity.

        CycloneDX severities: critical, high, medium, low, info, none, unknown

        Args:
            cyclonedx_severity: CycloneDX severity string

        Returns:
            str: Normalized severity (CRITICAL, HIGH, MEDIUM, LOW, INFO, NONE, UNKNOWN)
        """
        mapping = {
            "critical": "CRITICAL",
            "high": "HIGH",
            "medium": "MEDIUM",
            "low": "LOW",
            "info": "INFO",
            "none": "NONE",
            "unknown": "UNKNOWN",
        }
        return mapping.get(cyclonedx_severity.lower(), "UNKNOWN")

    def validate(self, payload: Dict[str, Any]) -> bool:
        """
        Validate CycloneDX payload.

        Args:
            payload: CycloneDX payload

        Returns:
            bool: True if valid CycloneDX format
        """
        # Call base validation first
        if not super().validate(payload):
            return False

        # CycloneDX-specific validation
        if "bomFormat" not in payload:
            self.errors.append("Missing bomFormat")
            return False

        bom_format = payload.get("bomFormat")
        if bom_format != "CycloneDX":
            self.errors.append(f"Invalid bomFormat: {bom_format} (expected CycloneDX)")
            return False

        if "specVersion" not in payload:
            self.errors.append("Missing specVersion")
            return False

        spec_version = payload.get("specVersion")
        if not spec_version.startswith("1."):
            self.errors.append(f"Unsupported CycloneDX version: {spec_version} (expected 1.x)")
            self.logger.warning(
                "CycloneDX version mismatch",
                version=spec_version,
                expected="1.4 or 1.5",
            )
            # Continue anyway

        if "components" not in payload:
            self.errors.append("CycloneDX payload has no components")
            self.logger.warning("CycloneDX SBOM has no components")
            # Don't fail - empty SBOM is technically valid

        return True
