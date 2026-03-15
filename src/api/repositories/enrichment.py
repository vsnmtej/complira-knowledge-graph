"""
Enrichment repository.

Handles database access for vulnerability enrichment:
- CVE details from reference DB
- EPSS scores from reference DB
- KEV status from reference DB
- Threat intelligence (CWE → CAPEC → ATT&CK) from reference DB
"""

from typing import List, Dict, Any, Optional
from api.repositories.base import BaseRepository
from complira_graph.models import (
    Vulnerability,
    EPSSHistory,
    KEVEntry,
    Weakness,
    AttackPattern,
    ATTACKTechnique,
)
import structlog

logger = structlog.get_logger()


class EnrichmentRepository(BaseRepository):
    """
    Repository for enrichment queries against reference database.

    All methods query the reference database (complira_graph_reference)
    for vulnerability intelligence data.
    """

    def __init__(self, db):
        """
        Initialize enrichment repository.

        Args:
            db: Reference database instance (complira_graph_reference)
        """
        super().__init__(db, "vulnerabilities")

    def get_cve_details(self, cve_id: str) -> Optional[Vulnerability]:
        """
        Get CVE details from reference database.

        Args:
            cve_id: CVE identifier (e.g., "CVE-2023-1234")

        Returns:
            Vulnerability model or None if not found
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln.cve_id == @cve_id
            LIMIT 1
            RETURN vuln
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)

        if not results:
            logger.debug("CVE not found in reference DB", cve_id=cve_id)
            return None

        return Vulnerability(**results[0])

    def batch_get_cve_details(self, cve_ids: List[str]) -> Dict[str, Vulnerability]:
        """
        Batch get CVE details for multiple CVEs.

        Args:
            cve_ids: List of CVE identifiers

        Returns:
            Dict mapping CVE ID → Vulnerability model
        """
        if not cve_ids:
            return {}

        query = """
        FOR cve_id IN @cve_ids
            LET vuln = FIRST(
                FOR v IN vulnerabilities
                    FILTER v.cve_id == cve_id
                    RETURN v
            )
            FILTER vuln != null
            RETURN vuln
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_ids": cve_ids})
        results = list(cursor)

        logger.debug(
            "Batch fetched CVE details",
            requested=len(cve_ids),
            found=len(results)
        )

        return {
            vuln_dict['cve_id']: Vulnerability(**vuln_dict)
            for vuln_dict in results
        }

    def get_latest_epss(self, cve_id: str) -> Optional[EPSSHistory]:
        """
        Get latest EPSS score for CVE.

        Args:
            cve_id: CVE identifier

        Returns:
            EPSSHistory model or None if not found
        """
        query = """
        FOR epss IN epss_history
            FILTER epss.cve_id == @cve_id
            SORT epss.score_date DESC
            LIMIT 1
            RETURN epss
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)

        if not results:
            logger.debug("EPSS not found", cve_id=cve_id)
            return None

        return EPSSHistory(**results[0])

    def batch_get_latest_epss(self, cve_ids: List[str]) -> Dict[str, EPSSHistory]:
        """
        Batch get latest EPSS scores for multiple CVEs.

        Args:
            cve_ids: List of CVE identifiers

        Returns:
            Dict mapping CVE ID → EPSSHistory model
        """
        if not cve_ids:
            return {}

        query = """
        FOR cve_id IN @cve_ids
            LET latest_epss = FIRST(
                FOR epss IN epss_history
                    FILTER epss.cve_id == cve_id
                    SORT epss.score_date DESC
                    LIMIT 1
                    RETURN epss
            )
            FILTER latest_epss != null
            RETURN latest_epss
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_ids": cve_ids})
        results = list(cursor)

        logger.debug(
            "Batch fetched EPSS scores",
            requested=len(cve_ids),
            found=len(results)
        )

        return {
            epss_dict['cve_id']: EPSSHistory(**epss_dict)
            for epss_dict in results
        }

    def check_kev_status(self, cve_id: str) -> Optional[KEVEntry]:
        """
        Check if CVE is in CISA KEV catalog.

        Args:
            cve_id: CVE identifier

        Returns:
            KEVEntry model or None if not in KEV
        """
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln.cve_id == @cve_id
            LIMIT 1
            LET kev = FIRST(
                FOR k IN 1..1 OUTBOUND vuln._id exploited_in_wild
                    RETURN k
            )
            FILTER kev != null
            RETURN kev
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_id": cve_id})
        results = list(cursor)

        if not results:
            logger.debug("CVE not in KEV", cve_id=cve_id)
            return None

        return KEVEntry(**results[0])

    def batch_check_kev_status(self, cve_ids: List[str]) -> Dict[str, KEVEntry]:
        """
        Batch check KEV status for multiple CVEs.

        Args:
            cve_ids: List of CVE identifiers

        Returns:
            Dict mapping CVE ID → KEVEntry model (only for CVEs in KEV)
        """
        if not cve_ids:
            return {}

        query = """
        FOR cve_id IN @cve_ids
            LET vuln = FIRST(
                FOR v IN vulnerabilities
                    FILTER v.cve_id == cve_id
                    RETURN v
            )
            FILTER vuln != null
            LET kev = FIRST(
                FOR k IN 1..1 OUTBOUND vuln._id exploited_in_wild
                    RETURN k
            )
            FILTER kev != null
            RETURN kev
        """

        cursor = self.db.aql_execute(query, bind_vars={"cve_ids": cve_ids})
        results = list(cursor)

        logger.debug(
            "Batch checked KEV status",
            requested=len(cve_ids),
            found=len(results)
        )

        return {
            kev_dict['cve_id']: KEVEntry(**kev_dict)
            for kev_dict in results
        }

    def get_threat_intelligence_chain(self, cwe_id: str) -> Optional[Dict[str, Any]]:
        """
        Get CWE → CAPEC → ATT&CK threat intelligence chain.

        Args:
            cwe_id: CWE identifier (e.g., "CWE-79")

        Returns:
            Dict with cwe, capecs, attacks or None if CWE not found
        """
        query = """
        FOR cwe IN weaknesses
            FILTER cwe.cwe_id == @cwe_id
            LIMIT 1

            // Get CAPECs
            LET capecs = (
                FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
                    RETURN {
                        capec_id: c.capec_id,
                        name: c.name,
                        description: c.description,
                        abstraction: c.abstraction,
                        status: c.status,
                        likelihood: c.likelihood,
                        severity: c.severity,
                        _key: c._key
                    }
            )

            // Get ATT&CK techniques
            LET attacks = (
                FOR capec IN FLATTEN(
                    FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
                        RETURN c
                )
                    FOR a IN 1..1 OUTBOUND capec._id capec_maps_to_attack
                        RETURN {
                            technique_id: a.technique_id,
                            name: a.name,
                            description: a.description,
                            tactic_names: a.tactic_names,
                            is_subtechnique: a.is_subtechnique,
                            platforms: a.platforms,
                            _key: a._key
                        }
            )

            RETURN {
                cwe: cwe,
                capecs: capecs,
                attacks: attacks
            }
        """

        cursor = self.db.aql_execute(query, bind_vars={"cwe_id": cwe_id})
        results = list(cursor)

        if not results:
            logger.debug("CWE not found in reference DB", cwe_id=cwe_id)
            return None

        return results[0]

    def batch_get_threat_intelligence_chain(
        self, cwe_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch get threat intelligence chains for multiple CWEs.

        Args:
            cwe_ids: List of CWE identifiers

        Returns:
            Dict mapping CWE ID → threat intel dict {cwe, capecs, attacks}
        """
        if not cwe_ids:
            return {}

        query = """
        FOR cwe_id IN @cwe_ids
            LET cwe = FIRST(
                FOR w IN weaknesses
                    FILTER w.cwe_id == cwe_id
                    RETURN w
            )
            FILTER cwe != null

            // Get CAPECs
            LET capecs = (
                FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
                    RETURN {
                        capec_id: c.capec_id,
                        name: c.name,
                        description: c.description,
                        abstraction: c.abstraction,
                        status: c.status,
                        likelihood: c.likelihood,
                        severity: c.severity,
                        _key: c._key
                    }
            )

            // Get ATT&CK techniques
            LET attacks = (
                FOR capec IN FLATTEN(
                    FOR c IN 1..1 INBOUND cwe._id capec_relates_to_cwe
                        RETURN c
                )
                    FOR a IN 1..1 OUTBOUND capec._id capec_maps_to_attack
                        RETURN {
                            technique_id: a.technique_id,
                            name: a.name,
                            description: a.description,
                            tactic_names: a.tactic_names,
                            is_subtechnique: a.is_subtechnique,
                            platforms: a.platforms,
                            _key: a._key
                        }
            )

            RETURN {
                cwe_id: cwe_id,
                cwe: cwe,
                capecs: capecs,
                attacks: attacks
            }
        """

        cursor = self.db.aql_execute(query, bind_vars={"cwe_ids": cwe_ids})
        results = list(cursor)

        logger.debug(
            "Batch fetched threat intel chains",
            requested=len(cwe_ids),
            found=len(results)
        )

        return {
            result['cwe_id']: result
            for result in results
        }
