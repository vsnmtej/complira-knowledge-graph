"""
Grype native JSON parser.

Grype (anchore/grype) is an open-source vulnerability scanner for container images
and filesystems. It can output results in multiple formats; this parser handles the
Grype native JSON format (--output json).

Grype native JSON format:
    {
        "matches": [...],         # List of vulnerability matches
        "ignoredMatches": [...],  # Ignored matches
        "source": {...},          # Scanned source
        "distro": {...},          # OS distro info
        "descriptor": {           # Grype tool metadata
            "name": "grype",
            "version": "0.74.0"
        }
    }

Each match:
    {
        "vulnerability": {
            "id": "CVE-2023-44487",
            "severity": "High",
            "fix": {
                "state": "fixed",      # "fixed", "wont-fix", "not-fixed", "unknown"
                "versions": ["1.2.3"]
            },
            ...
        },
        "matchDetails": [...],
        "artifact": {
            "name": "nghttp2",
            "version": "1.43.0",
            "purl": "pkg:apk/alpine/nghttp2@1.43.0-r3",
            ...
        }
    }

Key feature: `fix.state` is extracted and surfaced as `scanner_vex_status` in every
vulnerability dict, enabling downstream VEX generation to short-circuit LLM calls
when the scanner has already provided a deterministic status.
"""

from typing import Dict, Any, List, Optional
from api.parsers.base import BaseScanParser, ParsedScanData, ParsedFinding


# Grype fix.state → VEX-compatible status mapping
_GRYPE_FIX_STATE_TO_VEX = {
    "fixed": "fixed",
    "wont-fix": "affected",      # Affected, but fix will not be applied
    "not-fixed": "affected",     # Affected, no fix available yet
    "unknown": None,             # Indeterminate — fall through to heuristics
}

# Severity normalization
_SEVERITY_MAP = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "info": "INFO",
    "informational": "INFO",
    "negligible": "NONE",
    "none": "NONE",
    "unknown": "UNKNOWN",
}


class GryperAnalyzer(BaseScanParser):
    """
    Grype native JSON parser with VEX status pre-annotation.

    Parses Grype's native JSON output format and extracts vulnerability matches
    as normalized ParsedFinding objects. Each finding carries `scanner_vex_status`
    in its `raw_data` field, derived from Grype's `fix.state`.

    VEX Status Mapping:
        fix.state="fixed"      → scanner_vex_status="fixed"
        fix.state="wont-fix"   → scanner_vex_status="affected"
        fix.state="not-fixed"  → scanner_vex_status="affected"
        fix.state="unknown"    → scanner_vex_status=None (use heuristics downstream)

    Example:
        >>> analyzer = GryperAnalyzer()
        >>> scan_data = analyzer.parse(grype_json_payload)
        >>> for finding in scan_data.findings:
        ...     vex_hint = finding.raw_data.get("scanner_vex_status")
        ...     # "fixed", "affected", or None
    """

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """
        Parse Grype native JSON payload.

        Args:
            payload: Grype JSON payload (dict with 'matches' array)

        Returns:
            ParsedScanData: Normalized scan data with scanner_vex_status in raw_data

        Raises:
            ValueError: If payload is invalid or parsing fails
        """
        if not self.validate(payload):
            raise ValueError(f"Grype payload validation failed: {', '.join(self.errors)}")

        try:
            descriptor = payload.get("descriptor", {})
            tool_name = descriptor.get("name", "grype")
            tool_version = descriptor.get("version", "unknown")

            findings = self._extract_findings(payload)
            components = self._extract_components(payload)

            return ParsedScanData(
                tool_name=tool_name,
                tool_version=tool_version,
                scan_timestamp=payload.get("descriptor", {}).get("timestamp", ""),
                findings=findings,
                components=components,
                metadata=self._extract_metadata(payload),
            )

        except Exception as e:
            self._handle_parse_error(e, "Grype parsing")
            raise

    def _extract_findings(self, payload: Dict[str, Any]) -> List[ParsedFinding]:
        """
        Extract vulnerability matches from Grype JSON.

        Each match is processed by `_process_grype_match`, which extracts `fix.state`
        as `scanner_vex_status` and includes it in the normalized vulnerability dict.

        Args:
            payload: Grype JSON payload

        Returns:
            list: ParsedFinding objects, each with scanner_vex_status in raw_data
        """
        findings = []
        tool_name = payload.get("descriptor", {}).get("name", "grype")

        for match in payload.get("matches", []):
            try:
                vuln_dict = self._process_grype_match(match)
                if not vuln_dict:
                    continue

                cve_id = vuln_dict.get("cve_id", "")
                if not cve_id:
                    self.logger.debug("Skipping match without CVE ID", match_id=match.get("vulnerability", {}).get("id"))
                    continue

                finding = ParsedFinding(
                    cve_id=cve_id,
                    severity=vuln_dict.get("severity", "UNKNOWN"),
                    description=vuln_dict.get("description", ""),
                    location=vuln_dict.get("location", "unknown"),
                    tool_name=tool_name,
                    scan_type="grype",
                    raw_data=vuln_dict,  # includes scanner_vex_status
                )
                findings.append(finding)

            except Exception as e:
                self.logger.warning(
                    "Skipping Grype match due to error",
                    error=str(e),
                    vulnerability_id=match.get("vulnerability", {}).get("id"),
                )
                continue

        self.logger.debug(
            "Extracted Grype findings",
            findings_count=len(findings),
            total_matches=len(payload.get("matches", [])),
        )

        return findings

    def _process_grype_match(self, match: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a single Grype match and extract normalized vulnerability dict.

        Grype's `fix.state` is extracted and surfaced as `scanner_vex_status`
        in the returned dict. Downstream VEX generation uses this to short-circuit
        the LLM when the scanner has already produced a deterministic assessment.

        Fix state precedence:
            1. `vulnerability.fix.state` (standard Grype location)
            2. Top-level `fix.state` (some Grype versions)
            3. None if absent (fall through to heuristics)

        Args:
            match: Single Grype match dict

        Returns:
            dict: Normalized vulnerability dict with scanner_vex_status, or None to skip
        """
        vuln = match.get("vulnerability", {})
        artifact = match.get("artifact", {})

        # --- CVE ID ---
        cve_id = vuln.get("id", "")
        if not cve_id or not cve_id.startswith("CVE-"):
            return None

        # --- Severity ---
        raw_severity = vuln.get("severity", "unknown")
        severity = _SEVERITY_MAP.get(raw_severity.lower(), "UNKNOWN")

        # --- Description ---
        description = vuln.get("description", "")

        # --- Location (PURL preferred, fallback to name@version) ---
        purl = artifact.get("purl", "")
        if purl:
            location = purl
        else:
            name = artifact.get("name", "unknown")
            version = artifact.get("version", "unknown")
            location = f"{name}@{version}"

        # --- fix.state → scanner_vex_status ---
        # Check vulnerability.fix.state first (standard location)
        fix_data = vuln.get("fix") or match.get("fix") or {}
        fix_state = fix_data.get("state")  # "fixed", "wont-fix", "not-fixed", "unknown"
        fix_versions = fix_data.get("versions", [])

        scanner_vex_status = _GRYPE_FIX_STATE_TO_VEX.get(fix_state) if fix_state else None

        # --- CVSS ---
        cvss_list = vuln.get("cvss", [])
        cvss_v3_score = None
        cvss_v3_vector = None
        for cvss in cvss_list:
            if cvss.get("version", "").startswith("3"):
                metrics = cvss.get("metrics", {})
                cvss_v3_score = metrics.get("baseScore")
                cvss_v3_vector = cvss.get("vector")
                break

        # --- Namespace ---
        namespace = vuln.get("namespace", "")

        return {
            "cve_id": cve_id,
            "severity": severity,
            "description": description,
            "location": location,
            "fix_state": fix_state,
            "fix_versions": fix_versions,
            "scanner_vex_status": scanner_vex_status,  # Key field for VEX short-circuit
            "cvss_v3_score": cvss_v3_score,
            "cvss_v3_vector": cvss_v3_vector,
            "namespace": namespace,
            "artifact_name": artifact.get("name", ""),
            "artifact_version": artifact.get("version", ""),
            "artifact_type": artifact.get("type", ""),
            "artifact_purl": purl,
            "match_details": match.get("matchDetails", []),
        }

    def _extract_components(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract unique artifacts from Grype matches as SBOM components.

        Args:
            payload: Grype JSON payload

        Returns:
            list: Unique artifact dicts (deduplicated by purl)
        """
        seen_purls: set = set()
        components = []

        for match in payload.get("matches", []):
            artifact = match.get("artifact", {})
            purl = artifact.get("purl", "")

            if purl and purl in seen_purls:
                continue

            component = {
                "name": artifact.get("name", ""),
                "version": artifact.get("version", ""),
                "purl": purl,
                "type": artifact.get("type", ""),
                "cpes": artifact.get("cpes", []),
                "licenses": [
                    lic.get("value", "") if isinstance(lic, dict) else str(lic)
                    for lic in artifact.get("licenses", [])
                ],
            }
            components.append(component)

            if purl:
                seen_purls.add(purl)

        return components

    def _extract_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract Grype-specific metadata.

        Args:
            payload: Grype JSON payload

        Returns:
            dict: Metadata (tool info, source, distro, etc.)
        """
        descriptor = payload.get("descriptor", {})
        source = payload.get("source", {})
        distro = payload.get("distro", {})

        return {
            "format": "grype_native_json",
            "grype_version": descriptor.get("version", "unknown"),
            "grype_db_checksum": descriptor.get("db", {}).get("checksum"),
            "source_type": source.get("type"),
            "source_target": source.get("target"),
            "distro_name": distro.get("name"),
            "distro_version": distro.get("version"),
            "ignored_matches_count": len(payload.get("ignoredMatches", [])),
        }

    def validate(self, payload: Dict[str, Any]) -> bool:
        """
        Validate Grype native JSON payload.

        Args:
            payload: Grype JSON payload

        Returns:
            bool: True if valid Grype native format
        """
        if not super().validate(payload):
            return False

        # Grype native JSON must have 'matches' array
        if "matches" not in payload:
            self.errors.append("Missing 'matches' array (not a Grype native JSON payload)")
            return False

        if not isinstance(payload["matches"], list):
            self.errors.append("'matches' must be a list")
            return False

        # Grype descriptor should identify the tool
        descriptor = payload.get("descriptor", {})
        tool_name = descriptor.get("name", "")
        if tool_name and tool_name.lower() != "grype":
            self.logger.warning(
                "Unexpected tool name in Grype payload",
                tool_name=tool_name,
                expected="grype",
            )
            # Don't fail — descriptor may be absent in some Grype versions

        return True
