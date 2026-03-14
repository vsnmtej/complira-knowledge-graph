"""
Scan repository.

Handles database access for:
- scan_sessions: Scan metadata
- scan_findings: Individual findings from scans
"""

from typing import List, Dict, Any, Optional
from api.repositories.base import BaseRepository
import structlog

logger = structlog.get_logger()


class ScanSessionRepository(BaseRepository):
    """
    Repository for scan_sessions collection.

    Scan sessions store metadata about scan executions:
    - customer_id
    - tool_name, tool_version
    - scan_timestamp
    - status (pending, processing, completed, failed)
    - findings_count
    - created_at, updated_at
    """

    def __init__(self, db):
        """
        Initialize scan session repository.

        Args:
            db: Database instance (customer database)
        """
        super().__init__(db, "scan_sessions")

    def create_session(
        self,
        customer_id: str,
        tool_name: str,
        tool_version: str,
        scan_timestamp: str,
        scan_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        repository_id: Optional[str] = None,
    ):
        """
        Create new scan session with validated model.

        Args:
            customer_id: Customer identifier
            tool_name: Scanner tool name
            tool_version: Scanner tool version
            scan_timestamp: Scan execution timestamp
            scan_type: Scan type (sarif, cyclonedx, etc.)
            metadata: Optional additional metadata
            project_id: Optional project identifier (for multi-tenant hierarchy)
            repository_id: Optional repository identifier (for multi-tenant hierarchy)

        Returns:
            ScanSession: Validated scan session model instance
        """
        from datetime import datetime
        # Import from legacy flat models file (not the models package)
        from complira_graph.models import ScanSession  # models.py, not models/__init__.py

        # Create validated model instance
        session = ScanSession(
            customer_id=customer_id,
            tool_name=tool_name,
            tool_version=tool_version,
            scan_timestamp=scan_timestamp,
            scan_type=scan_type,
            status="processing",
            findings_count=0,
            components_count=0,
            metadata=metadata or {},
            project_id=project_id,
            repository_id=repository_id,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )

        # Convert to dict for database storage
        session_dict = session.model_dump()

        # Store in database
        result = self.create(session_dict)

        logger.info(
            "Scan session created",
            session_id=result.get("_key"),
            customer_id=customer_id,
            tool_name=tool_name,
        )

        # Return as validated model
        return ScanSession(**result)

    def update_session_status(
        self,
        session_key: str,
        status: str,
        findings_count: Optional[int] = None,
        components_count: Optional[int] = None,
    ):
        """
        Update scan session status with model validation.

        Args:
            session_key: Session _key
            status: New status (processing, completed, failed)
            findings_count: Optional findings count
            components_count: Optional components count

        Returns:
            ScanSession: Updated scan session model
        """
        from datetime import datetime
        # Import from legacy flat models file (not the models package)
        from complira_graph.models import ScanSession  # models.py, not models/__init__.py

        update_data = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }

        if findings_count is not None:
            update_data["findings_count"] = findings_count

        if components_count is not None:
            update_data["components_count"] = components_count

        result = self.update(session_key, update_data)

        logger.debug(
            "Scan session updated",
            session_id=session_key,
            status=status,
        )

        # Return as validated model
        return ScanSession(**result)

    def list_customer_sessions(
        self,
        customer_id: str,
        limit: int = 100,
        offset: int = 0,
        project_id: Optional[str] = None,
        repository_id: Optional[str] = None,
    ):
        """
        List all scan sessions for a customer, optionally filtered by project/repository.

        Args:
            customer_id: Customer identifier
            limit: Maximum number of sessions
            offset: Number of sessions to skip
            project_id: Optional project identifier filter
            repository_id: Optional repository identifier filter

        Returns:
            List[ScanSession]: List of validated session models sorted by created_at DESC
        """
        from complira_graph.models import ScanSession

        # Build filter conditions
        filters = ["session.customer_id == @customer_id"]
        bind_vars = {
            "customer_id": customer_id,
            "limit": limit,
            "offset": offset,
        }

        if project_id is not None:
            filters.append("session.project_id == @project_id")
            bind_vars["project_id"] = project_id

        if repository_id is not None:
            filters.append("session.repository_id == @repository_id")
            bind_vars["repository_id"] = repository_id

        filter_clause = " AND ".join(filters)

        query = f"""
        FOR session IN scan_sessions
            FILTER {filter_clause}
            SORT session.created_at DESC
            LIMIT @offset, @limit
            RETURN session
        """

        cursor = self.db.aql_execute(query, bind_vars=bind_vars)

        # Convert each dict to validated model
        return [ScanSession(**session) for session in cursor]


class ScanFindingRepository(BaseRepository):
    """
    Repository for scan_findings collection.

    Scan findings store individual vulnerabilities discovered in scans:
    - customer_id
    - scan_session_id
    - cve_id
    - severity
    - description
    - location
    - raw_data
    """

    def __init__(self, db):
        """
        Initialize scan finding repository.

        Args:
            db: Database instance (customer database)
        """
        super().__init__(db, "scan_findings")

    def create_finding(
        self,
        customer_id: str,
        scan_session_id: str,
        cve_id: Optional[str],
        severity: str,
        description: str,
        location: str,
        tool_name: str,
        raw_data: Dict[str, Any],
    ):
        """
        Create new scan finding with model validation and normalization.

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session _key
            cve_id: CVE identifier (optional - None for non-CVE findings)
            severity: Severity level (will be normalized to uppercase)
            description: Finding description
            location: Finding location (file:line or component@version)
            tool_name: Scanner tool name
            raw_data: Original finding data

        Returns:
            ScanFinding: Validated finding model instance with normalized severity and CVE ID
        """
        from datetime import datetime
        from complira_graph.models import ScanFinding

        # Create validated model instance (auto-normalizes severity and CVE ID)
        finding = ScanFinding(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            cve_id=cve_id,  # Model validates format and normalizes to uppercase
            severity=severity,  # Model normalizes to uppercase
            description=description,
            location=location,
            tool_name=tool_name,
            raw_data=raw_data,
            created_at=datetime.utcnow().isoformat(),
        )

        # Convert to dict for database storage
        finding_dict = finding.model_dump()

        # Store in database
        result = self.create(finding_dict)

        logger.debug(
            "Scan finding created",
            finding_id=result.get("_key"),
            cve_id=finding.cve_id,  # Use normalized CVE ID from model
            session_id=scan_session_id,
        )

        # Return as validated model
        return ScanFinding(**result)

    def bulk_create_findings(
        self,
        findings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Bulk create scan findings.

        Args:
            findings: List of finding dictionaries

        Returns:
            list: Created findings with _key
        """
        from datetime import datetime

        # Add created_at to all findings
        for finding in findings:
            if "created_at" not in finding:
                finding["created_at"] = datetime.utcnow().isoformat()

        # Use bulk insert for performance
        results = self.collection.insert_many(findings, return_new=True)

        logger.info(
            "Bulk created scan findings",
            findings_count=len(findings),
        )

        return [r['new'] for r in results]

    def list_session_findings(
        self,
        customer_id: str,
        scan_session_id: str,
        limit: int = 1000,
        offset: int = 0,
    ):
        """
        List all findings for a scan session.

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session _key
            limit: Maximum number of findings
            offset: Number of findings to skip

        Returns:
            List[ScanFinding]: List of validated finding models sorted by severity
        """
        from complira_graph.models import ScanFinding

        query = """
        FOR finding IN scan_findings
            FILTER finding.customer_id == @customer_id
            FILTER finding.scan_session_id == @scan_session_id
            SORT finding.severity DESC
            LIMIT @offset, @limit
            RETURN finding
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={
                "customer_id": customer_id,
                "scan_session_id": scan_session_id,
                "limit": limit,
                "offset": offset,
            }
        )

        # Convert each dict to validated model
        return [ScanFinding(**finding) for finding in cursor]

    def count_session_findings(
        self,
        customer_id: str,
        scan_session_id: str,
    ) -> int:
        """
        Count findings for a scan session.

        Args:
            customer_id: Customer identifier
            scan_session_id: Scan session _key

        Returns:
            int: Number of findings
        """
        query = """
        FOR finding IN scan_findings
            FILTER finding.customer_id == @customer_id
            FILTER finding.scan_session_id == @scan_session_id
            COLLECT WITH COUNT INTO count
            RETURN count
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={
                "customer_id": customer_id,
                "scan_session_id": scan_session_id,
            }
        )

        result = list(cursor)
        return result[0] if result else 0


class ScanEdgeRepository(BaseRepository):
    """
    Repository for scan-related edge collections.

    Handles edges:
    - finding_to_cve: Finding → CVE relationships
    - component_to_finding: Component → Finding relationships
    - matched_by_cpe: Component → CPE mappings
    """

    def __init__(self, db, collection_name: str):
        """
        Initialize scan edge repository.

        Args:
            db: Database instance (customer database)
            collection_name: Name of the edge collection
        """
        super().__init__(db, collection_name)

    def create_finding_to_cve_edges(
        self,
        findings: List[Dict[str, Any]],
    ) -> int:
        """
        Create edges from findings to CVE nodes.

        Args:
            findings: List of finding documents

        Returns:
            int: Number of edges created
        """
        edges_created = 0
        for finding in findings:
            if not finding.get("cve_id"):
                continue  # Skip findings without CVE ID

            # Create edge from finding to CVE
            edge = {
                "_from": f"scan_findings/{finding['_key']}",
                "_to": f"vulnerabilities/{finding['cve_id']}",
            }

            try:
                self.collection.insert(edge, overwrite_mode="ignore")
                edges_created += 1
            except Exception as e:
                logger.debug(
                    "Failed to create finding→CVE edge",
                    finding_id=finding["_key"],
                    cve_id=finding["cve_id"],
                    error=str(e),
                )

        logger.info(
            "Created finding→CVE edges",
            edges_created=edges_created,
        )

        return edges_created

    def create_component_to_finding_edges(
        self,
        components: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
    ) -> int:
        """
        Create edges from components to findings based on location matching.

        Args:
            components: List of component documents
            findings: List of finding documents

        Returns:
            int: Number of edges created
        """
        # Build component lookup map
        component_map = {}
        for component in components:
            purl = component.get("purl", "")
            if purl:
                component_map[purl] = component

        edges_created = 0
        for finding in findings:
            location = finding.get("location", "")

            # Try to match finding location to component PURL
            matched_component = None
            for purl, component in component_map.items():
                # Simple substring match (can be improved with better heuristics)
                if purl in location or component.get("name", "") in location:
                    matched_component = component
                    break

            if matched_component:
                # Create edge from component to finding
                edge = {
                    "_from": f"customer_components/{matched_component['_key']}",
                    "_to": f"scan_findings/{finding['_key']}",
                }

                try:
                    self.collection.insert(edge, overwrite_mode="ignore")
                    edges_created += 1
                except Exception as e:
                    logger.debug(
                        "Failed to create component→finding edge",
                        component_key=matched_component["_key"],
                        finding_id=finding["_key"],
                        error=str(e),
                    )

        logger.info(
            "Created component→finding edges",
            edges_created=edges_created,
        )

        return edges_created

    def create_matched_by_cpe_edge(
        self,
        component_key: str,
        cpe_key: str,
        customer_id: str,
        confidence: float,
        provenance: Dict[str, Any],
    ) -> bool:
        """
        Create edge from component to CPE entry.

        Args:
            component_key: Component document _key
            cpe_key: CPE entry _key
            customer_id: Customer identifier
            confidence: Confidence score (0.0-1.0)
            provenance: LLM provenance data

        Returns:
            bool: True if edge created successfully
        """
        edge = {
            "_from": f"customer_components/{component_key}",
            "_to": f"cpe_entries/{cpe_key}",
            "customer_id": customer_id,
            "confidence": confidence,
            "provenance": provenance,
        }

        try:
            self.collection.insert(edge, overwrite_mode="ignore")
            logger.debug(
                "Created matched_by_cpe edge",
                component_key=component_key,
                cpe_key=cpe_key,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to create matched_by_cpe edge",
                component_key=component_key,
                cpe_key=cpe_key,
                error=str(e),
            )
            return False


class CPERepository(BaseRepository):
    """
    Repository for CPE entries and LLM enrichments.

    Handles:
    - cpe_entries: CPE (Common Platform Enumeration) mappings
    - llm_enrichments: LLM-generated enrichment provenance
    """

    def __init__(self, db, collection_name: str):
        """
        Initialize CPE repository.

        Args:
            db: Database instance (customer database)
            collection_name: Name of the collection
        """
        super().__init__(db, collection_name)

    def insert_cpe_entry(
        self,
        customer_id: str,
        cpe_uri: str,
        purl: str,
        vendor: str,
        product: str,
        version: str,
        source: str = "llm",
    ) -> Dict[str, Any]:
        """
        Insert CPE entry.

        Args:
            customer_id: Customer identifier
            cpe_uri: CPE URI (e.g., "cpe:2.3:a:vendor:product:version")
            purl: Package URL
            vendor: Vendor name
            product: Product name
            version: Product version
            source: Source of CPE mapping (default: "llm")

        Returns:
            dict: Created or existing CPE entry
        """
        from datetime import datetime

        # Generate safe key from CPE URI
        safe_key = cpe_uri.replace(":", "_").replace("/", "_").replace("*", "ANY")

        cpe_entry = {
            "_key": safe_key,
            "customer_id": customer_id,
            "cpe_uri": cpe_uri,
            "purl": purl,
            "vendor": vendor,
            "product": product,
            "version": version,
            "source": source,
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            result = self.collection.insert(
                cpe_entry,
                overwrite_mode="update",
            )
            logger.debug(
                "CPE entry inserted",
                cpe_uri=cpe_uri,
                purl=purl,
            )
            return cpe_entry
        except Exception as e:
            logger.error(
                "Failed to insert CPE entry",
                cpe_uri=cpe_uri,
                error=str(e),
            )
            raise

    def insert_llm_enrichment(
        self,
        provenance: Dict[str, Any],
    ) -> bool:
        """
        Insert LLM enrichment provenance.

        Args:
            provenance: LLM provenance data

        Returns:
            bool: True if inserted successfully
        """
        try:
            # Ensure collection exists
            if not self.db.has_collection("llm_enrichments"):
                self.db.create_collection("llm_enrichments", edge=False)

            llm_collection = self.db.collection("llm_enrichments")
            llm_collection.insert(provenance)
            logger.debug("LLM enrichment provenance stored")
            return True
        except Exception as e:
            logger.debug(
                "Failed to store LLM enrichment provenance",
                error=str(e),
            )
            return False
