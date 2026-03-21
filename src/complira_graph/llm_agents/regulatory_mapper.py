"""
Regulatory Mapper LLM Agent.

Uses Claude Opus 4 to map vulnerabilities to regulatory compliance requirements.
Analyzes CVE impacts in context of NIST 800-53, ISO 27001, PCI-DSS, HIPAA, etc.

Model: Claude Opus 4 (highest reasoning for complex compliance analysis)
Output: maps_to_requirement edges linking vulnerabilities to controls
"""

from typing import List, Dict, Any
import json
from datetime import datetime
import structlog

from ..agents.base import BaseLLMAgent
from ..utils.keys import normalize_cve_id

logger = structlog.get_logger()


class RegulatoryMapperAgent(BaseLLMAgent):
    """
    LLM agent for mapping vulnerabilities to regulatory compliance requirements.

    Uses Claude Opus 4 for complex reasoning about compliance impacts.
    """

    # LLM configuration
    MODEL = "claude-opus-4"
    MAX_TOKENS = 16384  # Large enough for comprehensive regulatory mappings without truncation
    CONFIDENCE_THRESHOLD = 0.85
    BATCH_SIZE = 20  # Small batch - expensive model

    def find_gaps(self) -> List[Dict[str, Any]]:
        """
        Find high-severity vulnerabilities without regulatory mappings.

        Returns:
            list[dict]: Vulnerabilities needing compliance mapping

        Query Logic:
            - Find CVEs with CVSS >= 7.0 without maps_to_requirement edges
            - Prioritize KEV vulnerabilities
            - Limit to BATCH_SIZE
        """
        self.logger.info("Finding vulnerabilities needing regulatory mapping")

        query = """
        FOR cve IN vulnerabilities
            FILTER cve.cvss_v3_score >= 7.0 OR cve.cvss_v2_score >= 7.0
            // Check if regulatory mapping exists
            LET has_mapping = LENGTH(
                FOR v, e IN 1..1 OUTBOUND cve maps_to_requirement
                    RETURN 1
            ) > 0
            FILTER !has_mapping
            // Prioritize KEV vulnerabilities
            LET is_kev = LENGTH(
                FOR v, e IN 1..1 OUTBOUND cve exploited_in_wild
                    RETURN 1
            ) > 0
            // Get CWE context (deduplicated)
            LET cwes = UNIQUE(
                FOR v, e IN 1..1 OUTBOUND cve has_weakness
                    RETURN {
                        cwe_id: v.cwe_id,
                        name: v.name
                    }
            )
            SORT is_kev DESC, cve.cvss_v3_score DESC
            LIMIT @batch_size
            RETURN {
                _key: cve._key,
                cve_id: cve.cve_id,
                description: cve.description,
                cvss_v3_score: cve.cvss_v3_score,
                cwes: cwes,
                is_kev: is_kev
            }
        """

        cursor = self.db.aql.execute(
            query,
            bind_vars={'batch_size': self.BATCH_SIZE}
        )

        gaps = list(cursor)

        self.logger.info(
            "Found vulnerabilities needing regulatory mapping",
            count=len(gaps),
        )

        return gaps

    def enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map vulnerability to regulatory requirements using Claude Opus 4.

        Args:
            record: Vulnerability record from find_gaps()

        Returns:
            dict: Enrichment data with regulatory mappings

        Raises:
            Exception: On API failure or parsing error
        """
        cve_id = record.get('cve_id', '')
        description = record.get('description', '')
        cwes = record.get('cwes', [])
        is_kev = record.get('is_kev', False)

        # Construct prompt
        prompt = self._build_mapping_prompt(cve_id, description, cwes, is_kev)

        self.logger.debug("Calling Claude API for regulatory mapping", cve_id=cve_id)

        # L4: Use Opus for complex cross-framework regulatory mapping ($25)
        try:
            response = self.anthropic_client.messages.create(
                model=self.settings.ANTHROPIC_MODEL_OPUS,
                max_tokens=self.MAX_TOKENS,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            response_text = response.content[0].text
            response_text = self._strip_markdown_fences(response_text)

            # Try to parse JSON with enhanced error handling
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as json_err:
                # Log detailed error for debugging
                self.logger.error(
                    "Failed to parse Opus JSON response",
                    cve_id=cve_id,
                    error=str(json_err),
                    response_length=len(response_text),
                    response_preview=response_text[:500] if response_text else "None",
                    response_suffix=response_text[-200:] if len(response_text) > 200 else response_text,
                )

                # Advanced salvage strategy
                result = None

                # Strategy 1: Try to find complete outermost braces
                try:
                    first_brace = response_text.index('{')
                    last_brace = response_text.rindex('}')
                    salvaged_json = response_text[first_brace:last_brace+1]
                    result = json.loads(salvaged_json)
                    self.logger.warning(
                        "Salvaged JSON using outermost braces",
                        cve_id=cve_id,
                    )
                except (ValueError, json.JSONDecodeError):
                    pass

                # Strategy 2: Try to fix unterminated strings by completing the JSON structure
                if result is None:
                    try:
                        # Find the last complete key-value pair before truncation
                        # Add closing quotes, brackets, and braces as needed
                        fixed_json = response_text

                        # If ends with incomplete string, close it
                        if fixed_json.rstrip().endswith('"'):
                            # Already has closing quote
                            pass
                        elif '"' in fixed_json[-100:]:  # Unterminated string in last 100 chars
                            fixed_json = fixed_json + '"'

                        # Ensure proper closing of control_mappings array
                        if ']' not in fixed_json[-50:]:
                            fixed_json = fixed_json + ']'

                        # Ensure proper closing of root object
                        if '}' not in fixed_json[-20:]:
                            fixed_json = fixed_json + '}'

                        result = json.loads(fixed_json)
                        self.logger.warning(
                            "Salvaged JSON by completing truncated structure",
                            cve_id=cve_id,
                        )
                    except json.JSONDecodeError:
                        pass

                # Strategy 3: Extract control_mappings array even if outer structure is broken
                if result is None:
                    try:
                        import re
                        # Look for control_mappings array
                        match = re.search(r'"control_mappings"\s*:\s*\[(.*)', response_text, re.DOTALL)
                        if match:
                            # Try to extract complete mappings
                            mappings_text = '[' + match.group(1)
                            # Find where array likely ends (before next top-level key or end)
                            next_key_match = re.search(r'\],\s*"[a-z_]+"\s*:', mappings_text)
                            if next_key_match:
                                mappings_text = mappings_text[:next_key_match.start()+1]
                            else:
                                # Try to close the array
                                if ']' not in mappings_text[-50:]:
                                    mappings_text = mappings_text + ']'

                            # Create minimal valid structure
                            result = {
                                'control_mappings': json.loads(mappings_text),
                                'compliance_impact': 'high',  # Default
                                'remediation_priority': 'high',  # Default
                            }
                            self.logger.warning(
                                "Salvaged control_mappings array from broken JSON",
                                cve_id=cve_id,
                                mappings_found=len(result['control_mappings']),
                            )
                    except Exception:
                        pass

                # If all salvage strategies failed, raise original error
                if result is None:
                    self.logger.error(
                        "All JSON salvage strategies failed, skipping enrichment",
                        cve_id=cve_id,
                    )
                    raise json_err

            enrichment = {
                'cve_key': record.get('_key'),
                'cve_id': cve_id,
                'control_mappings': result.get('control_mappings', []),
                'compliance_impact': result.get('compliance_impact'),
                'remediation_priority': result.get('remediation_priority'),
                'model': self.MODEL,
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'timestamp': datetime.utcnow().isoformat(),
            }

            self.logger.debug(
                "Regulatory mapping complete",
                cve_id=cve_id,
                mappings_count=len(enrichment['control_mappings']),
            )

            return enrichment

        except json.JSONDecodeError as e:
            self.logger.error(
                "Regulatory mapping failed - JSON parsing error",
                cve_id=cve_id,
                error=str(e),
            )
            raise

        except Exception as e:
            self.logger.error(
                "Regulatory mapping failed",
                cve_id=cve_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def validate(self, enrichment: Dict[str, Any]) -> bool:
        """
        Validate regulatory mapping quality.

        Filters out low-confidence mappings and validates structure.
        Enrichment passes if at least ONE high-confidence mapping remains.

        Args:
            enrichment: Enrichment data from enrich()

        Returns:
            bool: True if enrichment has at least one valid high-confidence mapping

        Side Effects:
            Modifies enrichment['control_mappings'] to remove low-confidence mappings
        """
        mappings = enrichment.get('control_mappings', [])

        if not mappings:
            self.logger.warning(
                "No control mappings generated",
                cve_id=enrichment.get('cve_id'),
            )
            return False

        # Filter mappings: keep only those with complete fields and sufficient confidence
        valid_mappings = []

        for mapping in mappings:
            # Check required fields
            if not mapping.get('framework'):
                self.logger.debug(
                    "Skipping mapping without framework",
                    cve_id=enrichment.get('cve_id'),
                )
                continue

            if not mapping.get('control_id'):
                self.logger.debug(
                    "Skipping mapping without control_id",
                    cve_id=enrichment.get('cve_id'),
                    framework=mapping.get('framework'),
                )
                continue

            confidence = mapping.get('confidence', 0.0)
            if confidence < self.CONFIDENCE_THRESHOLD:
                self.logger.debug(
                    "Skipping low-confidence mapping",
                    cve_id=enrichment.get('cve_id'),
                    framework=mapping.get('framework'),
                    control_id=mapping.get('control_id'),
                    confidence=confidence,
                    threshold=self.CONFIDENCE_THRESHOLD,
                )
                continue

            # Mapping is valid
            valid_mappings.append(mapping)

        # Update enrichment with only valid mappings
        enrichment['control_mappings'] = valid_mappings

        if not valid_mappings:
            self.logger.warning(
                "No high-confidence mappings after filtering",
                cve_id=enrichment.get('cve_id'),
                original_count=len(mappings),
            )
            return False

        self.logger.debug(
            "Validation passed",
            cve_id=enrichment.get('cve_id'),
            valid_mappings=len(valid_mappings),
            filtered_out=len(mappings) - len(valid_mappings),
        )

        return True

    def persist(self, enrichment: Dict[str, Any]) -> None:
        """
        Save regulatory mappings and provenance.

        Args:
            enrichment: Validated enrichment data

        Creates:
            - maps_to_requirement edges for each control mapping
            - llm_enrichments provenance record
        """
        cve_key = enrichment['cve_key']
        mappings = enrichment['control_mappings']

        for mapping in mappings:
            framework = mapping.get('framework')  # nist_800_53, iso_27001, pci_dss, etc.
            control_id = mapping.get('control_id')
            confidence = mapping.get('confidence')
            rationale = mapping.get('rationale')

            # Determine target collection based on framework
            target_collection_map = {
                'nist_800_53': 'oscal_controls',
                'iso_27001': 'regulatory_requirements',
                'pci_dss': 'regulatory_requirements',
                'hipaa': 'regulatory_requirements',
                'scf': 'scf_controls',
            }

            target_collection = target_collection_map.get(framework, 'regulatory_requirements')

            # Normalize control ID for _key
            control_key = control_id.lower().replace('.', '_').replace('(', '').replace(')', '')

            # Create edge
            edge = {
                '_from': f'vulnerabilities/{cve_key}',
                '_to': f'{target_collection}/{control_key}',
                'framework': framework,
                'confidence': confidence,
                'rationale': rationale,
                'source': 'llm',
                'model': enrichment['model'],
                'timestamp': enrichment['timestamp'],
            }

            try:
                self.db.collection('maps_to_requirement').insert(edge, overwrite_mode='ignore')

                self.logger.debug(
                    "Created maps_to_requirement edge",
                    cve_id=enrichment['cve_id'],
                    control_id=control_id,
                )

            except Exception as e:
                self.logger.error(
                    "Failed to create maps_to_requirement edge",
                    cve_id=enrichment['cve_id'],
                    control_id=control_id,
                    error=str(e),
                )

        # Store provenance
        provenance = {
            'entity_type': 'maps_to_requirement',
            'cve_id': enrichment['cve_id'],
            'control_mappings': mappings,
            'compliance_impact': enrichment['compliance_impact'],
            'remediation_priority': enrichment['remediation_priority'],
            'model': enrichment['model'],
            'input_tokens': enrichment['input_tokens'],
            'output_tokens': enrichment['output_tokens'],
            'timestamp': enrichment['timestamp'],
        }

        try:
            if not self.db.has_collection('llm_enrichments'):
                self.db.create_collection('llm_enrichments', edge=False)

            self.db.collection('llm_enrichments').insert(provenance)

            self.logger.info(
                "Stored regulatory mapping provenance",
                cve_id=enrichment['cve_id'],
                mappings_count=len(mappings),
            )

        except Exception as e:
            self.logger.error(
                "Failed to store provenance",
                cve_id=enrichment['cve_id'],
                error=str(e),
            )

    def _build_mapping_prompt(self, cve_id: str, description: str, cwes: List[Dict], is_kev: bool) -> str:
        """
        Build prompt for regulatory mapping.

        Args:
            cve_id: CVE identifier
            description: CVE description
            cwes: List of CWE weaknesses
            is_kev: Whether vulnerability is in CISA KEV

        Returns:
            str: Formatted prompt for Claude
        """
        cwe_text = "\n".join([f"- {cwe.get('cwe_id')}: {cwe.get('name')}" for cwe in cwes]) if cwes else "None identified"
        kev_status = "YES - Actively exploited in the wild (CISA KEV)" if is_kev else "No"

        prompt = f"""You are a cybersecurity compliance expert specializing in regulatory frameworks (NIST 800-53, ISO 27001, PCI-DSS, HIPAA, SOC 2).

Analyze the following vulnerability and map it to relevant security controls across frameworks.

CVE ID: {cve_id}
KEV Status: {kev_status}

Description:
{description}

Related Weaknesses (CWE):
{cwe_text}

Instructions:
1. Identify which security control families this vulnerability impacts (e.g., Access Control, System Integrity, Vulnerability Management)
2. Map to specific controls in NIST 800-53 Rev 5 (e.g., SI-2, RA-5, CM-3)
3. Map to ISO 27001:2022 controls if applicable (e.g., A.12.6.1, A.18.2.3)
4. Assess compliance impact (critical, high, medium, low)
5. Recommend remediation priority considering KEV status and severity

Common NIST 800-53 Controls for Vulnerabilities:
- SI-2: Flaw Remediation
- RA-5: Vulnerability Monitoring and Scanning
- CM-3: Configuration Change Control
- SI-7: Software, Firmware, and Information Integrity
- AC-6: Least Privilege
- SC-7: Boundary Protection

Respond with valid JSON in this format:
{{
    "control_mappings": [
        {{
            "framework": "nist_800_53",
            "control_id": "SI-2",
            "control_name": "Flaw Remediation",
            "confidence": 0.95,
            "rationale": "Vulnerability requires patching process"
        }},
        {{
            "framework": "iso_27001",
            "control_id": "A.12.6.1",
            "control_name": "Management of technical vulnerabilities",
            "confidence": 0.90,
            "rationale": "Directly addresses vulnerability management"
        }}
    ],
    "compliance_impact": "high",
    "remediation_priority": "immediate|high|medium|low",
    "compliance_notes": "Brief summary of compliance implications"
}}"""

        return prompt
