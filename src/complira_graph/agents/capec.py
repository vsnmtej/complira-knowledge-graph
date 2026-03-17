"""
CAPEC (Common Attack Pattern Enumeration and Classification) ingestion agent.

Fetches CAPEC data from MITRE and populates attack patterns collection.
CAPEC bridges ATT&CK techniques to CWE weaknesses.

Data source: https://capec.mitre.org/data/xml/capec_latest.xml
Collections populated:
- attack_patterns (document collection)
- capec_child_of (edge collection for hierarchy)
- capec_relates_to_cwe (edges to weaknesses)
- capec_maps_to_attack (edges to ATT&CK techniques)
"""

from typing import Generator
import zipfile
import io
from lxml import etree
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_capec_id, normalize_cwe_id, normalize_attack_id

logger = structlog.get_logger()


class CAPECAgent(BaseIngestionAgent):
    """
    Agent for ingesting CAPEC (Common Attack Pattern Enumeration) data.

    CAPEC provides a catalog of common attack patterns used by adversaries.
    """

    CAPEC_XML_URL = "https://capec.mitre.org/data/xml/capec_latest.xml"

    def __init__(self, db):
        """Initialize CAPEC agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="capec_mitre",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=120.0,
        )

    def fetch_data(self) -> bytes:
        """
        Fetch CAPEC XML data from MITRE.

        Returns:
            bytes: Raw XML data

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching CAPEC XML from MITRE", url=self.CAPEC_XML_URL)

        response = self.client.get(self.CAPEC_XML_URL)
        xml_data = response.content

        self.logger.info("Fetched CAPEC XML", size_bytes=len(xml_data))

        return xml_data

    def transform_data(self, raw_data: bytes) -> Generator[dict, None, None]:
        """
        Transform CAPEC XML to graph nodes and edges.

        Args:
            raw_data: Raw XML bytes from fetch_data()

        Yields:
            dict: CAPEC documents and relationship edges
        """
        # Parse XML
        root = etree.fromstring(raw_data)

        # Define XML namespace
        ns = {'capec': 'http://capec.mitre.org/capec-3'}

        # Extract attack patterns
        for attack_pattern in root.xpath('//capec:Attack_Pattern', namespaces=ns):
            capec_id = attack_pattern.get('ID')
            if not capec_id:
                continue

            # Normalize _key
            _key = normalize_capec_id(f"CAPEC-{capec_id}")

            # Extract basic fields
            name = attack_pattern.get('Name', '')
            abstraction = attack_pattern.get('Abstraction', '')  # Meta, Standard, Detailed
            status = attack_pattern.get('Status', '')

            # Description
            description_elem = attack_pattern.find('capec:Description', namespaces=ns)
            description = ''
            if description_elem is not None:
                description = ' '.join(description_elem.itertext()).strip()

            # Likelihood and severity
            likelihood_elem = attack_pattern.find('capec:Likelihood_Of_Attack', namespaces=ns)
            likelihood = likelihood_elem.text if likelihood_elem is not None else None

            severity_elem = attack_pattern.find('capec:Typical_Severity', namespaces=ns)
            severity = severity_elem.text if severity_elem is not None else None

            # Prerequisites
            prerequisites = []
            for prereq in attack_pattern.findall('capec:Prerequisites/capec:Prerequisite', namespaces=ns):
                if prereq.text:
                    prerequisites.append(prereq.text.strip())

            # Mitigations
            mitigations = []
            for mitigation in attack_pattern.findall('capec:Mitigations/capec:Mitigation', namespaces=ns):
                if mitigation.text:
                    mitigations.append(mitigation.text.strip())

            # Execution flow
            execution_flow = []
            for step in attack_pattern.findall('.//capec:Attack_Step', namespaces=ns):
                step_num = step.find('capec:Step', namespaces=ns)
                step_phase = step.find('capec:Phase', namespaces=ns)
                step_desc = step.find('capec:Description', namespaces=ns)

                execution_flow.append({
                    'step': step_num.text if step_num is not None else None,
                    'phase': step_phase.text if step_phase is not None else None,
                    'description': step_desc.text if step_desc is not None else None,
                })

            # Related CWEs
            related_cwes = []
            for cwe in attack_pattern.findall('capec:Related_Weaknesses/capec:Related_Weakness', namespaces=ns):
                cwe_id = cwe.get('CWE_ID')
                if cwe_id:
                    related_cwes.append({
                        'cwe_id': f"CWE-{cwe_id}",
                        'nature': cwe.get('Nature', 'TargetedBy'),  # Default relationship type
                    })

            # Taxonomy mappings (ATT&CK)
            attack_technique_ids = []
            for mapping in attack_pattern.findall('capec:Taxonomy_Mappings/capec:Taxonomy_Mapping', namespaces=ns):
                taxonomy_name = mapping.get('Taxonomy_Name', '')
                # Match both "ATTACK" (in XML) and "ATT&CK" (if it exists)
                if 'ATTACK' in taxonomy_name.upper():
                    for entry in mapping.findall('capec:Entry_ID', namespaces=ns):
                        if entry.text:
                            # Extract technique ID (e.g., "1574.010" -> "T1574.010")
                            technique_id = entry.text.strip()
                            # Normalize: add T prefix if not present and looks like a technique ID
                            if technique_id and not technique_id.startswith('T'):
                                # Check if it looks like a numeric technique ID
                                if technique_id.replace('.', '').isdigit():
                                    technique_id = f'T{technique_id}'
                            attack_technique_ids.append(technique_id)

            # Yield CAPEC document
            yield {
                '_key': _key,
                'capec_id': f"CAPEC-{capec_id}",
                'name': name,
                'abstraction': abstraction,
                'status': status,
                'description': description,
                'likelihood': likelihood,
                'severity': severity,
                'prerequisites': prerequisites,
                'mitigations': mitigations,
                'execution_flow': execution_flow,
                'attack_technique_ids': attack_technique_ids,
            }

            # Yield edges to related CWEs
            for related_cwe in related_cwes:
                cwe_key = normalize_cwe_id(related_cwe['cwe_id'])
                yield {
                    '_collection': 'capec_relates_to_cwe',
                    '_from': f'attack_patterns/{_key}',
                    '_to': f'weaknesses/{cwe_key}',
                    'nature': related_cwe['nature'],
                    'source': 'capec',
                }

            # Yield edges to ATT&CK techniques
            for attack_id in attack_technique_ids:
                attack_key = normalize_attack_id(attack_id)
                yield {
                    '_collection': 'capec_maps_to_attack',
                    '_from': f'attack_patterns/{_key}',
                    '_to': f'attack_techniques/{attack_key}',
                    'source': 'capec',
                }

            # Yield hierarchy edges (ChildOf relationships)
            for related in attack_pattern.findall('capec:Related_Attack_Patterns/capec:Related_Attack_Pattern', namespaces=ns):
                nature = related.get('Nature')
                related_id = related.get('CAPEC_ID')

                if nature == 'ChildOf' and related_id:
                    parent_key = normalize_capec_id(f"CAPEC-{related_id}")
                    yield {
                        '_collection': 'capec_child_of',
                        '_from': f'attack_patterns/{_key}',
                        '_to': f'attack_patterns/{parent_key}',
                        'source': 'capec',
                    }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load CAPEC data into database.

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
        edges_by_collection = {
            'capec_relates_to_cwe': [],
            'capec_child_of': [],
            'capec_maps_to_attack': [],
        }

        for record in records:
            if '_collection' in record:
                # It's an edge
                collection = record.pop('_collection')
                if collection in edges_by_collection:
                    edges_by_collection[collection].append(record)
            else:
                # It's a document
                documents.append(record)

        # Load documents
        self.logger.info("Loading CAPEC attack patterns", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='attack_patterns',
            on_duplicate=on_duplicate,
        )

        # Load edges
        total_edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        for collection, edges in edges_by_collection.items():
            if not edges:
                continue

            self.logger.info(f"Loading {collection} edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name=collection,
                on_duplicate=on_duplicate,
            )

            total_edge_stats['created'] += edge_stats['created']
            total_edge_stats['updated'] += edge_stats['updated']
            total_edge_stats['errors'] += edge_stats['errors']
            total_edge_stats['total'] += edge_stats['total']

        # Combine statistics
        combined_stats = {
            'attack_patterns': doc_stats,
            'edges': total_edge_stats,
            'total_created': doc_stats['created'] + total_edge_stats['created'],
            'total_updated': doc_stats['updated'] + total_edge_stats['updated'],
            'total_errors': doc_stats['errors'] + total_edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'attack_patterns'
