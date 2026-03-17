"""
PURL to CPE Mapper LLM Agent.

Uses Claude Sonnet 4.5 to map Package URLs (PURL) to CPE identifiers.
Bridges the gap between modern package managers and legacy CPE-based vulnerability databases.

Model: Claude Sonnet 4.5 (higher reasoning capability)
Confidence Threshold: 0.90
Output: matched_by_cpe edges linking components to CPE entries
"""

from typing import List, Dict, Any
import json
from datetime import datetime
import structlog

from ..agents.base import BaseLLMAgent
from ..utils.keys import normalize_purl

logger = structlog.get_logger()


class PURLtoCPEAgent(BaseLLMAgent):
    """
    LLM agent for mapping Package URLs to CPE identifiers.

    Uses Claude Sonnet 4.5 to understand package ecosystem conventions and generate accurate CPE mappings.
    """

    # LLM configuration
    MODEL = "claude-sonnet-4.5"
    MAX_TOKENS = 2048
    CONFIDENCE_THRESHOLD = 0.90
    BATCH_SIZE = 50

    def find_gaps(self) -> List[Dict[str, Any]]:
        """
        Find components without CPE mappings.

        Returns:
            list[dict]: Components needing CPE mapping

        Query Logic:
            - Find components without matched_by_cpe edges
            - Limit to BATCH_SIZE to control costs
            - Prioritize components with known vulnerabilities
        """
        self.logger.info("Finding components without CPE mappings")

        query = """
        FOR component IN components
            FILTER component.purl != null
            // Check if CPE mapping exists
            LET has_cpe = LENGTH(
                FOR v, e IN 1..1 OUTBOUND component matched_by_cpe
                    RETURN 1
            ) > 0
            FILTER !has_cpe
            // Prioritize components with vulnerabilities
            LET has_vulns = LENGTH(
                FOR v, e IN 1..1 INBOUND component affects
                    RETURN 1
            ) > 0
            SORT has_vulns DESC, component.name ASC
            LIMIT @batch_size
            RETURN {
                _key: component._key,
                purl: component.purl,
                ecosystem: component.ecosystem,
                name: component.name,
                latest_version: component.latest_version
            }
        """

        cursor = self.db.aql.execute(
            query,
            bind_vars={'batch_size': self.BATCH_SIZE}
        )

        gaps = list(cursor)

        self.logger.info(
            "Found components without CPE",
            count=len(gaps),
        )

        return gaps

    def enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map PURL to CPE using Claude Sonnet 4.5.

        Args:
            record: Component record from find_gaps()

        Returns:
            dict: Enrichment data with CPE mapping

        Raises:
            Exception: On API failure or parsing error
        """
        purl = record.get('purl', '')
        ecosystem = record.get('ecosystem', '')
        name = record.get('name', '')
        version = record.get('latest_version', '')

        # Construct prompt
        prompt = self._build_mapping_prompt(purl, ecosystem, name, version)

        self.logger.debug("Calling Claude API for PURL to CPE mapping", purl=purl)

        # L2: Use Sonnet for PURL→CPE infrastructure mapping ($15)
        try:
            response = self.anthropic_client.messages.create(
                model=self.settings.ANTHROPIC_MODEL_SONNET,
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
                'component_key': record.get('_key'),
                'purl': purl,
                'cpe_uri': result.get('cpe_uri'),
                'vendor': result.get('vendor'),
                'product': result.get('product'),
                'version': result.get('version', '*'),
                'confidence': result.get('confidence'),
                'reasoning': result.get('reasoning'),
                'model': self.MODEL,
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'timestamp': datetime.utcnow().isoformat(),
            }

            self.logger.debug(
                "PURL to CPE mapping complete",
                purl=purl,
                cpe_uri=enrichment['cpe_uri'],
                confidence=enrichment['confidence'],
            )

            return enrichment

        except Exception as e:
            self.logger.error(
                "PURL to CPE mapping failed",
                purl=purl,
                error=str(e),
            )
            raise

    def validate(self, enrichment: Dict[str, Any]) -> bool:
        """
        Validate CPE mapping quality.

        Args:
            enrichment: Enrichment data from enrich()

        Returns:
            bool: True if enrichment passes validation

        Validation Rules:
            - CPE URI must be present and valid format
            - Confidence must be >= 0.90
            - Vendor and product must be present
        """
        cpe_uri = enrichment.get('cpe_uri', '')
        confidence = enrichment.get('confidence', 0.0)
        vendor = enrichment.get('vendor', '')
        product = enrichment.get('product', '')

        # Check CPE URI format (cpe:2.3:a:vendor:product:...)
        if not cpe_uri or not cpe_uri.startswith('cpe:2.3:'):
            self.logger.warning(
                "Invalid CPE URI format",
                purl=enrichment.get('purl'),
                cpe_uri=cpe_uri,
            )
            return False

        # Check confidence threshold
        if confidence < self.CONFIDENCE_THRESHOLD:
            self.logger.debug(
                "Confidence below threshold",
                purl=enrichment.get('purl'),
                confidence=confidence,
                threshold=self.CONFIDENCE_THRESHOLD,
            )
            return False

        # Verify vendor and product
        if not vendor or not product:
            self.logger.warning(
                "Missing vendor or product",
                purl=enrichment.get('purl'),
                vendor=vendor,
                product=product,
            )
            return False

        return True

    def persist(self, enrichment: Dict[str, Any]) -> None:
        """
        Save CPE mapping and provenance.

        Args:
            enrichment: Validated enrichment data

        Creates:
            1. cpe_entries document (if not exists)
            2. matched_by_cpe edge (components → cpe_entries)
            3. llm_enrichments provenance record
        """
        component_key = enrichment['component_key']
        cpe_uri = enrichment['cpe_uri']

        # Generate CPE key
        import hashlib
        if len(cpe_uri) > 200:
            cpe_key = f"cpe_{hashlib.sha256(cpe_uri.encode()).hexdigest()[:32]}"
        else:
            cpe_key = cpe_uri.replace(':', '_').replace('.', '_').replace('*', 'ANY')

        # Create or update CPE entry
        cpe_entry = {
            '_key': cpe_key,
            'cpe_uri': cpe_uri,
            'vendor': enrichment['vendor'],
            'product': enrichment['product'],
            'version': enrichment.get('version', '*'),
            'source': 'llm',
        }

        try:
            self.db.collection('cpe_entries').insert(
                cpe_entry,
                overwrite_mode='update'
            )

            self.logger.debug(
                "Created/updated CPE entry",
                cpe_uri=cpe_uri,
            )

        except Exception as e:
            self.logger.error(
                "Failed to create CPE entry",
                cpe_uri=cpe_uri,
                error=str(e),
            )
            raise

        # Create matched_by_cpe edge
        edge = {
            '_from': f'components/{component_key}',
            '_to': f'cpe_entries/{cpe_key}',
            'confidence': enrichment['confidence'],
            'source': 'llm',
            'model': enrichment['model'],
            'reasoning': enrichment['reasoning'],
            'timestamp': enrichment['timestamp'],
        }

        try:
            self.db.collection('matched_by_cpe').insert(edge, overwrite_mode='ignore')

            self.logger.info(
                "Created matched_by_cpe edge",
                purl=enrichment['purl'],
                cpe_uri=cpe_uri,
                confidence=enrichment['confidence'],
            )

        except Exception as e:
            self.logger.error(
                "Failed to create matched_by_cpe edge",
                purl=enrichment['purl'],
                error=str(e),
            )
            raise

        # Store provenance
        provenance = {
            'entity_type': 'matched_by_cpe',
            'entity_from': f'components/{component_key}',
            'entity_to': f'cpe_entries/{cpe_key}',
            'purl': enrichment['purl'],
            'cpe_uri': cpe_uri,
            'confidence': enrichment['confidence'],
            'reasoning': enrichment['reasoning'],
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
                purl=enrichment['purl'],
                error=str(e),
            )

    def _build_mapping_prompt(self, purl: str, ecosystem: str, name: str, version: str) -> str:
        """
        Build prompt for PURL to CPE mapping.

        Args:
            purl: Package URL
            ecosystem: Package ecosystem (npm, pypi, etc.)
            name: Package name
            version: Package version

        Returns:
            str: Formatted prompt for Claude
        """
        prompt = f"""You are a cybersecurity expert specializing in software vulnerability identification and CPE (Common Platform Enumeration) naming conventions.

Map the following Package URL (PURL) to a CPE 2.3 identifier.

Package Information:
- PURL: {purl}
- Ecosystem: {ecosystem}
- Name: {name}
- Version: {version or "Not specified"}

CPE 2.3 Format:
cpe:2.3:part:vendor:product:version:update:edition:language:sw_edition:target_sw:target_hw:other

Where:
- part: 'a' (application), 'h' (hardware), 'o' (operating system)
- vendor: Vendor name (lowercase, underscores for spaces)
- product: Product name (lowercase, underscores for spaces)
- version: Version string (or '*' for any version)
- Remaining fields: Usually '*' (any)

Common Ecosystem Mappings:
- npm packages: Usually vendor is the organization/author, product is package name
- PyPI packages: Python packages, vendor often matches package name or maintainer
- Maven: Format is groupId:artifactId, vendor is usually group domain
- Go: Vendor is often the domain (e.g., golang for golang.org packages)
- RubyGems: Vendor often matches gem name or author
- Crates.io: Rust packages, vendor often is package maintainer

Instructions:
1. Determine the appropriate CPE vendor (consider official project, organization, or maintainer)
2. Determine the CPE product name (normalize to lowercase, replace spaces/hyphens with underscores)
3. Include version if specific, otherwise use '*'
4. Provide a confidence score (0.0 to 1.0) for your mapping
5. Explain your reasoning

Respond ONLY with valid JSON in this exact format:
{{
    "cpe_uri": "cpe:2.3:a:vendor:product:version:*:*:*:*:*:*:*",
    "vendor": "vendor_name",
    "product": "product_name",
    "version": "version or *",
    "confidence": 0.95,
    "reasoning": "Brief explanation of CPE mapping logic"
}}"""

        return prompt
