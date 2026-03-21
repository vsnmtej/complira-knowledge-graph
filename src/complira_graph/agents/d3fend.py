"""
D3FEND (Detection, Denial, and Disruption Framework Empowering Network Defense) ingestion agent.

Fetches D3FEND ontology from MITRE and populates defensive techniques collection.
D3FEND provides defensive countermeasures mapped to ATT&CK offensive techniques.

Data sources:
- https://d3fend.mitre.org/ontologies/d3fend.json (techniques)
- https://d3fend.mitre.org/api/ontology/inference/d3fend-full-mappings.csv (ATT&CK mappings)

Collections populated:
- d3fend_techniques (document collection)
- d3fend_counters_technique (edges to ATT&CK techniques)
"""

from typing import Generator
import csv
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_attack_id

logger = structlog.get_logger()


class D3FENDAgent(BaseIngestionAgent):
    """
    Agent for ingesting D3FEND (Defensive Framework) data.

    D3FEND provides a knowledge graph of defensive cybersecurity techniques.
    """

    D3FEND_JSON_URL = "https://d3fend.mitre.org/ontologies/d3fend.json"
    D3FEND_MAPPINGS_CSV_URL = "https://d3fend.mitre.org/api/ontology/inference/d3fend-full-mappings.csv"

    def __init__(self, db):
        """Initialize D3FEND agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="d3fend_mitre",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=120.0,
        )

    def fetch_data(self) -> dict:
        """
        Fetch D3FEND ontology and ATT&CK mappings from MITRE.

        Returns:
            dict: Contains 'ontology' (JSON-LD) and 'mappings' (CSV data)

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching D3FEND ontology from MITRE", url=self.D3FEND_JSON_URL)

        # Fetch JSON-LD ontology
        response = self.client.get(self.D3FEND_JSON_URL)
        ontology_data = response.json()

        self.logger.info(
            "Fetched D3FEND ontology",
            graph_count=len(ontology_data.get('@graph', [])),
        )

        # Fetch ATT&CK mappings CSV
        self.logger.info("Fetching D3FEND ATT&CK mappings", url=self.D3FEND_MAPPINGS_CSV_URL)
        csv_response = self.client.get(self.D3FEND_MAPPINGS_CSV_URL)
        csv_lines = csv_response.text.splitlines()
        mappings_data = list(csv.DictReader(csv_lines))

        self.logger.info(
            "Fetched D3FEND ATT&CK mappings",
            mapping_count=len(mappings_data),
        )

        return {
            'ontology': ontology_data,
            'mappings': mappings_data,
        }

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform D3FEND JSON-LD and CSV mappings to graph nodes and edges.

        Args:
            raw_data: Dict with 'ontology' (JSON-LD) and 'mappings' (CSV data) from fetch_data()

        Yields:
            dict: D3FEND technique documents and relationship edges
        """
        # Extract ontology and mappings
        ontology = raw_data.get('ontology', {})
        mappings_csv = raw_data.get('mappings', [])

        # D3FEND uses JSON-LD format with @graph containing all entities
        graph = ontology.get('@graph', [])

        # Namespaces
        D3FEND_NS = "http://d3fend.mitre.org/ontologies/d3fend.owl#"
        DCTERMS_NS = "http://purl.org/dc/terms/"
        RDF_TYPE = "@type"

        # Extract defensive techniques
        # D3FEND techniques have the d3f:d3fend-id field
        for entity in graph:
            # Check for d3fend-id (this identifies actual techniques)
            d3fend_id = entity.get('d3f:d3fend-id')
            if not d3fend_id:
                continue

            entity_id = entity.get('@id', '')

            # Extract technique ID from entity_id (e.g., "d3f:BiometricAuthentication")
            if entity_id.startswith('d3f:'):
                technique_id = entity_id.replace('d3f:', '')
            else:
                # Fallback to full entity_id as key
                technique_id = entity_id.split('#')[-1] if '#' in entity_id else entity_id

            # Use d3fend_id as part of _key for uniqueness (e.g., "BiometricAuthentication_D3_BA")
            _key = f"{technique_id}_{d3fend_id.replace('-', '_')}"

            # Extract label (human-readable name)
            label = entity.get('rdfs:label', '')
            if isinstance(label, list):
                label = label[0] if label else ''
            if isinstance(label, dict):
                label = label.get('@value', '')

            # Extract definition/description
            definition = entity.get('d3f:definition', '')
            if isinstance(definition, list):
                definition = definition[0] if definition else ''
            if isinstance(definition, dict):
                definition = definition.get('@value', '')

            # Extract parent technique (subClassOf)
            parent_technique = None
            subclass_of = entity.get('rdfs:subClassOf', [])
            if not isinstance(subclass_of, list):
                subclass_of = [subclass_of]

            for parent in subclass_of:
                if isinstance(parent, dict):
                    parent_id = parent.get('@id', '')
                elif isinstance(parent, str):
                    parent_id = parent
                else:
                    continue

                if parent_id.startswith('d3f:'):
                    parent_technique = parent_id.replace('d3f:', '')
                    # Skip abstract base classes
                    if parent_technique not in ['DefensiveTechnique', 'DigitalArtifact', 'CyberTechnique']:
                        break
                    else:
                        parent_technique = None

            # Yield D3FEND technique document
            yield {
                '_key': _key,
                'd3fend_id': d3fend_id,  # The actual D3FEND ID like "D3-BA" or "D3A-SSST"
                'technique_id': technique_id,  # The technique name like "BiometricAuthentication"
                'name': label or technique_id,
                'description': definition,
                'parent_technique': parent_technique,
                'uri': entity_id,
            }

        # Process CSV mappings to create counter edges
        # Build technique_id -> _key mapping for lookups
        technique_id_to_key = {}
        for entity in graph:
            d3fend_id = entity.get('d3f:d3fend-id')
            if not d3fend_id:
                continue

            entity_id = entity.get('@id', '')
            if entity_id.startswith('d3f:'):
                technique_id = entity_id.replace('d3f:', '')
            else:
                technique_id = entity_id.split('#')[-1] if '#' in entity_id else entity_id

            _key = f"{technique_id}_{d3fend_id.replace('-', '_')}"
            technique_id_to_key[technique_id] = _key

        # Process CSV mappings
        for mapping in mappings_csv:
            # Extract D3FEND technique URI (e.g., "http://d3fend.mitre.org/ontologies/d3fend.owl#TokenBinding")
            def_tech = mapping.get('def_tech', '')

            # Extract ATT&CK technique ID (e.g., "T1078")
            off_tech_id = mapping.get('off_tech_id', '')

            if not def_tech or not off_tech_id:
                continue

            # Extract D3FEND technique name from URI
            if '#' in def_tech:
                d3fend_technique_name = def_tech.split('#')[1]
            elif def_tech.startswith('d3f:'):
                d3fend_technique_name = def_tech.replace('d3f:', '')
            else:
                continue

            # Look up D3FEND _key
            d3fend_key = technique_id_to_key.get(d3fend_technique_name)
            if not d3fend_key:
                continue

            # Normalize ATT&CK ID
            attack_key = normalize_attack_id(off_tech_id)

            # Yield counter edge
            yield {
                '_collection': 'd3fend_counters_technique',
                '_from': f'd3fend_techniques/{d3fend_key}',
                '_to': f'attack_techniques/{attack_key}',
                'source': 'd3fend',
            }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load D3FEND data into database.

        Overrides base class to handle multiple collections.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Combined statistics
        """
        # Separate documents from edges
        documents = []
        edges = []

        for record in records:
            if '_collection' in record:
                # It's an edge
                record.pop('_collection')
                edges.append(record)
            else:
                # It's a document
                documents.append(record)

        # Load documents
        self.logger.info("Loading D3FEND techniques", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='d3fend_techniques',
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        if edges:
            self.logger.info("Loading d3fend_counters_technique edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name='d3fend_counters_technique',
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            'd3fend_techniques': doc_stats,
            'edges': edge_stats,
            'total_created': doc_stats['created'] + edge_stats['created'],
            'total_updated': doc_stats['updated'] + edge_stats['updated'],
            'total_errors': doc_stats['errors'] + edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'd3fend_techniques'
