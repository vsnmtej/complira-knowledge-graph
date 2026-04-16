"""
SARIF format parser.

SARIF (Static Analysis Results Interchange Format) is used by:
- GitHub Code Scanning
- Semgrep
- Snyk
- Checkmarx
- CodeQL
- Many other SAST/DAST tools

Spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
"""

from typing import Dict, Any, List
from api.parsers.base import BaseScanParser, ParsedScanData, ParsedFinding


class SARIFParser(BaseScanParser):
    """
    SARIF 2.1.0 format parser.

    Extracts vulnerabilities from SARIF results and converts to
    normalized ParsedFinding format.
    """

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """
        Parse SARIF 2.1.0 payload.

        Args:
            payload: SARIF JSON payload (dict)

        Returns:
            ParsedScanData: Normalized scan data

        Raises:
            ValueError: If payload is invalid or parsing fails
        """
        if not self.validate(payload):
            raise ValueError(f"SARIF validation failed: {', '.join(self.errors)}")

        try:
            runs = payload.get("runs", [])
            if not runs:
                raise ValueError("SARIF payload has no runs")

            run = runs[0]  # Most tools produce single run
            tool_driver = run.get("tool", {}).get("driver", {})
            tool_name = tool_driver.get("name", "Unknown")
            tool_version = tool_driver.get("version", "Unknown")

            findings = self._extract_findings(payload)
            metadata = self._extract_metadata(payload)

            return ParsedScanData(
                tool_name=tool_name,
                tool_version=tool_version,
                scan_timestamp=metadata.get("timestamp", ""),
                findings=findings,
                components=[],  # SARIF doesn't have SBOM data
                metadata=metadata
            )

        except Exception as e:
            self._handle_parse_error(e, "SARIF parsing")
            raise

    def _extract_findings(self, payload: Dict[str, Any]) -> List[ParsedFinding]:
        """
        Extract findings from SARIF results.

        Args:
            payload: SARIF payload

        Returns:
            list: ParsedFinding objects
        """
        findings = []

        for run in payload.get("runs", []):
            tool_name = run.get("tool", {}).get("driver", {}).get("name", "Unknown")

            for result in run.get("results", []):
                # SARIF uses ruleId (e.g., CVE-2021-44228 or custom rule IDs)
                rule_id = result.get("ruleId", "")

                # Extract CVE ID if present
                cve_id = ""
                if rule_id.upper().startswith("CVE-"):
                    cve_id = rule_id.upper()
                else:
                    # Check message for CVE reference
                    message_text = result.get("message", {}).get("text", "")
                    if "CVE-" in message_text.upper():
                        # Extract first CVE ID from message
                        import re
                        match = re.search(r'CVE-\d{4}-\d{4,}', message_text.upper())
                        if match:
                            cve_id = match.group(0)

                # Map SARIF level to severity
                level = result.get("level", "warning")
                severity = self._map_level_to_severity(level)

                # Extract description
                message = result.get("message", {})
                description = message.get("text", "") or message.get("markdown", "")

                # Extract location
                location = self._extract_location(result)

                finding = ParsedFinding(
                    cve_id=cve_id,
                    severity=severity,
                    description=description,
                    location=location,
                    tool_name=tool_name,
                    scan_type="sarif",
                    raw_data=result
                )

                findings.append(finding)

        self.logger.debug(
            "Extracted SARIF findings",
            findings_count=len(findings),
        )

        return findings

    def _extract_location(self, result: Dict[str, Any]) -> str:
        """
        Extract file location from SARIF result.

        Args:
            result: SARIF result object

        Returns:
            str: Location string (file:line or file)
        """
        locations = result.get("locations", [])
        if not locations:
            return ""

        physical = locations[0].get("physicalLocation", {})
        artifact = physical.get("artifactLocation", {})
        uri = artifact.get("uri", "")

        region = physical.get("region", {})
        line = region.get("startLine", 0)

        if line:
            return f"{uri}:{line}"
        return uri

    def _extract_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract SARIF metadata.

        Args:
            payload: SARIF payload

        Returns:
            dict: Metadata (tool info, timestamps, etc.)
        """
        runs = payload.get("runs", [])
        if not runs:
            return {}

        run = runs[0]
        invocations = run.get("invocations", [{}])
        invocation = invocations[0] if invocations else {}

        return {
            "timestamp": invocation.get("startTimeUtc", ""),
            "tool_driver": run.get("tool", {}).get("driver", {}),
            "sarif_version": payload.get("version", "2.1.0"),
            "execution_successful": invocation.get("executionSuccessful", True),
        }

    def _map_level_to_severity(self, level: str) -> str:
        """
        Map SARIF level to normalized severity.

        SARIF levels: error, warning, note, none

        Args:
            level: SARIF level

        Returns:
            str: Normalized severity (CRITICAL, HIGH, MEDIUM, LOW, INFO, NONE)
        """
        mapping = {
            "error": "HIGH",
            "warning": "MEDIUM",
            "note": "LOW",
            "none": "INFO",
        }
        return mapping.get(level.lower(), "UNKNOWN")

    def validate(self, payload: Dict[str, Any]) -> bool:
        """
        Validate SARIF payload.

        Args:
            payload: SARIF payload

        Returns:
            bool: True if valid SARIF 2.1.0 format
        """
        # Call base validation first
        if not super().validate(payload):
            return False

        # SARIF-specific validation
        if "version" not in payload:
            self.errors.append("Missing SARIF version")
            return False

        version = payload.get("version")
        if not version.startswith("2.1"):
            self.errors.append(f"Unsupported SARIF version: {version} (expected 2.1.x)")
            self.logger.warning(
                "SARIF version mismatch",
                version=version,
                expected="2.1.x",
            )
            # Continue anyway - some tools use slightly different versions

        if "runs" not in payload or not payload["runs"]:
            self.errors.append("SARIF payload has no runs")
            return False

        return True
