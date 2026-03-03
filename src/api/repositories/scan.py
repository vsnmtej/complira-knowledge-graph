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

        Returns:
            ScanSession: Validated scan session model instance
        """
        from datetime import datetime
        from complira_graph.models import ScanSession

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
        from complira_graph.models import ScanSession

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
    ):
        """
        List all scan sessions for a customer.

        Args:
            customer_id: Customer identifier
            limit: Maximum number of sessions
            offset: Number of sessions to skip

        Returns:
            List[ScanSession]: List of validated session models sorted by created_at DESC
        """
        from complira_graph.models import ScanSession

        query = """
        FOR session IN scan_sessions
            FILTER session.customer_id == @customer_id
            SORT session.created_at DESC
            LIMIT @offset, @limit
            RETURN session
        """

        cursor = self.db.aql_execute(
            query,
            bind_vars={
                "customer_id": customer_id,
                "limit": limit,
                "offset": offset,
            }
        )

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
