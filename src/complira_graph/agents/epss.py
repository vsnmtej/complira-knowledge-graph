"""
EPSS (Exploit Prediction Scoring System) ingestion agent.

Fetches EPSS scores from FIRST.org and populates time-series data.
EPSS provides probability scores (0-1) for CVE exploitation likelihood.

Data source: https://epss.empiricalsecurity.com/epss_scores-current.csv.gz
Collections populated:
- epss_history (document collection with time-series scores)
- has_epss (edges from vulnerabilities to current EPSS score)
"""

from typing import Generator
from datetime import datetime
import gzip
import csv
import io
import structlog

from .base import BaseIngestionAgent
from ..utils.http_client import create_http_client
from ..utils.keys import normalize_cve_id

logger = structlog.get_logger()


class EPSSAgent(BaseIngestionAgent):
    """
    Agent for ingesting EPSS (Exploit Prediction Scoring System) data.

    EPSS provides machine learning-based probability scores for CVE exploitation.
    """

    EPSS_CSV_URL = "https://epss.empiricalsecurity.com/epss_scores-current.csv.gz"

    def __init__(self, db):
        """Initialize EPSS agent."""
        super().__init__(db)
        self.client = create_http_client(
            service_name="epss_first",
            calls_per_period=10,
            period_seconds=60,
            circuit_breaker=False,
            timeout=120.0,  # Large gzipped CSV file
        )

    def fetch_data(self) -> bytes:
        """
        Fetch EPSS scores CSV from FIRST.org.

        Returns:
            bytes: Gzipped CSV data

        Raises:
            Exception: On fetch failure
        """
        self.logger.info("Fetching EPSS scores from FIRST.org", url=self.EPSS_CSV_URL)

        response = self.client.get(self.EPSS_CSV_URL)
        gz_data = response.content

        self.logger.info(
            "Fetched EPSS scores",
            compressed_size_bytes=len(gz_data),
        )

        return gz_data

    def transform_data(self, raw_data: bytes) -> Generator[dict, None, None]:
        """
        Transform EPSS CSV to graph nodes and edges.

        Args:
            raw_data: Gzipped CSV data from fetch_data()

        Yields:
            dict: EPSS score documents and edges

        CSV Format:
            cve,epss,percentile
            CVE-2023-1234,0.12345,0.67890
        """
        # Decompress gzipped CSV
        with gzip.GzipFile(fileobj=io.BytesIO(raw_data)) as gz:
            csv_data = gz.read().decode('utf-8')

        # Skip comment lines (lines starting with #)
        lines = csv_data.split('\n')
        csv_lines = [line for line in lines if not line.startswith('#')]
        clean_csv = '\n'.join(csv_lines)

        # Parse CSV
        reader = csv.DictReader(io.StringIO(clean_csv))

        # Get current date for time-series tracking
        score_date = datetime.utcnow().date().isoformat()

        for row in reader:
            cve_id = row.get('cve', '').strip()
            if not cve_id or not cve_id.startswith('CVE-'):
                continue

            # Parse EPSS score and percentile
            try:
                epss_score = float(row.get('epss', 0))
                percentile = float(row.get('percentile', 0))
            except (ValueError, TypeError):
                self.logger.warning(
                    "Invalid EPSS score data",
                    cve_id=cve_id,
                    epss=row.get('epss'),
                    percentile=row.get('percentile'),
                )
                continue

            cve_key = normalize_cve_id(cve_id)

            # Create unique key for time-series record
            # Format: CVE_2023_1234_2024_02_28
            _key = f"{cve_key}_{score_date.replace('-', '_')}"

            # Yield EPSS history document (time-series)
            yield {
                '_key': _key,
                'cve_id': cve_id,
                'cve_key': cve_key,
                'epss_score': epss_score,
                'percentile': percentile,
                'score_date': score_date,
                'source': 'epss',
            }

            # Yield edge from vulnerability to EPSS score
            yield {
                '_collection': 'has_epss',
                '_from': f'vulnerabilities/{cve_key}',
                '_to': f'epss_history/{_key}',
                'score_date': score_date,
                'source': 'epss',
            }

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load EPSS data into database.

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
        self.logger.info("Loading EPSS history records", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='epss_history',
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        if edges:
            self.logger.info("Loading has_epss edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name='has_epss',
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            'epss_history': doc_stats,
            'edges': edge_stats,
            'total_created': doc_stats['created'] + edge_stats['created'],
            'total_updated': doc_stats['updated'] + edge_stats['updated'],
            'total_errors': doc_stats['errors'] + edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'epss_history'
