"""
ATLAS (Adversarial Threat Landscape for Artificial-Intelligence Systems) ingestion agent.

Fetches ATLAS data from MITRE and populates AI/ML-specific attack techniques collection.
ATLAS extends ATT&CK with techniques specific to AI/ML systems.

Data source: https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/dist/ATLAS.yaml
Collections populated:
- atlas_techniques (document collection)
- atlas_maps_to_attack (edges to ATT&CK techniques)
"""

from typing import Generator
import yaml
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_attack_id

logger = structlog.get_logger()


class ATLASAgent(BaseIngestionAgent):
    """
    Agent for ingesting ATLAS (AI/ML Attack Framework) data.

    ATLAS provides a knowledge base of adversary tactics and techniques for AI/ML systems.
    """

    # ATLAS data from GitHub repository
    ATLAS_YAML_URL = "https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/dist/ATLAS.yaml"

    def __init__(self, db):
        """Initialize ATLAS agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="atlas_mitre",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=60.0,
        )

    def fetch_data(self) -> dict:
        """
        Fetch ATLAS data from MITRE GitHub repository.

        Returns:
            dict: ATLAS data as YAML/dict

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching ATLAS data from MITRE GitHub", url=self.ATLAS_YAML_URL)

        response = self.client.get(self.ATLAS_YAML_URL)
        data = yaml.safe_load(response.content)

        # Extract techniques from matrices structure
        # ATLAS YAML has structure: matrices[0].techniques
        techniques = []
        if 'matrices' in data and len(data['matrices']) > 0:
            matrix = data['matrices'][0]
            techniques = matrix.get('techniques', [])

        self.logger.info(
            "Fetched ATLAS data",
            techniques_count=len(techniques),
        )

        return {'techniques': techniques}

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform ATLAS YAML to graph nodes and edges.

        Args:
            raw_data: YAML data from fetch_data()

        Yields:
            dict: ATLAS technique documents and relationship edges
        """
        techniques = raw_data.get('techniques', [])

        for technique in techniques:
            # Extract technique ID (e.g., "AML.T0000")
            atlas_id = technique.get('id', '')
            if not atlas_id:
                continue

            # Use atlas_id as _key (e.g., "AML_T0000")
            _key = atlas_id.replace('.', '_')

            # Extract basic fields
            name = technique.get('name', '')
            description = technique.get('description', '')

            # Tactic information (ATLAS uses simple string list of tactic IDs)
            tactics = technique.get('tactics', [])
            tactic_ids = tactics if isinstance(tactics, list) else []

            # Platforms
            platforms = technique.get('platforms', [])

            # Related ATT&CK techniques (field name: 'ATT&CK-reference')
            attack_techniques = []
            attack_ref = technique.get('ATT&CK-reference')
            if attack_ref and isinstance(attack_ref, dict):
                attack_id = attack_ref.get('id', '')
                # Extract ATT&CK ID (e.g., "T1596")
                if attack_id and attack_id.startswith('T'):
                    attack_techniques.append(attack_id)

            # Case studies
            case_studies = technique.get('case-studies', [])
            case_study_refs = []
            for study in case_studies:
                if isinstance(study, dict):
                    case_study_refs.append({
                        'name': study.get('name', ''),
                        'url': study.get('url', ''),
                    })
                elif isinstance(study, str):
                    case_study_refs.append({'name': study})

            # Mitigations
            mitigations = technique.get('mitigations', [])
            mitigation_list = []
            for mitigation in mitigations:
                if isinstance(mitigation, dict):
                    mitigation_list.append({
                        'id': mitigation.get('id', ''),
                        'description': mitigation.get('description', ''),
                    })
                elif isinstance(mitigation, str):
                    mitigation_list.append({'description': mitigation})

            # Detection
            detections = technique.get('detections', [])
            detection_list = []
            for detection in detections:
                if isinstance(detection, dict):
                    detection_list.append({
                        'id': detection.get('id', ''),
                        'description': detection.get('description', ''),
                    })
                elif isinstance(detection, str):
                    detection_list.append({'description': detection})

            # References
            references = technique.get('references', [])
            reference_list = []
            for ref in references:
                if isinstance(ref, dict):
                    reference_list.append({
                        'title': ref.get('title', ''),
                        'url': ref.get('url', ''),
                    })
                elif isinstance(ref, str):
                    reference_list.append({'title': ref})

            # Yield ATLAS technique document
            yield {
                '_key': _key,
                'atlas_id': atlas_id,
                'name': name,
                'description': description,
                'tactic_ids': tactic_ids,
                'platforms': platforms,
                'case_studies': case_study_refs,
                'mitigations': mitigation_list,
                'detections': detection_list,
                'references': reference_list,
            }

            # Yield edges to ATT&CK techniques
            for attack_id in attack_techniques:
                attack_key = normalize_attack_id(attack_id)
                yield {
                    '_collection': 'atlas_maps_to_attack',
                    '_from': f'atlas_techniques/{_key}',
                    '_to': f'attack_techniques/{attack_key}',
                    'source': 'atlas',
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load ATLAS data into database.

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
        self.logger.info("Loading ATLAS techniques", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='atlas_techniques',
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        if edges:
            self.logger.info("Loading atlas_maps_to_attack edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name='atlas_maps_to_attack',
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            'atlas_techniques': doc_stats,
            'edges': edge_stats,
            'total_created': doc_stats['created'] + edge_stats['created'],
            'total_updated': doc_stats['updated'] + edge_stats['updated'],
            'total_errors': doc_stats['errors'] + edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'atlas_techniques'
