"""
SCF (Secure Controls Framework) ingestion agent.

Fetches SCF controls and populates the controls collection with mappings to other frameworks.
SCF provides a comprehensive cybersecurity framework with mappings to NIST, ISO, PCI-DSS, etc.

Data source: https://securecontrolsframework.com/scf-download/
Format: Excel (.xlsx)
Version: 2025.4 (latest as of March 2026)

The agent automatically downloads the SCF Excel file if not present locally.

Collections populated:
- scf_controls (document collection) - ~1,200-1,300 controls across 33 domains
- cross_framework_mapping (edges to OSCAL controls, etc.)
"""

from typing import Generator
from pathlib import Path
import pandas as pd
import requests
import structlog

from .base import BaseIngestionAgent
from ..utils.keys import normalize_key
from ..utils.http_client import create_http_client

logger = structlog.get_logger()


class SCFAgent(BaseIngestionAgent):
    """
    Agent for ingesting SCF (Secure Controls Framework) data from Excel file.

    SCF provides ~1,200-1,300 cybersecurity controls organized into 33 domains,
    with mappings to 100+ frameworks (NIST, ISO, CIS, SOC 2, PCI-DSS, etc.).

    Automatically downloads SCF Excel file if not present locally.
    """

    # Direct download URLs from GitHub releases
    # These are verified working URLs from the official SCF repository
    SCF_DOWNLOAD_URLS = [
        # 2025.4 (latest - ~5.3 MB)
        "https://github.com/securecontrolsframework/securecontrolsframework/releases/download/2025.4/secure-controls-framework-scf-2025-4.xlsx",
        # 2025.3.1
        "https://github.com/securecontrolsframework/securecontrolsframework/releases/download/2025.3/secure-controls-framework-scf-2025-3-1.xlsx",
        # 2025.2.2
        "https://github.com/securecontrolsframework/securecontrolsframework/releases/download/2025.2.2/Secure.Controls.Framework.SCF.-.2025.2.2.xlsx",
        # 2025.2.1
        "https://github.com/securecontrolsframework/securecontrolsframework/releases/download/2025.2.1/secure-controls-framework-scf-2025-2-1.xlsx",
        # 2025.2
        "https://github.com/securecontrolsframework/securecontrolsframework/releases/download/2025.2/secure-controls-framework-scf-2025-2.xlsx",
    ]

    def __init__(self, db, scf_file_path: str = None, auto_download: bool = True):
        """
        Initialize SCF agent.

        Args:
            db: ArangoDB database instance
            scf_file_path: Path to SCF Excel file (default: data/scf/scf_2025.xlsx)
            auto_download: Automatically download SCF file if not present (default: True)
        """
        super().__init__(db)

        # Default path for SCF Excel file
        if scf_file_path is None:
            project_root = Path(__file__).parent.parent.parent.parent
            scf_file_path = project_root / "data" / "scf" / "scf_2025.xlsx"

        self.scf_file_path = Path(scf_file_path)
        self.auto_download = auto_download

        # Create HTTP client for downloads
        self.client = create_http_client(
            service_name="scf",
            calls_per_period=10,
            period_seconds=60,
            timeout=300.0,  # 5 minutes for large file downloads
        )

        self.logger.info(
            "SCF agent initialized",
            scf_file_path=str(self.scf_file_path),
            auto_download=auto_download
        )

    def _download_scf_file(self) -> bool:
        """
        Attempt to download SCF Excel file from known URLs.

        Returns:
            bool: True if download successful, False otherwise
        """
        self.logger.info("Attempting to download SCF Excel file...")

        # Ensure directory exists
        self.scf_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Try each download URL
        for url in self.SCF_DOWNLOAD_URLS:
            try:
                self.logger.info(f"Trying download URL: {url}")

                response = self.client.get(url, timeout=300)

                if response.status_code == 200:
                    # Check if response is actually an Excel file
                    content_type = response.headers.get('content-type', '')

                    if 'spreadsheet' in content_type or 'excel' in content_type or response.content.startswith(b'PK'):
                        # Save file
                        with open(self.scf_file_path, 'wb') as f:
                            f.write(response.content)

                        file_size = len(response.content) / (1024 * 1024)  # MB
                        self.logger.info(
                            "SCF file downloaded successfully",
                            url=url,
                            size_mb=f"{file_size:.2f}",
                            path=str(self.scf_file_path)
                        )
                        return True
                    else:
                        self.logger.debug(
                            "URL returned non-Excel content",
                            url=url,
                            content_type=content_type
                        )

            except Exception as e:
                self.logger.debug(
                    "Failed to download from URL",
                    url=url,
                    error=str(e)
                )
                continue

        # All URLs failed
        self.logger.warning("Could not download SCF file from any known URL")
        return False

    def fetch_data(self) -> pd.DataFrame:
        """
        Read SCF Excel file (downloads if not present).

        Returns:
            pd.DataFrame: SCF controls data

        Raises:
            FileNotFoundError: If SCF Excel file not found and download fails
        """
        # Check if file exists
        if not self.scf_file_path.exists():
            if self.auto_download:
                self.logger.info("SCF file not found locally, attempting download...")

                # Try to download
                if not self._download_scf_file():
                    # Download failed - raise error without manual fallback
                    error_msg = (
                        f"Failed to automatically download SCF Excel file from all known URLs. "
                        f"Tried {len(self.SCF_DOWNLOAD_URLS)} different sources. "
                        f"Expected file location: {self.scf_file_path}"
                    )
                    self.logger.error("SCF file download failed", path=str(self.scf_file_path))
                    raise FileNotFoundError(error_msg)
            else:
                # Auto-download disabled
                error_msg = (
                    f"SCF Excel file not found at: {self.scf_file_path}. "
                    f"Auto-download is disabled. Enable with: SCFAgent(db, auto_download=True)"
                )
                self.logger.error("SCF file not found", path=str(self.scf_file_path))
                raise FileNotFoundError(error_msg)

        self.logger.info("Reading SCF Excel file", path=str(self.scf_file_path))

        # Read Excel file
        # SCF has multiple sheets, we want the main controls sheet
        # Common patterns: "SCF 2025.4", "SCF 2024.2", "SCF Controls", etc.
        try:
            # Get all sheet names
            xl_file = pd.ExcelFile(self.scf_file_path)
            sheet_names = xl_file.sheet_names

            # Try to find the main controls sheet (contains version number or "Controls")
            controls_sheet = None
            for sheet_name in sheet_names:
                sheet_lower = sheet_name.lower()
                if any(pattern in sheet_lower for pattern in ["scf 20", "scf controls", "controls", "master", "control catalog"]):
                    # Prefer sheets with version numbers (more specific)
                    if any(year in sheet_name for year in ["2025", "2024", "2023"]):
                        controls_sheet = sheet_name
                        break
                    elif not controls_sheet:
                        controls_sheet = sheet_name

            if controls_sheet:
                df = pd.read_excel(self.scf_file_path, sheet_name=controls_sheet)
                self.logger.info(
                    "Loaded SCF controls sheet",
                    sheet_name=controls_sheet,
                    rows=len(df),
                    columns=len(df.columns)
                )
            else:
                # Fallback to first sheet
                df = pd.read_excel(self.scf_file_path, sheet_name=0)
                self.logger.warning("Using first sheet (no controls sheet found)", sheet_name=sheet_names[0])

            self.logger.info("SCF data loaded", controls=len(df))
            return df

        except Exception as e:
            self.logger.error("Failed to read SCF Excel file", error=str(e))
            raise

    def transform_data(self, df: pd.DataFrame) -> Generator[dict, None, None]:
        """
        Transform SCF DataFrame to graph documents and edges.

        Args:
            df: SCF controls DataFrame from fetch_data()

        Yields:
            dict: Documents for scf_controls collection and cross_framework_mapping edges
        """
        self.logger.info("Transforming SCF data", total_rows=len(df))

        # Track statistics
        controls_count = 0
        mapping_count = 0

        # Normalize column names (handle variations and multi-line headers)
        # Replace newlines and excess whitespace
        df.columns = df.columns.str.replace('\n', ' ', regex=False).str.strip().str.lower()

        # Common column name variations (based on actual SCF file structure)
        # Note: Order matters! More specific matches should come first
        column_mapping = {
            'scf_id': ['scf #', 'scf id', 'scf_id', 'control id', 'id', 'control_id'],
            'domain': ['scf domain', 'domain', 'control domain', 'category'],
            'title': ['scf control', 'title', 'control title', 'name', 'control name'],
            'description': [
                'secure controls framework (scf) control description',
                'description',
                'control description',
                'objective',
                'control objective'
            ],
            'control_question': ['scf control question', 'control question', 'question'],
            'evidence_request': ['evidence request list (erl) #', 'evidence request', 'evidence_request', 'erl #', 'evidence'],
            'conformity_cadence': ['conformity validation cadence', 'validation cadence', 'cadence'],
            'control_weighting': ['relative control weighting', 'control weighting', 'weighting'],
            'pptdf_applicability': ['pptdf applicability', 'applicability'],
            'function': ['nist csf function grouping', 'function', 'control function', 'csf function', 'nist function'],
        }

        # Find actual column names (partial matching for flexibility)
        actual_columns = {}
        for standard_name, variations in column_mapping.items():
            for col in df.columns:
                for variation in variations:
                    if variation.lower() in col or col in variation.lower():
                        actual_columns[standard_name] = col
                        break
                if standard_name in actual_columns:
                    break

        self.logger.info("Detected SCF columns", columns=list(actual_columns.keys()))

        # Process each control
        for idx, row in df.iterrows():
            try:
                # Extract SCF ID (required)
                scf_id_col = actual_columns.get('scf_id')
                if not scf_id_col:
                    self.logger.warning("No SCF ID column found, skipping row", row_index=idx)
                    continue

                scf_id = row.get(scf_id_col)
                if pd.isna(scf_id) or not scf_id:
                    continue  # Skip rows without control ID

                scf_id = str(scf_id).strip()
                _key = normalize_key(scf_id, "scf")

                # Extract domain and domain code
                domain = row.get(actual_columns.get('domain')) if 'domain' in actual_columns else None
                if not pd.isna(domain):
                    domain = str(domain).strip()
                else:
                    domain = None

                # Domain code is typically first part of SCF ID (e.g., "ACC" from "SCF-ACC-01")
                domain_code = None
                if scf_id.startswith("SCF-"):
                    parts = scf_id.split("-")
                    if len(parts) >= 2:
                        domain_code = parts[1]

                # Extract other fields
                title = row.get(actual_columns.get('title')) if 'title' in actual_columns else None
                if not pd.isna(title):
                    title = str(title).strip()
                else:
                    title = None

                description = row.get(actual_columns.get('description')) if 'description' in actual_columns else None
                if not pd.isna(description):
                    description = str(description).strip()
                else:
                    description = None

                assessment_objective = row.get(actual_columns.get('assessment_objective')) if 'assessment_objective' in actual_columns else None
                if not pd.isna(assessment_objective):
                    assessment_objective = str(assessment_objective).strip()
                else:
                    assessment_objective = None

                # Extract optional fields
                control_question = row.get(actual_columns.get('control_question')) if 'control_question' in actual_columns else None
                if not pd.isna(control_question):
                    control_question = str(control_question).strip()
                else:
                    control_question = None

                evidence_request = row.get(actual_columns.get('evidence_request')) if 'evidence_request' in actual_columns else None
                if not pd.isna(evidence_request):
                    evidence_request = str(evidence_request).strip()
                else:
                    evidence_request = None

                conformity_cadence = row.get(actual_columns.get('conformity_cadence')) if 'conformity_cadence' in actual_columns else None
                if not pd.isna(conformity_cadence):
                    conformity_cadence = str(conformity_cadence).strip()
                else:
                    conformity_cadence = None

                control_weighting = row.get(actual_columns.get('control_weighting')) if 'control_weighting' in actual_columns else None
                if not pd.isna(control_weighting):
                    try:
                        control_weighting = int(control_weighting)
                    except (ValueError, TypeError):
                        control_weighting = None
                else:
                    control_weighting = None

                pptdf_applicability = row.get(actual_columns.get('pptdf_applicability')) if 'pptdf_applicability' in actual_columns else None
                if not pd.isna(pptdf_applicability):
                    pptdf_applicability = str(pptdf_applicability).strip()
                else:
                    pptdf_applicability = None

                function = row.get(actual_columns.get('function')) if 'function' in actual_columns else None
                if not pd.isna(function):
                    function = str(function).strip()
                else:
                    function = None

                # Yield control document
                control_doc = {
                    '_collection': 'scf_controls',
                    '_key': _key,
                    'scf_id': scf_id,
                    'domain': domain,
                    'domain_code': domain_code,
                    'title': title,
                    'description': description,
                    'control_question': control_question,
                    'assessment_objective': assessment_objective,
                    'evidence_request': evidence_request,
                    'conformity_cadence': conformity_cadence,
                    'control_weighting': control_weighting,
                    'pptdf_applicability': pptdf_applicability,
                    'function': function,
                    'version': '2025',  # Update this based on file version
                }

                # Remove None values
                control_doc = {k: v for k, v in control_doc.items() if v is not None}

                yield control_doc
                controls_count += 1

                # Parse framework mappings (NIST, ISO, CIS, etc.)
                # Look for NIST mapping columns
                nist_columns = [col for col in df.columns if 'nist' in col.lower() and '800-53' in col.lower()]
                for nist_col in nist_columns:
                    nist_value = row.get(nist_col)
                    if pd.isna(nist_value) or not nist_value:
                        continue

                    # NIST controls can be comma-separated OR newline-separated
                    nist_controls_raw = str(nist_value).replace('\n', ',').split(',')
                    for nist_control in nist_controls_raw:
                        nist_control = nist_control.strip()
                        if not nist_control or nist_control in ['N/A', 'n/a', '-', '']:
                            continue

                        # Normalize NIST control ID to match oscal_controls format
                        # E.g., "PM-1" → "pm-1", "AC-2(1)" → "ac-2_1"
                        nist_key = nist_control.lower().replace('.', '_').replace('(', '_').replace(')', '')

                        # Create cross-framework mapping edge
                        yield {
                            '_collection': 'cross_framework_mapping',
                            '_from': f'scf_controls/{_key}',
                            '_to': f'oscal_controls/{nist_key}',  # NIST controls stored in oscal_controls
                            'source_framework': 'SCF',
                            'target_framework': 'NIST SP 800-53',
                            'mapping_type': 'related',
                            'source': 'scf',
                        }
                        mapping_count += 1

            except Exception as e:
                self.logger.warning(
                    "Failed to process SCF control",
                    row_index=idx,
                    error=str(e)
                )
                continue

        self.logger.info(
            "SCF transformation complete",
            controls=controls_count,
            framework_mappings=mapping_count
        )

    def load_data(self, records: Generator[dict, None, None], collection_name: str = None, on_duplicate: str = "update") -> dict:
        """
        Load SCF data into database.

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
            collection_name = record.get('_collection')

            # Check if it's an edge (has _from and _to) or edge collection
            if '_from' in record and '_to' in record:
                # It's an edge
                if '_collection' in record:
                    record.pop('_collection')
                edges.append(record)
            elif collection_name == 'scf_controls':
                # It's a control document
                record.pop('_collection', None)
                documents.append(record)
            else:
                # Default: treat as document
                record.pop('_collection', None)
                documents.append(record)

        # Load documents
        self.logger.info("Loading SCF controls", count=len(documents))
        doc_stats = super().load_data(
            iter(documents),
            collection_name='scf_controls',
            on_duplicate=on_duplicate,
        )

        # Load edges
        edge_stats = {'created': 0, 'updated': 0, 'errors': 0, 'total': 0}

        if edges:
            self.logger.info("Loading cross_framework_mapping edges", count=len(edges))
            edge_stats = super().load_data(
                iter(edges),
                collection_name='cross_framework_mapping',
                on_duplicate=on_duplicate,
            )

        # Combine statistics
        combined_stats = {
            'scf_controls': doc_stats,
            'edges': edge_stats,
            'total_created': doc_stats['created'] + edge_stats['created'],
            'total_updated': doc_stats['updated'] + edge_stats['updated'],
            'total_errors': doc_stats['errors'] + edge_stats['errors'],
        }

        return combined_stats

    def _get_primary_collection(self) -> str:
        """Get primary collection name."""
        return 'scf_controls'
