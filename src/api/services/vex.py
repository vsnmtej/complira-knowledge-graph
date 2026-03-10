"""
VEX Management Service.

Handles CRUD operations for VEX documents and enriches them with
knowledge graph data (KEV, EPSS, CWE, ATT&CK, NIST controls, regulatory).
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
import structlog

from api.services.base import BaseGraphService, IDatabase, ICacheService
from api.models.requests.vex import (
    VEXDocumentRequest,
    VEXUpdateRequest,
    VEXVulnerabilityPatchRequest,
)
from api.models.responses.vex import (
    VEXDocumentResponse,
    VEXVulnerabilityResponse,
    VEXEnrichment,
    VEXCreateResponse,
    VEXUpdateResponse,
    VEXListResponse,
)

logger = structlog.get_logger()


class VEXService(BaseGraphService):
    """
    Service for managing VEX documents.

    Handles:
    - CREATE: Store client-generated VEX documents
    - READ: Retrieve VEX with knowledge graph enrichment
    - UPDATE: Update entire VEX document
    - PATCH: Update single vulnerability assessment
    - LIST: List all VEX documents for customer
    - DELETE: Remove VEX document
    """

    def __init__(
        self,
        customer_db: IDatabase,
        reference_db: IDatabase,
        cache: ICacheService,
    ):
        """
        Initialize VEX service.

        Args:
            customer_db: Customer database (for VEX storage)
            reference_db: Reference database (for knowledge graph)
            cache: Cache service
        """
        super().__init__(db=customer_db, cache=cache)
        self.customer_db = customer_db
        self.reference_db = reference_db
        self.logger = structlog.get_logger(service="VEXService")

    # ========================================================================
    # CREATE OPERATIONS
    # ========================================================================

    async def create_vex(
        self,
        vex_request: VEXDocumentRequest,
        customer_id: str,
    ) -> VEXCreateResponse:
        """
        Create new VEX document from client.

        Stores client VEX and enriches each CVE with knowledge graph data.

        Args:
            vex_request: VEX document from client
            customer_id: Customer ID

        Returns:
            VEXCreateResponse: Creation confirmation with statistics

        Raises:
            ValueError: If validation fails
        """
        self.logger.info(
            "Creating VEX document",
            customer_id=customer_id,
            vulnerabilities_count=len(vex_request.vulnerabilities),
        )

        # Generate unique VEX ID
        vex_id = f"vex_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat() + "Z"

        # Enrich each vulnerability
        enriched_vulnerabilities = []
        enriched_count = 0

        for vuln in vex_request.vulnerabilities:
            enrichment = await self._enrich_vulnerability(vuln.id)
            if enrichment:
                enriched_count += 1

            enriched_vulnerabilities.append({
                "cve_id": vuln.id,
                "state": vuln.analysis.state,
                "justification": vuln.analysis.justification,
                "response": vuln.analysis.response,
                "detail": vuln.analysis.detail,
                "enrichment": enrichment or {},
            })

        # Build VEX document
        vex_document = {
            "_key": vex_id,
            "customer_id": customer_id,
            "bomFormat": vex_request.bomFormat,
            "specVersion": vex_request.specVersion,
            "version": vex_request.version,
            "vulnerabilities": enriched_vulnerabilities,
            "metadata": vex_request.metadata,
            "created_at": now,
            "updated_at": now,
        }

        # Store in customer database
        collection = self.customer_db.collection("vex_documents")
        collection.insert(vex_document)

        self.logger.info(
            "VEX document created",
            vex_id=vex_id,
            customer_id=customer_id,
            vulnerabilities_count=len(vex_request.vulnerabilities),
            enriched_count=enriched_count,
        )

        return VEXCreateResponse(
            vex_id=vex_id,
            vulnerabilities_count=len(vex_request.vulnerabilities),
            enriched_count=enriched_count,
            created_at=now,
        )

    # ========================================================================
    # READ OPERATIONS
    # ========================================================================

    async def get_vex(
        self,
        vex_id: str,
        customer_id: str,
    ) -> Optional[VEXDocumentResponse]:
        """
        Retrieve VEX document by ID.

        Args:
            vex_id: VEX document identifier
            customer_id: Customer ID (for authorization)

        Returns:
            VEXDocumentResponse or None: Enriched VEX document

        Raises:
            ValueError: If VEX not found or unauthorized
        """
        self.logger.debug("Retrieving VEX document", vex_id=vex_id, customer_id=customer_id)

        # Fetch from customer database
        query = """
        FOR vex IN vex_documents
            FILTER vex._key == @vex_id
            FILTER vex.customer_id == @customer_id
            RETURN vex
        """

        cursor = self.customer_db.aql.execute(
            query,
            bind_vars={"vex_id": vex_id, "customer_id": customer_id}
        )

        results = list(cursor)
        if not results:
            raise ValueError(f"VEX document not found: {vex_id}")

        vex_doc = results[0]

        # Build response
        vulnerabilities = []
        for vuln in vex_doc["vulnerabilities"]:
            # Convert enrichment dict to VEXEnrichment model
            enrichment = VEXEnrichment(**vuln.get("enrichment", {}))

            vulnerabilities.append(
                VEXVulnerabilityResponse(
                    cve_id=vuln["cve_id"],
                    state=vuln["state"],
                    justification=vuln.get("justification"),
                    response=vuln.get("response"),
                    detail=vuln.get("detail"),
                    enrichment=enrichment,
                )
            )

        return VEXDocumentResponse(
            vex_id=vex_doc["_key"],
            bomFormat=vex_doc.get("bomFormat", "CycloneDX"),
            specVersion=vex_doc.get("specVersion", "1.5"),
            version=vex_doc.get("version", 1),
            vulnerabilities=vulnerabilities,
            metadata=vex_doc.get("metadata", {}),
            created_at=vex_doc["created_at"],
            updated_at=vex_doc["updated_at"],
            customer_id=vex_doc["customer_id"],
        )

    async def list_vex_documents(
        self,
        customer_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[VEXListResponse]:
        """
        List all VEX documents for customer.

        Args:
            customer_id: Customer ID
            limit: Maximum documents to return
            offset: Number of documents to skip

        Returns:
            List of VEXListResponse
        """
        self.logger.debug(
            "Listing VEX documents",
            customer_id=customer_id,
            limit=limit,
            offset=offset,
        )

        query = """
        FOR vex IN vex_documents
            FILTER vex.customer_id == @customer_id
            SORT vex.created_at DESC
            LIMIT @offset, @limit
            RETURN {
                vex_id: vex._key,
                vulnerabilities_count: LENGTH(vex.vulnerabilities),
                created_at: vex.created_at,
                updated_at: vex.updated_at,
                metadata: vex.metadata
            }
        """

        cursor = self.customer_db.aql.execute(
            query,
            bind_vars={"customer_id": customer_id, "limit": limit, "offset": offset}
        )

        results = list(cursor)

        return [
            VEXListResponse(
                vex_id=doc["vex_id"],
                vulnerabilities_count=doc["vulnerabilities_count"],
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
                metadata=doc.get("metadata", {}),
            )
            for doc in results
        ]

    # ========================================================================
    # UPDATE OPERATIONS
    # ========================================================================

    async def update_vex(
        self,
        vex_id: str,
        update_request: VEXUpdateRequest,
        customer_id: str,
    ) -> VEXUpdateResponse:
        """
        Update entire VEX document (PUT operation).

        Args:
            vex_id: VEX document identifier
            update_request: Updated VEX data
            customer_id: Customer ID (for authorization)

        Returns:
            VEXUpdateResponse: Update confirmation

        Raises:
            ValueError: If VEX not found or unauthorized
        """
        self.logger.info(
            "Updating VEX document",
            vex_id=vex_id,
            customer_id=customer_id,
            vulnerabilities_count=len(update_request.vulnerabilities),
        )

        # Verify VEX exists and customer owns it
        existing = await self.get_vex(vex_id, customer_id)
        if not existing:
            raise ValueError(f"VEX document not found: {vex_id}")

        now = datetime.utcnow().isoformat() + "Z"

        # Re-enrich all vulnerabilities
        enriched_vulnerabilities = []
        for vuln in update_request.vulnerabilities:
            enrichment = await self._enrich_vulnerability(vuln.id)

            enriched_vulnerabilities.append({
                "cve_id": vuln.id,
                "state": vuln.analysis.state,
                "justification": vuln.analysis.justification,
                "response": vuln.analysis.response,
                "detail": vuln.analysis.detail,
                "enrichment": enrichment or {},
            })

        # Update document
        update_doc = {
            "vulnerabilities": enriched_vulnerabilities,
            "metadata": update_request.metadata,
            "updated_at": now,
        }

        collection = self.customer_db.collection("vex_documents")
        collection.update(
            {"_key": vex_id, "customer_id": customer_id},
            update_doc,
        )

        self.logger.info(
            "VEX document updated",
            vex_id=vex_id,
            customer_id=customer_id,
        )

        return VEXUpdateResponse(
            vex_id=vex_id,
            updated_at=now,
            vulnerabilities_count=len(update_request.vulnerabilities),
        )

    async def patch_vulnerability(
        self,
        vex_id: str,
        cve_id: str,
        patch_request: VEXVulnerabilityPatchRequest,
        customer_id: str,
    ) -> VEXUpdateResponse:
        """
        Update single vulnerability assessment (PATCH operation).

        Args:
            vex_id: VEX document identifier
            cve_id: CVE identifier to update
            patch_request: Updated analysis
            customer_id: Customer ID (for authorization)

        Returns:
            VEXUpdateResponse: Update confirmation

        Raises:
            ValueError: If VEX or CVE not found
        """
        self.logger.info(
            "Patching vulnerability in VEX",
            vex_id=vex_id,
            cve_id=cve_id,
            customer_id=customer_id,
        )

        # Get existing VEX
        existing = await self.get_vex(vex_id, customer_id)
        if not existing:
            raise ValueError(f"VEX document not found: {vex_id}")

        # Find vulnerability to update
        vuln_index = None
        for idx, vuln in enumerate(existing.vulnerabilities):
            if vuln.cve_id.upper() == cve_id.upper():
                vuln_index = idx
                break

        if vuln_index is None:
            raise ValueError(f"CVE not found in VEX document: {cve_id}")

        # Re-enrich this CVE
        enrichment = await self._enrich_vulnerability(cve_id)

        now = datetime.utcnow().isoformat() + "Z"

        # Update using AQL
        query = """
        FOR vex IN vex_documents
            FILTER vex._key == @vex_id
            FILTER vex.customer_id == @customer_id
            LET updated_vulns = (
                FOR vuln IN vex.vulnerabilities
                    RETURN vuln.cve_id == @cve_id ?
                        MERGE(vuln, {
                            state: @state,
                            justification: @justification,
                            response: @response,
                            detail: @detail,
                            enrichment: @enrichment
                        }) : vuln
            )
            UPDATE vex WITH {
                vulnerabilities: updated_vulns,
                updated_at: @updated_at
            } IN vex_documents
            RETURN NEW
        """

        cursor = self.customer_db.aql.execute(
            query,
            bind_vars={
                "vex_id": vex_id,
                "customer_id": customer_id,
                "cve_id": cve_id.upper(),
                "state": patch_request.analysis.state,
                "justification": patch_request.analysis.justification,
                "response": patch_request.analysis.response,
                "detail": patch_request.analysis.detail,
                "enrichment": enrichment or {},
                "updated_at": now,
            }
        )

        list(cursor)  # Execute query

        self.logger.info(
            "Vulnerability patched in VEX",
            vex_id=vex_id,
            cve_id=cve_id,
            customer_id=customer_id,
        )

        return VEXUpdateResponse(
            vex_id=vex_id,
            updated_at=now,
            vulnerabilities_count=len(existing.vulnerabilities),
        )

    # ========================================================================
    # DELETE OPERATIONS
    # ========================================================================

    async def delete_vex(
        self,
        vex_id: str,
        customer_id: str,
    ) -> bool:
        """
        Delete VEX document.

        Args:
            vex_id: VEX document identifier
            customer_id: Customer ID (for authorization)

        Returns:
            bool: True if deleted

        Raises:
            ValueError: If VEX not found or unauthorized
        """
        self.logger.info(
            "Deleting VEX document",
            vex_id=vex_id,
            customer_id=customer_id,
        )

        # Verify ownership
        existing = await self.get_vex(vex_id, customer_id)
        if not existing:
            raise ValueError(f"VEX document not found: {vex_id}")

        # Delete
        collection = self.customer_db.collection("vex_documents")
        collection.delete({"_key": vex_id, "customer_id": customer_id})

        self.logger.info(
            "VEX document deleted",
            vex_id=vex_id,
            customer_id=customer_id,
        )

        return True

    # ========================================================================
    # ENRICHMENT LOGIC
    # ========================================================================

    async def _enrich_vulnerability(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """
        Enrich CVE with knowledge graph data.

        Fetches:
        - KEV status (CISA catalog)
        - EPSS scores
        - CVSS scores
        - CWE weaknesses
        - ATT&CK techniques
        - NIST controls
        - D3FEND defenses
        - Regulatory violations

        Args:
            cve_id: CVE identifier

        Returns:
            Enrichment data dictionary or None
        """
        self.logger.debug("Enriching CVE", cve_id=cve_id)

        # Normalize CVE ID
        cve_key = cve_id.replace("-", "_").upper()

        # Enrichment query (optimized single query)
        query = """
        LET cve = DOCUMENT("vulnerabilities", @cve_key)

        LET kev = (
            FOR k IN kev_entries
                FILTER k.cve_id == cve.cve_id
                LIMIT 1
                RETURN {
                    in_kev: true,
                    kev_date_added: k.date_added,
                    kev_due_date: k.due_date
                }
        )[0]

        LET epss = (
            FOR e IN 1..1 OUTBOUND cve has_epss
                SORT e.score_date DESC
                LIMIT 1
                RETURN {
                    epss_score: e.epss_score,
                    epss_percentile: e.percentile
                }
        )[0]

        LET weaknesses = (
            FOR cwe IN 1..1 OUTBOUND cve has_weakness
                RETURN {
                    cwe_id: cwe.cwe_id,
                    name: cwe.name
                }
        )

        LET attack_techniques = (
            FOR cwe IN 1..1 OUTBOUND cve has_weakness
                FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                    FOR tech IN 1..1 OUTBOUND capec capec_maps_to_attack
                        RETURN DISTINCT {
                            technique_id: tech.technique_id,
                            name: tech.name
                        }
        )

        LET nist_controls = (
            FOR cwe IN 1..1 OUTBOUND cve has_weakness
                FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                    FOR tech IN 1..1 OUTBOUND capec capec_maps_to_attack
                        FOR ctrl IN 1..1 OUTBOUND tech technique_mitigated_by_control
                            RETURN DISTINCT {
                                control_id: ctrl.control_id,
                                title: ctrl.title
                            }
        )

        LET d3fend = (
            FOR cwe IN 1..1 OUTBOUND cve has_weakness
                FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
                    FOR tech IN 1..1 OUTBOUND capec capec_maps_to_attack
                        FOR def IN 1..1 OUTBOUND tech d3fend_counters_technique
                            RETURN DISTINCT {
                                technique_id: def.technique_id,
                                name: def.name
                            }
        )

        LET regulatory = (
            FOR req IN 1..1 OUTBOUND cve violates_requirement
                RETURN {
                    framework: req.framework,
                    requirement_id: req.requirement_id
                }
        )

        RETURN {
            in_kev: kev.in_kev OR false,
            kev_date_added: kev.kev_date_added,
            kev_due_date: kev.kev_due_date,
            epss_score: epss.epss_score,
            epss_percentile: epss.epss_percentile,
            cvss_score: cve.cvss_v3_score,
            cvss_severity: cve.cvss_v3_severity,
            weaknesses: weaknesses,
            attack_techniques: attack_techniques,
            nist_controls: nist_controls,
            d3fend_defenses: d3fend,
            regulatory_violations: regulatory
        }
        """

        try:
            cursor = self.reference_db.aql.execute(
                query,
                bind_vars={"cve_key": cve_key}
            )

            results = list(cursor)
            if results:
                enrichment = results[0]
                self.logger.debug(
                    "CVE enriched",
                    cve_id=cve_id,
                    in_kev=enrichment.get("in_kev", False),
                    weaknesses_count=len(enrichment.get("weaknesses", [])),
                )
                return enrichment
            else:
                self.logger.warning("CVE not found in reference database", cve_id=cve_id)
                return None

        except Exception as e:
            self.logger.error(
                "Failed to enrich CVE",
                cve_id=cve_id,
                error=str(e),
            )
            return None
