"""
CVE Entity Extractor LLM Agent.

Uses Claude Haiku 4.5 to extract structured entities from CVE descriptions.
Identifies affected products, vendors, attack vectors, and exploitation requirements.

Model: Claude Haiku 4.5 (fast, cost-effective for extraction)
Output: Enriched vulnerability documents with structured metadata
"""

from typing import List, Dict, Any
import json
from datetime import datetime
import structlog

from ..agents.base import BaseLLMAgent

logger = structlog.get_logger()


class CVEEntityExtractorAgent(BaseLLMAgent):
    """
    LLM agent for extracting structured entities from CVE descriptions.

    Uses Claude Haiku 4.5 for fast entity extraction.
    """

    # LLM configuration
    MODEL = "claude-haiku-4.5"
    MAX_TOKENS = 1024
    BATCH_SIZE = 100  # Fast model, can process larger batches

    def find_gaps(self) -> List[Dict[str, Any]]:
        """
        Find CVEs without structured entity extraction.

        Returns:
            list[dict]: CVEs needing entity extraction

        Query Logic:
            - Find vulnerabilities without extracted_entities field
            - Prioritize high-severity CVEs
            - Limit to BATCH_SIZE
        """
        self.logger.info("Finding CVEs needing entity extraction")

        query = """
        FOR cve IN vulnerabilities
            FILTER cve.description != null AND cve.description != ""
            FILTER cve.extracted_entities == null
            SORT cve.cvss_v3_score DESC, cve.published DESC
            LIMIT @batch_size
            RETURN {
                _key: cve._key,
                cve_id: cve.cve_id,
                description: cve.description,
                cvss_v3_score: cve.cvss_v3_score
            }
        """

        cursor = self.db.aql.execute(
            query,
            bind_vars={'batch_size': self.BATCH_SIZE}
        )

        gaps = list(cursor)

        self.logger.info(
            "Found CVEs needing entity extraction",
            count=len(gaps),
        )

        return gaps

    def enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured entities from CVE using Claude Haiku 4.5.

        Args:
            record: CVE record from find_gaps()

        Returns:
            dict: Enrichment data with extracted entities

        Raises:
            Exception: On API failure or parsing error
        """
        cve_id = record.get('cve_id', '')
        description = record.get('description', '')

        # Construct prompt
        prompt = self._build_extraction_prompt(cve_id, description)

        self.logger.debug("Calling Claude API for entity extraction", cve_id=cve_id)

        # L5: Use Haiku for entity extraction from CVE descriptions ($5)
        try:
            response = self.anthropic_client.messages.create(
                model=self.settings.ANTHROPIC_MODEL_HAIKU,
                max_tokens=self.MAX_TOKENS,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            response_text = response.content[0].text
            response_text = self._strip_markdown_fences(response_text)
            result = json.loads(response_text)

            enrichment = {
                'cve_key': record.get('_key'),
                'cve_id': cve_id,
                'extracted_entities': result.get('entities'),
                'attack_vector': result.get('attack_vector'),
                'prerequisites': result.get('prerequisites', []),
                'exploitation_complexity': result.get('exploitation_complexity'),
                'model': self.MODEL,
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'timestamp': datetime.utcnow().isoformat(),
            }

            self.logger.debug(
                "Entity extraction complete",
                cve_id=cve_id,
                entities_count=len(enrichment['extracted_entities']),
            )

            return enrichment

        except Exception as e:
            self.logger.error(
                "Entity extraction failed",
                cve_id=cve_id,
                error=str(e),
            )
            raise

    def validate(self, enrichment: Dict[str, Any]) -> bool:
        """
        Validate entity extraction quality.

        Args:
            enrichment: Enrichment data from enrich()

        Returns:
            bool: True if enrichment passes validation
        """
        entities = enrichment.get('extracted_entities', {})

        if not entities:
            self.logger.warning(
                "No entities extracted",
                cve_id=enrichment.get('cve_id'),
            )
            return False

        # Check if at least one entity type was identified
        has_data = any([
            entities.get('vendors'),
            entities.get('products'),
            entities.get('versions'),
            entities.get('attack_vectors'),
        ])

        return has_data

    def persist(self, enrichment: Dict[str, Any]) -> None:
        """
        Save extracted entities to vulnerability document.

        Args:
            enrichment: Validated enrichment data

        Updates:
            - Vulnerability document with extracted_entities field
            - llm_enrichments provenance record
        """
        cve_key = enrichment['cve_key']
        entities = enrichment['extracted_entities']

        # Update vulnerability document
        update_data = {
            'extracted_entities': entities,
            'attack_vector': enrichment['attack_vector'],
            'prerequisites': enrichment['prerequisites'],
            'exploitation_complexity': enrichment['exploitation_complexity'],
            'entity_extraction_timestamp': enrichment['timestamp'],
        }

        try:
            # ArangoDB update requires document dict with _key
            self.db.collection('vulnerabilities').update(
                {'_key': cve_key},
                update_data
            )

            self.logger.info(
                "Updated vulnerability with extracted entities",
                cve_id=enrichment['cve_id'],
                entities_count=len(entities) if isinstance(entities, dict) else 0,
            )

        except Exception as e:
            self.logger.error(
                "Failed to update vulnerability",
                cve_id=enrichment['cve_id'],
                cve_key=cve_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

        # Store provenance
        provenance = {
            'entity_type': 'vulnerability_enrichment',
            'cve_id': enrichment['cve_id'],
            'extracted_entities': entities,
            'model': enrichment['model'],
            'input_tokens': enrichment['input_tokens'],
            'output_tokens': enrichment['output_tokens'],
            'timestamp': enrichment['timestamp'],
        }

        try:
            if not self.db.has_collection('llm_enrichments'):
                self.db.create_collection('llm_enrichments', edge=False)

            self.db.collection('llm_enrichments').insert(provenance)

        except Exception as e:
            self.logger.error(
                "Failed to store provenance",
                cve_id=enrichment['cve_id'],
                error=str(e),
            )

    def _build_extraction_prompt(self, cve_id: str, description: str) -> str:
        """
        Build prompt for entity extraction.

        Args:
            cve_id: CVE identifier
            description: CVE description

        Returns:
            str: Formatted prompt for Claude
        """
        prompt = f"""You are a cybersecurity expert specializing in vulnerability analysis and information extraction.

Extract structured entities from the following CVE description:

CVE ID: {cve_id}

Description:
{description}

Extract the following information:

1. **Vendors**: Companies/organizations mentioned
2. **Products**: Software/hardware products affected
3. **Versions**: Specific version numbers or version ranges
4. **Attack Vector**: How the vulnerability can be exploited (network, local, physical, adjacent)
5. **Attack Type**: Type of attack (injection, overflow, xss, etc.)
6. **Prerequisites**: Requirements for exploitation (authentication, user interaction, etc.)
7. **Exploitation Complexity**: How difficult is exploitation (low, medium, high)
8. **Impact**: What the attacker can achieve (code execution, information disclosure, denial of service, etc.)

Respond ONLY with valid JSON in this exact format:
{{
    "entities": {{
        "vendors": ["vendor1", "vendor2"],
        "products": ["product1", "product2"],
        "versions": ["version1", "version2"],
        "attack_types": ["type1", "type2"],
        "impacts": ["impact1", "impact2"]
    }},
    "attack_vector": "network|local|physical|adjacent",
    "prerequisites": [
        "authentication_required",
        "user_interaction_required",
        "elevated_privileges_required"
    ],
    "exploitation_complexity": "low|medium|high",
    "summary": "One-sentence summary of the vulnerability"
}}

If information is not available, use empty arrays [] or null.
"""

        return prompt
