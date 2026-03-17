"""
MITRE ATT&CK ingestion agent.

Fetches ATT&CK Enterprise framework data and populates attack-related collections.

Data source: https://github.com/mitre/cti (STIX 2.1 JSON)
Collections populated:
- attack_techniques (techniques and sub-techniques)
- threat_groups (threat actor groups)
- technique_exploits_weakness (edges to CWE)
- uses_technique, mitigates, subtechnique_of, etc.
"""

from typing import Generator
import json
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_attack_id, normalize_cwe_id

logger = structlog.get_logger()


class ATTACKAgent(BaseIngestionAgent):
    """
    Agent for ingesting MITRE ATT&CK Enterprise framework data.

    ATT&CK provides a knowledge base of adversary tactics and techniques.
    """

    # ATT&CK Enterprise STIX bundle URL
    ATTACK_ENTERPRISE_URL = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"

    def __init__(self, db):
        """Initialize ATT&CK agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="mitre_attack",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=60.0,
        )

    def fetch_data(self) -> dict:
        """
        Fetch ATT&CK STIX bundle from GitHub.

        Returns:
            dict: STIX 2.1 bundle as JSON

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching ATT&CK Enterprise data", url=self.ATTACK_ENTERPRISE_URL)

        response = self.client.get(self.ATTACK_ENTERPRISE_URL)
        data = response.json()

        self.logger.info(
            "Fetched ATT&CK data",
            objects_count=len(data.get('objects', [])),
        )

        return data

    def transform_data(self, raw_data: dict) -> Generator[dict, None, None]:
        """
        Transform ATT&CK STIX data to graph nodes and edges.

        Args:
            raw_data: STIX 2.1 bundle from fetch_data()

        Yields:
            dict: ATT&CK documents and relationship edges
        """
        objects = raw_data.get('objects', [])

        # Process by STIX type
        for obj in objects:
            stix_type = obj.get('type')

            if stix_type == 'attack-pattern':
                # Attack techniques and sub-techniques
                yield from self._transform_technique(obj)

            elif stix_type == 'intrusion-set':
                # Threat actor groups
                yield from self._transform_group(obj)

            elif stix_type == 'relationship':
                # Relationships between objects
                yield from self._transform_relationship(obj)

    def _transform_technique(self, obj: dict) -> Generator[dict, None, None]:
        """
        Transform ATT&CK technique to graph node.

        Args:
            obj: STIX attack-pattern object

        Yields:
            dict: Technique document and edges
        """
        # Extract external references (technique ID)
        external_refs = obj.get('external_references', [])
        technique_ref = next(
            (ref for ref in external_refs if ref.get('source_name') == 'mitre-attack'),
            None
        )

        if not technique_ref:
            return

        technique_id = technique_ref.get('external_id')  # e.g., "T1059.001"
        if not technique_id:
            return

        _key = normalize_attack_id(technique_id)

        # Check if sub-technique
        is_subtechnique = '.' in technique_id
        parent_technique = technique_id.split('.')[0] if is_subtechnique else None

        # Extract kill chain phases (tactics)
        kill_chain_phases = obj.get('kill_chain_phases', [])
        tactic_names = [phase.get('phase_name') for phase in kill_chain_phases]

        # Platforms
        platforms = obj.get('x_mitre_platforms', [])

        # Data sources
        data_sources = obj.get('x_mitre_data_sources', [])

        # Detection guidance
        detection = obj.get('x_mitre_detection', '')

        # Deprecated status
        deprecated = obj.get('x_mitre_deprecated', False) or obj.get('revoked', False)

        # Yield technique document
        yield {
            '_key': _key,
            'technique_id': technique_id,
            'name': obj.get('name', ''),
            'description': obj.get('description', ''),
            'tactic_names': tactic_names,
            'is_subtechnique': is_subtechnique,
            'parent_technique': parent_technique,
            'platforms': platforms,
            'data_sources': data_sources,
            'detection': detection,
            'url': technique_ref.get('url', ''),
            'stix_id': obj.get('id', ''),
            'deprecated': deprecated,
            'mitre_version': obj.get('x_mitre_version', ''),
        }

        # Yield sub-technique edge if applicable
        if is_subtechnique and parent_technique:
            parent_key = normalize_attack_id(parent_technique)
            yield {
                '_collection': 'subtechnique_of',
                '_from': f'attack_techniques/{_key}',
                '_to': f'attack_techniques/{parent_key}',
                'source': 'mitre_attack',
            }

    def _transform_group(self, obj: dict) -> Generator[dict, None, None]:
        """
        Transform threat actor group to graph node.

        Args:
            obj: STIX intrusion-set object

        Yields:
            dict: Group document
        """
        # Extract external references
        external_refs = obj.get('external_references', [])
        group_ref = next(
            (ref for ref in external_refs if ref.get('source_name') == 'mitre-attack'),
            None
        )

        if not group_ref:
            return

        group_id = group_ref.get('external_id')  # e.g., "G0001"
        if not group_id:
            return

        _key = group_id  # Groups use G#### format, already valid

        # Aliases
        aliases = obj.get('aliases', [])

        yield {
            '_key': _key,
            'group_id': group_id,
            'name': obj.get('name', ''),
            'description': obj.get('description', ''),
            'aliases': aliases,
            'url': group_ref.get('url', ''),
            'stix_id': obj.get('id', ''),
            'mitre_version': obj.get('x_mitre_version', ''),
        }

    def _transform_relationship(self, obj: dict) -> Generator[dict, None, None]:
        """
        Transform STIX relationship to graph edge.

        Args:
            obj: STIX relationship object

        Yields:
            dict: Relationship edge
        """
        relationship_type = obj.get('relationship_type')
        source_ref = obj.get('source_ref', '')
        target_ref = obj.get('target_ref', '')

        # Only process certain relationship types
        if relationship_type not in ['uses', 'mitigates', 'subtechnique-of']:
            return

        # Determine source and target collections from STIX IDs
        # Format: intrusion-set--<uuid>, attack-pattern--<uuid>, course-of-action--<uuid>

        source_type = source_ref.split('--')[0] if '--' in source_ref else None
        target_type = target_ref.split('--')[0] if '--' in target_ref else None

        if not source_type or not target_type:
            return

        # Map STIX types to collections
        type_to_collection = {
            'intrusion-set': 'threat_groups',
            'attack-pattern': 'attack_techniques',
            'malware': 'attack_software',
            'tool': 'attack_software',
            'course-of-action': 'attack_mitigations',
        }

        source_collection = type_to_collection.get(source_type)
        target_collection = type_to_collection.get(target_type)

        if not source_collection or not target_collection:
            return

        # Map relationship type to edge collection
        edge_collection_map = {
            'uses': 'uses_technique',
            'mitigates': 'mitigates',
            'subtechnique-of': 'subtechnique_of',
        }

        edge_collection = edge_collection_map.get(relationship_type)
        if not edge_collection:
            return

        # Note: We use STIX IDs as temporary identifiers here
        # In a production system, you'd need to resolve STIX IDs to _keys
        # For now, we'll store the relationship but it may not have valid _from/_to
        # This is a known limitation that should be addressed in refinement

        yield {
            '_collection': edge_collection,
            '_stix_source_ref': source_ref,
            '_stix_target_ref': target_ref,
            'relationship_type': relationship_type,
            'description': obj.get('description', ''),
            'source': 'mitre_attack',
        }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load ATT&CK data into database.

        Overrides base class to handle multiple collections.

        Args:
            records: Generator from transform_data()
            collection_name: Ignored
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Combined statistics
        """
        # Separate by type
        techniques = []
        groups = []
        edges_by_collection = {}

        for record in records:
            if '_collection' in record:
                # It's an edge
                collection = record.pop('_collection')
                if collection not in edges_by_collection:
                    edges_by_collection[collection] = []
                edges_by_collection[collection].append(record)
            elif 'technique_id' in record:
                techniques.append(record)
            elif 'group_id' in record:
                groups.append(record)

        stats = {}

        # Load techniques
        if techniques:
            self.logger.info("Loading ATT&CK techniques", count=len(techniques))
            stats['techniques'] = super().load_data(
                iter(techniques),
                collection_name='attack_techniques',
                on_duplicate=on_duplicate,
            )

        # Load groups
        if groups:
            self.logger.info("Loading ATT&CK groups", count=len(groups))
            stats['groups'] = super().load_data(
                iter(groups),
                collection_name='threat_groups',
                on_duplicate=on_duplicate,
            )

        # Load edges
        # Note: Edges with _stix_*_ref won't work until we resolve STIX IDs
        # Skipping edge loading for now - needs refinement
        self.logger.warning(
            "Skipping ATT&CK relationship edges (requires STIX ID resolution)",
            edge_collections=list(edges_by_collection.keys()),
        )

        return stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'attack_techniques'
