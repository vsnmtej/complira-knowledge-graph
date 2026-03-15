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
        from api.repositories.scan import ScanEdgeRepository

        # Use repository to create edges
        edge_repo = ScanEdgeRepository(customer_db, "finding_to_cve")
        edges_created = edge_repo.create_finding_to_cve_edges(findings)

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
        from api.repositories.scan import ScanEdgeRepository

        # Use repository to create edges
        edge_repo = ScanEdgeRepository(customer_db, "component_to_finding")
        edges_created = edge_repo.create_component_to_finding_edges(components, findings)

        self.logger.debug(
            "Created component→finding edges",
            edges_count=edges_created,
        )

    async def generate_vex(
        self,
        customer_id: str,
        scan_session_id: str,
    ) -> dict:
        """
        Generate evidence-grounded VEX document for a scan session.

        Uses V2 evidence-based architecture:
        1. Collect graph evidence (CVE → CWE → CAPEC → ATT&CK → Controls)
        2. Generate assessments with LLM using structured evidence
        3. Export to CycloneDX VEX 1.5 format

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session ID

        Returns:
            dict: VEX generation result with:
                - scan_session_id: Session identifier
                - vex_document: CycloneDX VEX document (JSON)
                - vulnerabilities_assessed: Number of vulnerabilities analyzed
                - generated_at: ISO 8601 timestamp

        Raises:
            ValueError: If scan session not found or no findings with CVEs
        """
        from datetime import datetime
        from api.services.vex_evidence import VEXEvidenceService
        from complira_graph.llm_agents.vex_synthesizer_v2 import (
            VEXSynthesizerV2,
            export_cyclonedx_multi,
        )
        from anthropic import Anthropic

        self.logger.info(
            "Generating evidence-grounded VEX document",
            customer_id=customer_id,
            scan_session_id=scan_session_id,
        )

        # Get customer database
        from api.core.database import get_customer_db, get_reference_db
        customer_db = get_customer_db(customer_id)
        reference_db = get_reference_db()

        # Initialize repositories
        scan_repo = ScanSessionRepository(db=customer_db)
        finding_repo = ScanFindingRepository(db=customer_db)
        component_repo = ComponentRepository(db=customer_db)

        # Get scan session
        scan_session = scan_repo.get(scan_session_id)
        if not scan_session:
            raise ValueError(f"Scan session not found: {scan_session_id}")

        # Verify customer owns this session
        if scan_session.get("customer_id") != customer_id:
            raise ValueError(f"Access denied to scan session: {scan_session_id}")

        # Get findings with CVE IDs
        findings = finding_repo.list_session_findings(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            limit=1000,
            offset=0,
        )

        # Filter findings with CVE IDs
        cve_findings = [f for f in findings if f.get("cve_id")]

        if not cve_findings:
            # No vulnerabilities found - return empty VEX
            self.logger.info("No CVE findings found in scan session")
            return {
                "scan_session_id": scan_session_id,
                "vex_document": {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.5",
                    "version": 1,
                    "metadata": {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "component": {
                            "bom-ref": scan_session_id,
                            "type": "application",
                        }
                    },
                    "vulnerabilities": []
                },
                "vulnerabilities_assessed": 0,
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }

        self.logger.info(
            "Found CVE findings for VEX generation",
            findings_count=len(cve_findings),
        )

        # Initialize evidence service and synthesizer
        evidence_service = VEXEvidenceService(db=reference_db, cache=self.cache)
        anthropic_client = Anthropic(api_key=self.settings.ANTHROPIC_API_KEY)
        synthesizer = VEXSynthesizerV2(anthropic_client=anthropic_client)

        # Collect VEX assessments for each finding
        assessments = []
        for finding in cve_findings:
            cve_id = finding.get("cve_id")
            component_purl = finding.get("location", "unknown")

            try:
                # Collect evidence from graph
                evidence = await evidence_service.collect_evidence(
                    cve_id=cve_id,
                    component_purl=component_purl,
                    customer_id=customer_id,
                    include_tier2=True,
                )

                # Generate VEX assessment with LLM
                assessment = await synthesizer.synthesize_vex(
                    evidence=evidence,
                    component_purl=component_purl,
                )

                assessments.append(assessment)

                self.logger.debug(
                    "Generated VEX assessment",
                    cve_id=cve_id,
                    status=assessment.status,
                    evidence_tier1_complete=evidence.tier_1_complete,
                )

            except Exception as e:
                self.logger.error(
                    "Failed to generate VEX assessment",
                    cve_id=cve_id,
                    component_purl=component_purl,
                    error=str(e),
                )
                # Continue with next finding
                continue

        if not assessments:
            raise ValueError("Failed to generate any VEX assessments")

        # Export to CycloneDX VEX format
        vex_document = export_cyclonedx_multi(
            synthesizer=synthesizer,
            assessments=assessments,
            scan_session_id=scan_session_id,
        )

        self.logger.info(
            "Evidence-grounded VEX document generated",
            vulnerabilities_assessed=len(assessments),
        )

        return {
            "scan_session_id": scan_session_id,
            "vex_document": vex_document,
            "vulnerabilities_assessed": len(assessments),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    async def match_cpes(
        self,
        customer_id: str,
        scan_session_id: str,
    ) -> dict:
        """
        Generate CPE mappings for components in a scan session.

        Uses PURLtoCPEAgent to map Package URLs (PURLs) to CPE identifiers,
        enabling vulnerability matching via CVE→CPE relationships.

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session ID

        Returns:
            dict: CPE matching result with:
                - scan_session_id: Session identifier
                - components_processed: Number of components analyzed
                - cpe_mappings_created: Number of matched_by_cpe edges created
                - completed_at: ISO 8601 timestamp

        Raises:
            ValueError: If scan session not found or no components found
        """
        from datetime import datetime

        self.logger.info(
            "Matching CPEs for scan session",
            customer_id=customer_id,
            scan_session_id=scan_session_id,
        )

        # Get customer database
        from api.core.database import get_customer_db
        customer_db = get_customer_db(customer_id)

        # Initialize repositories
        scan_repo = ScanSessionRepository(db=customer_db)
        component_repo = ComponentRepository(db=customer_db)

        # Get scan session
        scan_session = scan_repo.get(scan_session_id)
        if not scan_session:
            raise ValueError(f"Scan session not found: {scan_session_id}")

        # Verify customer owns this session
        if scan_session.get("customer_id") != customer_id:
            raise ValueError(f"Access denied to scan session: {scan_session_id}")

        # Get components from this scan
        components = component_repo.get_by_scan_session(scan_session_id)

        if not components:
            raise ValueError("No components found in scan session")

        self.logger.info(
            "Found components for CPE matching",
            components_count=len(components),
        )

        # Use PURLtoCPEAgent to match CPEs
        from complira_graph.llm_agents.purl_to_cpe import PURLtoCPEAgent
        from anthropic import Anthropic

        # Initialize Anthropic client
        anthropic_client = Anthropic(api_key=self.settings.ANTHROPIC_API_KEY)

        # Initialize CPE agent (will work with customer_components collection)
        cpe_agent = PURLtoCPEAgent(
            db=customer_db,
            anthropic_client=anthropic_client
        )

        # Process components in batches
        cpe_mappings_created = 0
        components_processed = 0

        for component in components:
            component_key = component.get("_key")
            purl = component.get("purl")

            if not purl:
                continue

            # Check if CPE mapping already exists
            existing_mapping_query = """
            FOR v, e IN 1..1 OUTBOUND @component_id matched_by_cpe
                LIMIT 1
                RETURN 1
            """
            cursor = customer_db.aql.execute(
                existing_mapping_query,
                bind_vars={"component_id": f"customer_components/{component_key}"}
            )

            if list(cursor):
                # Mapping already exists, skip
                self.logger.debug(
                    "CPE mapping already exists",
                    component_key=component_key,
                    purl=purl,
                )
                continue

            # Create record for enrichment
            record = {
                "_key": component_key,
                "purl": purl,
                "ecosystem": component.get("type", ""),
                "name": component.get("name", ""),
                "latest_version": component.get("version", ""),
            }

            try:
                # Generate CPE mapping
                enrichment = cpe_agent.enrich(record)

                # Validate mapping
                if cpe_agent.validate(enrichment):
                    # Create CPE entry and edge manually (since agent uses 'components' collection)
                    # but we need 'customer_components' collection
                    cpe_uri = enrichment['cpe_uri']

                    # Generate CPE key
                    import hashlib
                    if len(cpe_uri) > 200:
                        cpe_key = f"cpe_{hashlib.sha256(cpe_uri.encode()).hexdigest()[:32]}"
                    else:
                        cpe_key = cpe_uri.replace(':', '_').replace('.', '_').replace('*', 'ANY')

                    # Use repositories for database operations
                    from api.repositories.scan import CPERepository, ScanEdgeRepository

                    # Create or update CPE entry
                    try:
                        cpe_repo = CPERepository(customer_db, 'cpe_entries')
                        cpe_repo.insert_cpe_entry(
                            customer_id=customer_id,
                            cpe_uri=cpe_uri,
                            purl=purl,
                            vendor=enrichment['vendor'],
                            product=enrichment['product'],
                            version=enrichment.get('version', '*'),
                            source='llm',
                        )
                    except Exception as e:
                        self.logger.error(
                            "Failed to create CPE entry",
                            cpe_uri=cpe_uri,
                            error=str(e),
                        )
                        continue

                    # Create matched_by_cpe edge
                    try:
                        edge_repo = ScanEdgeRepository(customer_db, 'matched_by_cpe')
                        provenance = {
                            'source': 'llm',
                            'model': enrichment['model'],
                            'reasoning': enrichment['reasoning'],
                            'timestamp': enrichment['timestamp'],
                        }

                        success = edge_repo.create_matched_by_cpe_edge(
                            component_key=component_key,
                            cpe_key=cpe_key,
                            customer_id=customer_id,
                            confidence=enrichment['confidence'],
                            provenance=provenance,
                        )

                        if success:
                            cpe_mappings_created += 1
                            self.logger.info(
                                "Created CPE mapping",
                                purl=purl,
                                cpe_uri=enrichment.get("cpe_uri"),
                                confidence=enrichment.get("confidence"),
                            )
                    except Exception as e:
                        self.logger.error(
                            "Failed to create matched_by_cpe edge",
                            purl=purl,
                            error=str(e),
                        )
                        continue

                    # Store provenance (optional)
                    provenance_doc = {
                        'entity_type': 'matched_by_cpe',
                        'entity_from': f'customer_components/{component_key}',
                        'entity_to': f'cpe_entries/{cpe_key}',
                        'purl': purl,
                        'cpe_uri': cpe_uri,
                        'confidence': enrichment['confidence'],
                        'reasoning': enrichment['reasoning'],
                        'model': enrichment['model'],
                        'input_tokens': enrichment['input_tokens'],
                        'output_tokens': enrichment['output_tokens'],
                        'timestamp': enrichment['timestamp'],
                    }

                    try:
                        llm_repo = CPERepository(customer_db, 'llm_enrichments')
                        llm_repo.insert_llm_enrichment(provenance_doc)
                    except Exception as e:
                        self.logger.debug(
                            "Failed to store provenance",
                            purl=purl,
                            error=str(e),
                        )

                else:
                    self.logger.warning(
                        "CPE mapping failed validation",
                        purl=purl,
                    )

            except Exception as e:
                self.logger.error(
                    "Failed to create CPE mapping",
                    purl=purl,
                    error=str(e),
                )
                # Continue with next component

            components_processed += 1

        self.logger.info(
            "CPE matching complete",
            components_processed=components_processed,
            cpe_mappings_created=cpe_mappings_created,
        )

        return {
            "scan_session_id": scan_session_id,
            "components_processed": components_processed,
            "cpe_mappings_created": cpe_mappings_created,
            "completed_at": datetime.utcnow().isoformat() + "Z",
        }

    # ========== Read Operations (Repository Delegation) ==========

    async def get_session(self, session_id: str, customer_id: str) -> Dict[str, Any] | None:
        """
        Get a scan session by ID.

        Args:
            session_id: Scan session identifier
            customer_id: Customer ID (for access control)

        Returns:
            dict: Scan session document or None if not found/unauthorized
        """
        session_repo = ScanSessionRepository(self.db)
        session = session_repo.get(session_id)

        if not session:
            return None

        # Verify customer owns this session
        if session.get("customer_id") != customer_id:
            return None

        return session

    async def list_session_findings(
        self,
        session_id: str,
        customer_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Dict[str, Any]]:
        """
        List findings for a scan session.

        Args:
            session_id: Scan session identifier
            customer_id: Customer ID (for access control)
            limit: Maximum findings to return
            offset: Number of findings to skip

        Returns:
            list: Scan findings
        """
        # Verify session exists and customer owns it
        session = await self.get_session(session_id, customer_id)
        if not session:
            return []

        finding_repo = ScanFindingRepository(self.db)
        return finding_repo.list_session_findings(
            customer_id=customer_id,
            scan_session_id=session_id,
            limit=limit,
            offset=offset,
        )

    async def list_customer_sessions(
        self,
        customer_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Dict[str, Any]]:
        """
        List all scan sessions for a customer.

        Args:
            customer_id: Customer ID
            limit: Maximum sessions to return
            offset: Number of sessions to skip

        Returns:
            list: Scan sessions sorted by created_at DESC
        """
        session_repo = ScanSessionRepository(self.db)
        return session_repo.list_customer_sessions(
            customer_id=customer_id,
            limit=limit,
            offset=offset,
        )
