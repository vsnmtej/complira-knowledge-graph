"""
CWE Classifier LLM Agent.

Uses Claude Haiku 4.5 to classify CVEs without CWE mappings.
Fills gaps in vulnerability data by inferring appropriate weakness types.

Model: Claude Haiku 4.5 (fast, cost-effective)
Confidence Threshold: 0.85
Output: has_weakness edges with confidence scores
"""

from typing import List, Dict, Any
import json
from datetime import datetime
import structlog

from ..agents.base import BaseLLMAgent
from ..utils.keys import normalize_cve_id, normalize_cwe_id

logger = structlog.get_logger()


class CWEClassifierAgent(BaseLLMAgent):
    """
    LLM agent for classifying CVEs to CWE weakness types.

    Uses Claude Haiku 4.5 to analyze CVE descriptions and assign appropriate CWE IDs.
    """

    # LLM configuration
    MODEL = "claude-haiku-4.5"
    MAX_TOKENS = 1024
    CONFIDENCE_THRESHOLD = 0.85
    BATCH_SIZE = 100  # Process in small batches to control costs

    def find_gaps(self) -> List[Dict[str, Any]]:
        """
        Find CVEs without CWE mappings.

        Returns:
            list[dict]: CVEs needing CWE classification

        Query Logic:
            - Find vulnerabilities without has_weakness edges
            - Limit to BATCH_SIZE to control costs
            - Prioritize by CVSS score (high severity first)
        """
        self.logger.info("Finding CVEs without CWE mappings")

        query = """
        FOR cve IN vulnerabilities
            FILTER cve.source == "nvd" OR cve.source == "osv" OR cve.source == "ghsa"
            FILTER LENGTH(cve.cwe_ids) == 0 OR cve.cwe_ids == null
            // Check if has_weakness edges exist
            LET has_cwe = LENGTH(
                FOR v, e IN 1..1 OUTBOUND cve has_weakness
                    RETURN 1
            ) > 0
            FILTER !has_cwe
            // Prioritize by CVSS score (high severity first)
            SORT cve.cvss_v3_score DESC, cve.cvss_v2_score DESC
            LIMIT @batch_size
            RETURN {
                _key: cve._key,
                cve_id: cve.cve_id,
                description: cve.description,
                summary: cve.summary,
                cvss_v3_score: cve.cvss_v3_score,
                cvss_v2_score: cve.cvss_v2_score
            }
        """

        cursor = self.db.aql.execute(
            query,
            bind_vars={'batch_size': self.BATCH_SIZE}
        )

        gaps = list(cursor)

        self.logger.info(
            "Found CVEs without CWE",
            count=len(gaps),
            batch_size=self.BATCH_SIZE,
        )

        return gaps

    def enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify CVE to CWE using Claude Haiku 4.5.

        Args:
            record: CVE record from find_gaps()

        Returns:
            dict: Enrichment data with CWE classification

        Raises:
            Exception: On API failure or parsing error
        """
        cve_id = record.get('cve_id', '')
        description = record.get('description', '') or record.get('summary', '')

        if not description:
            raise ValueError(f"No description available for {cve_id}")

        # Construct prompt
        prompt = self._build_classification_prompt(cve_id, description)

        self.logger.debug("Calling Claude API for CWE classification", cve_id=cve_id)

        # Call Claude API - L1: Use Haiku for fast CWE classification ($2.50)
        try:
            response = self.anthropic_client.messages.create(
                model=self.settings.ANTHROPIC_MODEL_HAIKU,
                max_tokens=self.MAX_TOKENS,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Extract response text
            response_text = response.content[0].text
            response_text = self._strip_markdown_fences(response_text)

            # Parse JSON response
            result = json.loads(response_text)

            # Build enrichment data
            enrichment = {
                'cve_key': record.get('_key'),
                'cve_id': cve_id,
                'cwe_id': result.get('cwe_id'),
                'cwe_name': result.get('cwe_name'),
                'confidence': result.get('confidence'),
                'reasoning': result.get('reasoning'),
                'model': self.MODEL,
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'timestamp': datetime.utcnow().isoformat(),
            }

            self.logger.debug(
                "CWE classification complete",
                cve_id=cve_id,
                cwe_id=enrichment['cwe_id'],
                confidence=enrichment['confidence'],
            )

            return enrichment

        except json.JSONDecodeError as e:
            self.logger.error(
                "Failed to parse LLM response",
                cve_id=cve_id,
                error=str(e),
                response=response_text if 'response_text' in locals() else None,
            )
            raise

        except Exception as e:
            self.logger.error(
                "LLM API call failed",
                cve_id=cve_id,
                error=str(e),
            )
            raise

    def validate(self, enrichment: Dict[str, Any]) -> bool:
        """
        Validate CWE classification quality.

        Args:
            enrichment: Enrichment data from enrich()

        Returns:
            bool: True if enrichment passes validation

        Validation Rules:
            - CWE ID must be present and valid format (CWE-###)
            - Confidence must be >= 0.85
            - CWE must exist in weaknesses collection
        """
        cwe_id = enrichment.get('cwe_id', '')
        confidence = enrichment.get('confidence', 0.0)

        # Check CWE ID format
        if not cwe_id or not cwe_id.startswith('CWE-'):
            self.logger.warning(
                "Invalid CWE ID format",
                cve_id=enrichment.get('cve_id'),
                cwe_id=cwe_id,
            )
            return False

        # Check confidence threshold
        if confidence < self.CONFIDENCE_THRESHOLD:
            self.logger.debug(
                "Confidence below threshold",
                cve_id=enrichment.get('cve_id'),
                confidence=confidence,
                threshold=self.CONFIDENCE_THRESHOLD,
            )
            return False

        # Verify CWE exists in database
        cwe_key = normalize_cwe_id(cwe_id)
        cwe_exists = self.db.collection('weaknesses').has(cwe_key)

        if not cwe_exists:
            self.logger.warning(
                "CWE does not exist in database",
                cve_id=enrichment.get('cve_id'),
                cwe_id=cwe_id,
                cwe_key=cwe_key,
            )
            return False

        return True

    def persist(self, enrichment: Dict[str, Any]) -> None:
        """
        Save CWE classification and provenance.

        Args:
            enrichment: Validated enrichment data

        Creates:
            1. has_weakness edge (vulnerabilities → weaknesses)
            2. llm_enrichments provenance record
        """
        cve_key = enrichment['cve_key']
        cwe_id = enrichment['cwe_id']
        cwe_key = normalize_cwe_id(cwe_id)

        # Create has_weakness edge
        edge = {
            '_from': f'vulnerabilities/{cve_key}',
            '_to': f'weaknesses/{cwe_key}',
            'confidence': enrichment['confidence'],
            'source': 'llm',
            'model': enrichment['model'],
            'reasoning': enrichment['reasoning'],
            'timestamp': enrichment['timestamp'],
        }

        try:
            self.db.collection('has_weakness').insert(edge, overwrite_mode='ignore')

            self.logger.info(
                "Created has_weakness edge",
                cve_id=enrichment['cve_id'],
                cwe_id=cwe_id,
                confidence=enrichment['confidence'],
            )

        except Exception as e:
            self.logger.error(
                "Failed to create has_weakness edge",
                cve_id=enrichment['cve_id'],
                error=str(e),
            )
            raise

        # Store provenance in llm_enrichments
        provenance = {
            'entity_type': 'has_weakness',
            'entity_from': f'vulnerabilities/{cve_key}',
            'entity_to': f'weaknesses/{cwe_key}',
            'cve_id': enrichment['cve_id'],
            'cwe_id': cwe_id,
            'confidence': enrichment['confidence'],
            'reasoning': enrichment['reasoning'],
            'model': enrichment['model'],
            'input_tokens': enrichment['input_tokens'],
            'output_tokens': enrichment['output_tokens'],
            'timestamp': enrichment['timestamp'],
        }

        try:
            # Note: llm_enrichments collection should be created in db.py if not exists
            # For now, we'll create it on-demand
            if not self.db.has_collection('llm_enrichments'):
                self.db.create_collection('llm_enrichments', edge=False)

            self.db.collection('llm_enrichments').insert(provenance)

            self.logger.debug(
                "Stored LLM enrichment provenance",
                cve_id=enrichment['cve_id'],
            )

        except Exception as e:
            self.logger.error(
                "Failed to store provenance",
                cve_id=enrichment['cve_id'],
                error=str(e),
            )
            # Don't raise - provenance failure shouldn't break edge creation

    def _build_classification_prompt(self, cve_id: str, description: str) -> str:
        """
        Build prompt for CWE classification.

        Args:
            cve_id: CVE identifier
            description: CVE description

        Returns:
            str: Formatted prompt for Claude
        """
        prompt = f"""You are a cybersecurity expert specializing in vulnerability classification using the Common Weakness Enumeration (CWE) taxonomy.

Analyze the following CVE description and classify it to the most appropriate CWE weakness type.

CVE ID: {cve_id}

Description:
{description}

Instructions:
1. Identify the PRIMARY weakness type described in this vulnerability
2. Select the most SPECIFIC applicable CWE (prefer Base/Variant over Pillar/Class)
3. Provide a confidence score (0.0 to 1.0) for your classification
4. Explain your reasoning in 1-2 sentences

Common CWE categories to consider:
- CWE-79: Cross-site Scripting (XSS)
- CWE-89: SQL Injection
- CWE-78: OS Command Injection
- CWE-22: Path Traversal
- CWE-434: Unrestricted Upload of File with Dangerous Type
- CWE-787: Out-of-bounds Write
- CWE-125: Out-of-bounds Read
- CWE-416: Use After Free
- CWE-20: Improper Input Validation
- CWE-200: Exposure of Sensitive Information
- CWE-119: Improper Restriction of Operations within Memory Buffer
- CWE-862: Missing Authorization
- CWE-476: NULL Pointer Dereference
- CWE-502: Deserialization of Untrusted Data

Respond ONLY with valid JSON in this exact format:
{{
    "cwe_id": "CWE-###",
    "cwe_name": "Name of the weakness",
    "confidence": 0.95,
    "reasoning": "Brief explanation of why this CWE was selected"
}}"""

        return prompt


# ========== Cost Estimation ==========

def estimate_classification_cost(num_cves: int, avg_description_length: int = 500) -> Dict[str, float]:
    """
    Estimate cost for CWE classification.

    Args:
        num_cves: Number of CVEs to classify
        avg_description_length: Average description length in characters

    Returns:
        dict: Cost estimates

    Pricing (Claude Haiku 4.5):
        Input: $0.80 per million tokens
        Output: $4.00 per million tokens

    Assumptions:
        - Input: ~1000 tokens per CVE (prompt + description)
        - Output: ~200 tokens per CVE (CWE classification + reasoning)
    """
    # Token estimates
    input_tokens_per_cve = 1000  # Conservative estimate
    output_tokens_per_cve = 200

    total_input_tokens = num_cves * input_tokens_per_cve
    total_output_tokens = num_cves * output_tokens_per_cve

    # Pricing
    input_cost_per_million = 0.80
    output_cost_per_million = 4.00

    input_cost = (total_input_tokens / 1_000_000) * input_cost_per_million
    output_cost = (total_output_tokens / 1_000_000) * output_cost_per_million
    total_cost = input_cost + output_cost

    return {
        'num_cves': num_cves,
        'total_input_tokens': total_input_tokens,
        'total_output_tokens': total_output_tokens,
        'input_cost_usd': round(input_cost, 2),
        'output_cost_usd': round(output_cost, 2),
        'total_cost_usd': round(total_cost, 2),
        'cost_per_cve_usd': round(total_cost / num_cves, 4) if num_cves > 0 else 0,
    }
