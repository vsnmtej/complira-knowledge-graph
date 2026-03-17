"""
CWE (Common Weakness Enumeration) ingestion agent.

Fetches CWE data from MITRE and populates the weaknesses collection.

Data source: https://cwe.mitre.org/data/xml/cwec_latest.xml.zip
Collections populated:
- weaknesses (document collection)
- child_of, peer_of, can_precede, requires (edge collections for CWE hierarchy)
"""

from typing import Generator
import zipfile
import io
from lxml import etree
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cwe_id

logger = structlog.get_logger()


class CWEAgent(BaseIngestionAgent):
    """
    Agent for ingesting CWE (Common Weakness Enumeration) data.

    CWE provides a comprehensive catalog of software and hardware weakness types.
    """

    CWE_XML_URL = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"

    def __init__(self, db):
        """Initialize CWE agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="cwe_mitre",
            calls_per_period=10,  # Conservative limit for MITRE
            period_seconds=60,
            circuit_breaker=False,
            timeout=120.0,  # Large XML file
        )

    def fetch_data(self) -> bytes:
        """
        Fetch CWE XML data from MITRE.

        Returns:
            bytes: Raw XML data (extracted from ZIP)

        Raises:
            Exception: On fetch or extraction failure
        """
        self.logger.info("Fetching CWE XML from MITRE", url=self.CWE_XML_URL)

        # Download ZIP file
        response = self.client.get(self.CWE_XML_URL)
        zip_data = response.content

        self.logger.info("Downloaded CWE ZIP", size_bytes=len(zip_data))

        # Extract XML from ZIP
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # Get first XML file in ZIP
            xml_filename = [name for name in zf.namelist() if name.endswith('.xml')][0]
            xml_data = zf.read(xml_filename)

        self.logger.info("Extracted CWE XML", filename=xml_filename, size_bytes=len(xml_data))

        return xml_data

    def transform_data(self, raw_data: bytes) -> Generator[dict, None, None]:
        """
        Transform CWE XML to graph nodes and edges.

        Args:
            raw_data: Raw XML bytes from fetch_data()

        Yields:
            dict: CWE documents and relationship edges
        """
        # Parse XML
        root = etree.fromstring(raw_data)

        # Define XML namespace
        ns = {'cwe': 'http://cwe.mitre.org/cwe-7'}

        # Extract weaknesses
        for weakness in root.xpath('//cwe:Weakness', namespaces=ns):
            cwe_id = weakness.get('ID')
            if not cwe_id:
                continue

            # Normalize _key
            _key = normalize_cwe_id(f"CWE-{cwe_id}")

            # Extract basic fields
            name = weakness.get('Name', '')
            abstraction = weakness.get('Abstraction', '')
            status = weakness.get('Status', '')

            # Description
            description_elem = weakness.find('cwe:Description', namespaces=ns)
            description = description_elem.text if description_elem is not None else ''

            # Extended description
            extended_desc_elem = weakness.find('cwe:Extended_Description', namespaces=ns)
            extended_description = ''
            if extended_desc_elem is not None:
                # Concatenate all text from child elements
                extended_description = ' '.join(extended_desc_elem.itertext()).strip()

            # Likelihood of exploit
            likelihood_elem = weakness.find('cwe:Likelihood_Of_Exploit', namespaces=ns)
            likelihood = likelihood_elem.text if likelihood_elem is not None and likelihood_elem.text else None

            # Common consequences
            consequences = []
            for consequence in weakness.findall('cwe:Common_Consequences/cwe:Consequence', namespaces=ns):
                scope_elems = consequence.findall('cwe:Scope', namespaces=ns)
                impact_elems = consequence.findall('cwe:Impact', namespaces=ns)
                note_elem = consequence.find('cwe:Note', namespaces=ns)

                note_text = None
                if note_elem is not None:
                    # Get all text, handle complex content
                    note_text = ''.join(note_elem.itertext()).strip()
                    note_text = note_text if note_text else None

                consequences.append({
                    'scopes': [s.text for s in scope_elems if s.text],
                    'impacts': [i.text for i in impact_elems if i.text],
                    'note': note_text,
                })

            # Detection methods
            detection_methods = []
            for method in weakness.findall('cwe:Detection_Methods/cwe:Detection_Method', namespaces=ns):
                method_elem = method.find('cwe:Method', namespaces=ns)
                effectiveness_elem = method.find('cwe:Effectiveness', namespaces=ns)
                desc_elem = method.find('cwe:Description', namespaces=ns)

                detection_methods.append({
                    'method': method_elem.text if method_elem is not None and method_elem.text else None,
                    'effectiveness': effectiveness_elem.text if effectiveness_elem is not None and effectiveness_elem.text else None,
                    'description': desc_elem.text if desc_elem is not None and desc_elem.text else None,
                })

            # Mitigations
            mitigations = []
            for mitigation in weakness.findall('cwe:Potential_Mitigations/cwe:Mitigation', namespaces=ns):
                phase_elems = mitigation.findall('cwe:Phase', namespaces=ns)
                strategy_elem = mitigation.find('cwe:Strategy', namespaces=ns)
                mitigation_desc_elem = mitigation.find('cwe:Description', namespaces=ns)

                mitigation_dict = {
                    'phases': [p.text for p in phase_elems if p.text],
                    'strategy': strategy_elem.text if strategy_elem is not None and strategy_elem.text else None,
                    'description': None,
                }

                # Handle description specially - might have complex content
                if mitigation_desc_elem is not None:
                    # Get all text content, not just direct text
                    desc_text = ''.join(mitigation_desc_elem.itertext()).strip()
                    mitigation_dict['description'] = desc_text if desc_text else None

                mitigations.append(mitigation_dict)

            # Yield CWE document
            yield {
                '_key': _key,
                'cwe_id': f"CWE-{cwe_id}",
                'name': name,
                'abstraction': abstraction,
                'status': status,
                'description': description,
                'extended_description': extended_description,
                'likelihood_of_exploit': likelihood,
                'common_consequences': consequences,
                'detection_methods': detection_methods,
                'mitigations': mitigations,
            }

            # Yield relationship edges
            # Related weaknesses (child_of, peer_of, can_precede, requires, etc.)
            for related in weakness.findall('cwe:Related_Weaknesses/cwe:Related_Weakness', namespaces=ns):
                nature = related.get('Nature')
                related_id = related.get('CWE_ID')

                if not nature or not related_id:
                    continue

                related_key = normalize_cwe_id(f"CWE-{related_id}")

                # Map nature to edge collection
                edge_collection_map = {
                    'ChildOf': 'child_of',
                    'PeerOf': 'peer_of',
                    'CanPrecede': 'can_precede',
                    'Requires': 'requires',
                }

                edge_collection = edge_collection_map.get(nature)
                if not edge_collection:
                    # Skip unsupported relationships
                    continue

                yield {
                    '_collection': edge_collection,
                    '_from': f'weaknesses/{_key}',
                    '_to': f'weaknesses/{related_key}',
                    'nature': nature,
                    'source': 'cwe',
                }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load CWE data into database.

        Overrides base class to handle multiple collections (nodes + edges).

        Args:
            records: Generator from transform_data()
            collection_name: Ignored (determined by record type)
            on_duplicate: Action on duplicate _key

        Returns:
            dict: Combined statistics for all collections
        """
        # Separate documents from edges
        documents = []
        edges_by_collection = {
            'child_of': [],
            'peer_of': [],
            'can_precede': [],
            'requires': [],
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
        self.logger.info("Loading CWE weaknesses", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='weaknesses',
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
            'weaknesses': doc_stats,
            'edges': total_edge_stats,
            'total_created': doc_stats['created'] + total_edge_stats['created'],
            'total_updated': doc_stats['updated'] + total_edge_stats['updated'],
            'total_errors': doc_stats['errors'] + total_edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'weaknesses'
