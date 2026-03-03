"""
Scan ingestion service.

Handles scan result ingestion from multiple formats:
- SARIF (SAST/DAST tools)
- CycloneDX (SCA/SBOM tools)
- Future: OSV, VEX, CSAF

SOLID Principles Applied:
- SRP: Business logic only, no parsing (delegates to parsers)
- DIP: Depends on IScanParser abstraction via ParserFactory
- OCP: Adding new scan formats requires no changes to this service
"""

from typing import Dict, Any
import structlog

from api.services.base import BaseGraphService
from api.parsers.factory import ParserFactory
from api.repositories.scan import ScanSessionRepository, ScanFindingRepository
from api.repositories.component import ComponentRepository
from api.models.requests.scan import ScanIngestRequest

logger = structlog.get_logger()


class ScanIngestionService(BaseGraphService):
    """
    Scan ingestion service (SRP: business logic only, no parsing).

    Delegates parsing to parser classes (DIP: depends on IScanParser abstraction).

    Flow:
    1. Get appropriate parser via factory (OCP)
    2. Parse payload (delegation to parser)
    3. Create scan_session document
    4. Normalize and store findings
    5. Extract and store components (SBOM)
    6. Create edges (finding → CVE, component → finding)
    """

    async def ingest_scan(
        self,
        customer_id: str,
        scan_request: ScanIngestRequest,
    ):
        """
        Ingest scan results with model validation.

        Args:
            customer_id: Customer identifier (from authentication)
            scan_request: Scan ingestion request

        Returns:
            ScanSession: Validated scan session model with final status and counts

        Raises:
            ValueError: If scan format is unsupported or parsing fails
            Exception: On database or processing errors
        """
        self.logger.info(
            "Starting scan ingestion",
            customer_id=customer_id,
            format=scan_request.format,
            scan_type=scan_request.scan_type,
        )

        # Step 1: Get parser (OCP - factory handles format selection)
        try:
            parser = ParserFactory.get_parser(scan_request.format)
        except ValueError as e:
            self.logger.error(
                "Unsupported scan format",
                format=scan_request.format,
                error=str(e),
            )
            raise

        # Step 2: Parse payload (SRP - parser handles format-specific logic)
        try:
            parsed_data = parser.parse(scan_request.payload)
            self.logger.debug(
                "Scan payload parsed",
                tool_name=parsed_data.tool_name,
                findings_count=len(parsed_data.findings),
                components_count=len(parsed_data.components),
            )
        except Exception as e:
            self.logger.error(
                "Scan parsing failed",
                format=scan_request.format,
                error=str(e),
            )
            raise ValueError(f"Failed to parse scan payload: {str(e)}")

        # Get customer database for persistence
        from api.core.database import get_customer_db
        customer_db = get_customer_db(customer_id)

        # Initialize repositories
        session_repo = ScanSessionRepository(customer_db)
        finding_repo = ScanFindingRepository(customer_db)
        component_repo = ComponentRepository(customer_db)

        # Step 3: Create scan session (returns ScanSession model)
        scan_session = session_repo.create_session(
            customer_id=customer_id,
            tool_name=parsed_data.tool_name,
            tool_version=parsed_data.tool_version,
            scan_timestamp=parsed_data.scan_timestamp,
            scan_type=scan_request.scan_type,
            metadata={
                **scan_request.metadata,
                **parsed_data.metadata,
            },
        )

        scan_session_id = scan_session._key  # Use model attribute

        self.logger.info(
            "Scan session created",
            scan_session_id=scan_session_id,
            customer_id=customer_id,
        )

        # Step 4: Store findings
        findings_created = []
        if parsed_data.findings:
            findings_created = await self._store_findings(
                customer_id=customer_id,
                scan_session_id=scan_session_id,
                findings=parsed_data.findings,
                finding_repo=finding_repo,
            )

        # Step 5: Store components (SBOM)
        components_created = []
        if parsed_data.components:
            components_created = await self._store_components(
                customer_id=customer_id,
                scan_session_id=scan_session_id,
                components=parsed_data.components,
                component_repo=component_repo,
            )

        # Step 6: Create edges (finding → CVE, component → finding)
        await self._create_edges(
            customer_db=customer_db,
            scan_session_id=scan_session_id,
            findings=findings_created,
            components=components_created,
        )

        # Step 7: Update scan session status (returns ScanSession model)
        updated_session = session_repo.update_session_status(
            session_key=scan_session_id,
            status="completed",
            findings_count=len(findings_created),
            components_count=len(components_created),
        )

        self.logger.info(
            "Scan ingestion completed",
            scan_session_id=scan_session_id,
            findings_count=len(findings_created),
            components_count=len(components_created),
        )

        # Return ScanSession model (FastAPI will auto-serialize to JSON)
        return updated_session

    async def _store_findings(
        self,
        customer_id: str,
        scan_session_id: str,
        findings: list,
        finding_repo: ScanFindingRepository,
    ):
        """
        Store scan findings with ParsedFinding → ScanFinding mapping.

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session _key
            findings: List of ParsedFinding objects (parser output models)
            finding_repo: Finding repository

        Returns:
            List[ScanFinding]: Created finding model instances
        """
        if not findings:
            return []

        findings_created = []

        # Map ParsedFinding → ScanFinding via repository
        for parsed_finding in findings:
            # Repository creates ScanFinding model (validates and normalizes)
            finding = finding_repo.create_finding(
                customer_id=customer_id,
                scan_session_id=scan_session_id,
                cve_id=parsed_finding.cve_id,  # May be None for non-CVE findings
                severity=parsed_finding.severity,  # Will be normalized to uppercase
                description=parsed_finding.description,
                location=parsed_finding.location,
                tool_name=parsed_finding.tool_name,
                raw_data=parsed_finding.raw_data,
            )
            findings_created.append(finding)

        self.logger.debug(
            "Findings stored",
            findings_count=len(findings_created),
        )

        return findings_created

    async def _store_components(
        self,
        customer_id: str,
        scan_session_id: str,
        components: list,
        component_repo: ComponentRepository,
    ) -> list:
        """
        Store SBOM components in database.

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session _key
            components: List of component dicts from parser
            component_repo: Component repository

        Returns:
            list: Created component documents
        """
        if not components:
            return []

        # Normalize components
        component_dicts = []
        for component in components:
            component_dict = {
                "customer_id": customer_id,
                "purl": component.get("purl", ""),
                "name": component.get("name", ""),
                "version": component.get("version", ""),
                "type": component.get("type", "library"),
                "metadata": {
                    "scan_session_id": scan_session_id,
                    **component,
                },
            }
            component_dicts.append(component_dict)

        # Bulk insert for performance
        try:
            components_created = component_repo.bulk_create_components(component_dicts)
            self.logger.debug(
                "Components stored",
                components_count=len(components_created),
            )
            return components_created

        except Exception as e:
            self.logger.error(
                "Failed to store components",
                error=str(e),
            )
            raise

    async def _create_edges(
        self,
        customer_db,
        scan_session_id: str,
        findings: list,
        components: list,
    ) -> None:
        """
        Create graph edges.

        Creates:
        - finding_to_cve: scan_finding → vulnerability (reference DB)
        - component_to_finding: customer_component → scan_finding

        Args:
            customer_db: Customer database instance
            scan_session_id: Scan session _key
            findings: Created finding documents
            components: Created component documents
        """
        # Create finding → CVE edges
        if findings:
            await self._create_finding_to_cve_edges(
                customer_db=customer_db,
                findings=findings,
            )

        # Create component → finding edges
        if components and findings:
            await self._create_component_to_finding_edges(
                customer_db=customer_db,
                components=components,
                findings=findings,
            )

    async def _create_finding_to_cve_edges(
        self,
        customer_db,
        findings: list,
    ) -> None:
        """
        Create edges from scan findings to CVE records.

        Args:
            customer_db: Customer database instance
            findings: Finding documents
        """
        edge_collection = customer_db.collection("finding_to_cve")

        edges_created = 0
        for finding in findings:
            if not finding.get("cve_id"):
                continue  # Skip findings without CVE ID

            # CVE records are in reference database
            # Edge format: customer_db/finding → reference_db/vulnerability
            edge = {
                "_from": finding["_id"],
                "_to": f"vulnerabilities/{finding['cve_id'].lower().replace('-', '_')}",
                "created_at": finding.get("created_at"),
            }

            try:
                edge_collection.insert(edge, overwrite_mode="ignore")
                edges_created += 1
            except Exception as e:
                self.logger.warning(
                    "Failed to create finding→CVE edge",
                    finding_id=finding.get("_key"),
                    cve_id=finding.get("cve_id"),
                    error=str(e),
                )

        self.logger.debug(
            "Created finding→CVE edges",
            edges_count=edges_created,
        )

    async def _create_component_to_finding_edges(
        self,
        customer_db,
        components: list,
        findings: list,
    ) -> None:
        """
        Create edges from components to findings.

        Matches components to findings based on location (PURL or name@version).

        Args:
            customer_db: Customer database instance
            components: Component documents
            findings: Finding documents
        """
        edge_collection = customer_db.collection("component_to_finding")

        # Build component lookup map
        component_map = {}
        for component in components:
            purl = component.get("purl", "")
            name = component.get("name", "")
            version = component.get("version", "")

            if purl:
                component_map[purl] = component
            if name and version:
                component_map[f"{name}@{version}"] = component

        edges_created = 0
        for finding in findings:
            location = finding.get("location", "")

            # Try to match finding location to component
            component = None
            if location in component_map:
                component = component_map[location]
            else:
                # Try partial match (finding location may be pkg:npm/foo@1.0.0)
                for key, comp in component_map.items():
                    if key in location or location in key:
                        component = comp
                        break

            if component:
                edge = {
                    "_from": component["_id"],
                    "_to": finding["_id"],
                    "created_at": finding.get("created_at"),
                }

                try:
                    edge_collection.insert(edge, overwrite_mode="ignore")
                    edges_created += 1
                except Exception as e:
                    self.logger.warning(
                        "Failed to create component→finding edge",
                        component_id=component.get("_key"),
                        finding_id=finding.get("_key"),
                        error=str(e),
                    )

        self.logger.debug(
            "Created component→finding edges",
            edges_count=edges_created,
        )
