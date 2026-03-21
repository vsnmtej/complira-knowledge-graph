"""
Base graph service with reusable traversal patterns (DRY).

This is the critical DRY component that eliminates 3000+ lines of
duplicated graph traversal logic across 10+ feature services.

All feature services extend this base class to inherit:
- Generic graph traversal
- Shortest path computation
- Coverage percentage calculation
- Risk aggregation
- Customer scoping injection

SOLID Principles:
- SRP: Only graph traversal logic, no HTTP or cache concerns
- OCP: Extensible via inheritance, closed for modification
- LSP: All subclasses are substitutable
- DIP: Depends on IDatabase and ICacheService abstractions
"""

from typing import Protocol, Any, List, Dict, Optional
from abc import ABC
import structlog

logger = structlog.get_logger()


# ========== Protocols (DIP) ==========


class IDatabase(Protocol):
    """
    Database abstraction (DIP).

    Services depend on this interface, not concrete ArangoDB implementation.
    """

    def aql_execute(self, query: str, bind_vars: dict = None):
        """Execute AQL query and return cursor."""
        ...

    def has_collection(self, name: str) -> bool:
        """Check if collection exists."""
        ...

    def collection(self, name: str):
        """Get collection."""
        ...


class ICacheService(Protocol):
    """
    Cache abstraction (DIP).

    Services depend on this interface, not concrete Redis implementation.
    """

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        ...

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        ...

    def delete(self, key: str) -> None:
        """Delete value from cache."""
        ...


# ========== Base Service (DRY) ==========


class BaseGraphService(ABC):
    """
    Reusable graph traversal patterns (DRY).

    All feature services extend this base class.

    Used by:
    - BlastRadiusService (CVE → CWE → CAPEC → ATT&CK → Threat Groups)
    - DefenseCoverageService (Findings → CVE → CWE → ATT&CK → Controls)
    - DependencyRiskService (Component → depends_on → CVE)
    - RemediationPlaybookService (CVE → CWE → CAPEC → ATT&CK → Controls → Reqs)
    - EnrichmentService (CVE → CWE → ATT&CK, KEV, EPSS)
    - CompactionService (Finding → aliases → dedupe)
    - ControlMappingService (CVE → CWE → NIST/ISO/PCI)
    - PortfolioRiskService (aggregate EPSS trends)
    - EPSSVelocityService (time-series analysis)
    - RegulatoryDeltaService (framework version diff)

    SOLID Principles Applied:
    - SRP: Only graph traversal logic, no HTTP or cache concerns
    - OCP: Extensible via inheritance, closed for modification
    - LSP: All subclasses are substitutable
    - DIP: Depends on IDatabase and ICacheService abstractions
    """

    def __init__(self, db: IDatabase, cache: ICacheService):
        """
        Initialize service with dependencies.

        Args:
            db: Database instance (DIP: depends on IDatabase abstraction)
            cache: Cache service (DIP: depends on ICacheService abstraction)
        """
        self.db = db
        self.cache = cache
        self.logger = structlog.get_logger(
            service=self.__class__.__name__
        )

    # ========== Graph Traversal Patterns (DRY) ==========

    def traverse(
        self,
        start_collection: str,
        start_key: str,
        edge_definitions: List[str],
        max_depth: int = 4,
        customer_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generic graph traversal (DRY).

        Used by:
        - BlastRadiusService (CVE → CWE → CAPEC → ATT&CK → Threat Groups)
        - DefenseCoverageService (Findings → CVE → CWE → ATT&CK → Controls)
        - DependencyRiskService (Component → depends_on → CVE)
        - RemediationPlaybookService (CVE → CWE → CAPEC → ATT&CK → Controls → Reqs)

        Args:
            start_collection: Starting collection name (e.g., "vulnerabilities")
            start_key: Starting document key (e.g., "cve-2021-44228")
            edge_definitions: List of edge collection names to traverse
            max_depth: Maximum traversal depth (default: 4 hops)
            customer_id: Optional customer ID for scoping (auto-injected filter)
            filters: Optional additional AQL filters

        Returns:
            dict: {
                "vertices": [list of vertex documents],
                "edges": [list of edge documents],
                "paths": [list of path objects]
            }

        Example:
            # Blast radius: CVE → CWE → CAPEC → ATT&CK
            result = self.traverse(
                start_collection="vulnerabilities",
                start_key="cve-2021-44228",
                edge_definitions=["has_weakness", "capec_relates_to_cwe", "capec_maps_to_attack"],
                max_depth=3
            )
        """
        self.logger.debug(
            "Starting graph traversal",
            start_collection=start_collection,
            start_key=start_key,
            max_depth=max_depth,
        )

        # Build AQL traversal query
        query = f"""
        FOR v, e, p IN 1..@max_depth OUTBOUND @start_doc {', '.join(edge_definitions)}
            OPTIONS {{uniqueVertices: "global", bfs: true}}
        """

        # Add filters
        filter_clauses = []

        if customer_id:
            filter_clauses.append(f'FILTER v.customer_id == "{customer_id}"')

        if filters:
            for field, value in filters.items():
                if isinstance(value, str):
                    filter_clauses.append(f'FILTER v.{field} == "{value}"')
                else:
                    filter_clauses.append(f'FILTER v.{field} == {value}')

        if filter_clauses:
            query += "\n    " + "\n    ".join(filter_clauses)

        query += """
            RETURN {vertex: v, edge: e, path: p}
        """

        # Execute query
        try:
            cursor = self.db.aql_execute(
                query,
                bind_vars={
                    'start_doc': f'{start_collection}/{start_key}',
                    'max_depth': max_depth
                }
            )

            results = list(cursor)

            # Extract unique vertices, edges, and paths
            vertices = []
            edges = []
            paths = []
            seen_vertices = set()
            seen_edges = set()

            for result in results:
                vertex = result.get('vertex')
                edge = result.get('edge')
                path = result.get('path')

                if vertex and vertex.get('_id') not in seen_vertices:
                    vertices.append(vertex)
                    seen_vertices.add(vertex['_id'])

                if edge and edge.get('_id') not in seen_edges:
                    edges.append(edge)
                    seen_edges.add(edge['_id'])

                if path:
                    paths.append(path)

            self.logger.info(
                "Graph traversal complete",
                vertices_count=len(vertices),
                edges_count=len(edges),
                paths_count=len(paths),
            )

            return {
                'vertices': vertices,
                'edges': edges,
                'paths': paths,
            }

        except Exception as e:
            self.logger.error(
                "Graph traversal failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def shortest_path(
        self,
        from_collection: str,
        from_key: str,
        to_collection: str,
        to_key: str,
        via_edges: List[str],
    ) -> Dict[str, Any]:
        """
        Shortest path between two nodes (DRY).

        Used by:
        - RemediationPlaybookService (CVE → specific control)
        - BlastRadiusService (CVE → threat actor group)

        Args:
            from_collection: Source collection
            from_key: Source document key
            to_collection: Target collection
            to_key: Target document key
            via_edges: Edge collections to traverse

        Returns:
            dict: {
                "vertices": [ordered list of vertices in path],
                "edges": [ordered list of edges in path],
                "distance": int (hop count)
            }

        Example:
            # Find path from CVE to specific ATT&CK technique
            path = self.shortest_path(
                from_collection="vulnerabilities",
                from_key="cve-2021-44228",
                to_collection="attack_techniques",
                to_key="t1190",
                via_edges=["has_weakness", "technique_exploits_weakness"]
            )
        """
        self.logger.debug(
            "Computing shortest path",
            from_doc=f"{from_collection}/{from_key}",
            to_doc=f"{to_collection}/{to_key}",
        )

        query = f"""
        FOR v, e IN OUTBOUND SHORTEST_PATH
            @from_doc TO @to_doc
            {', '.join(via_edges)}
            RETURN {{vertex: v, edge: e}}
        """

        try:
            cursor = self.db.aql_execute(
                query,
                bind_vars={
                    'from_doc': f'{from_collection}/{from_key}',
                    'to_doc': f'{to_collection}/{to_key}'
                }
            )

            results = list(cursor)

            vertices = [r['vertex'] for r in results if r.get('vertex')]
            edges = [r['edge'] for r in results if r.get('edge')]

            self.logger.info(
                "Shortest path computed",
                distance=len(edges),
                vertices_count=len(vertices),
            )

            return {
                'vertices': vertices,
                'edges': edges,
                'distance': len(edges),
            }

        except Exception as e:
            self.logger.error(
                "Shortest path computation failed",
                error=str(e),
            )
            raise

    def compute_coverage(
        self,
        items: List[str],
        target_collection: str,
        mapping_edge: str,
    ) -> float:
        """
        Compute coverage percentage (DRY).

        Used by:
        - ControlMappingService (coverage % per framework)
        - DefenseCoverageService (ATT&CK technique coverage)
        - RegulatoryDeltaService (framework migration impact)

        Args:
            items: List of document IDs to check (e.g., list of CVE IDs)
            target_collection: Target collection (e.g., "oscal_controls")
            mapping_edge: Edge collection linking items to targets

        Returns:
            float: Coverage percentage (0-100)

        Example:
            # Calculate % of CVEs mapped to NIST 800-53 controls
            coverage = self.compute_coverage(
                items=["vulnerabilities/cve-2021-44228", "vulnerabilities/cve-2021-45046"],
                target_collection="oscal_controls",
                mapping_edge="maps_to_requirement"
            )
        """
        self.logger.debug(
            "Computing coverage",
            items_count=len(items),
            target_collection=target_collection,
        )

        if not items:
            return 0.0

        query = f"""
        LET total = LENGTH(@items)
        LET covered = LENGTH(
            FOR item IN @items
                FOR v IN 1..1 OUTBOUND item {mapping_edge}
                    FILTER v._id LIKE CONCAT(@target_collection, "/%")
                    LIMIT 1
                    RETURN 1
        )
        RETURN (covered / total) * 100
        """

        try:
            cursor = self.db.aql_execute(
                query,
                bind_vars={
                    'items': items,
                    'target_collection': target_collection
                }
            )

            result = list(cursor)
            coverage = result[0] if result else 0.0

            self.logger.info(
                "Coverage computed",
                coverage_pct=f"{coverage:.2f}%",
                covered=int((coverage / 100) * len(items)),
                total=len(items),
            )

            return coverage

        except Exception as e:
            self.logger.error(
                "Coverage computation failed",
                error=str(e),
            )
            raise

    def aggregate_risk(
        self,
        findings: List[Dict],
        risk_weights: Optional[Dict[str, float]] = None,
    ) -> List[Dict]:
        """
        Aggregate risk scores across findings (DRY).

        Used by:
        - CompactionService (composite risk scoring)
        - PortfolioRiskService (aggregate EPSS trends)
        - DependencyRiskService (transitive risk propagation)

        Args:
            findings: List of finding dictionaries
            risk_weights: Optional custom weights for risk factors

        Returns:
            list: Findings sorted by risk_score (highest first)

        Default Risk Formula:
            risk_score = (
                kev_multiplier * (1 if KEV else 0) +
                epss_weight * epss_current +
                attack_path_weight * attack_path_count +
                control_gap_weight * control_gap_count
            )

        Example:
            findings = [
                {"cve_id": "CVE-2021-44228", "kev_listed": True, "epss_current": 0.95},
                {"cve_id": "CVE-2021-45046", "kev_listed": False, "epss_current": 0.12}
            ]
            sorted_findings = self.aggregate_risk(findings)
        """
        self.logger.debug(
            "Aggregating risk scores",
            findings_count=len(findings),
        )

        # Default risk weights
        default_weights = {
            'kev_multiplier': 3.0,  # KEV = 3x multiplier
            'epss_weight': 0.4,  # EPSS (0-1) weighted at 40%
            'attack_path_weight': 0.3,  # Attack path count weighted at 30%
            'control_gap_weight': 0.3,  # Control gap count weighted at 30%
        }

        weights = risk_weights or default_weights

        # Compute risk score for each finding
        for finding in findings:
            kev_score = weights['kev_multiplier'] if finding.get('kev_listed') else 0
            epss_score = weights['epss_weight'] * finding.get('epss_current', 0)
            attack_path_score = weights['attack_path_weight'] * finding.get('attack_path_count', 0)
            control_gap_score = weights['control_gap_weight'] * finding.get('control_gap_count', 0)

            finding['risk_score'] = (
                kev_score +
                epss_score +
                attack_path_score +
                control_gap_score
            )

        # Sort by risk descending
        sorted_findings = sorted(
            findings,
            key=lambda x: x.get('risk_score', 0),
            reverse=True
        )

        self.logger.info(
            "Risk aggregation complete",
            findings_count=len(sorted_findings),
            highest_risk=sorted_findings[0].get('risk_score') if sorted_findings else 0,
            lowest_risk=sorted_findings[-1].get('risk_score') if sorted_findings else 0,
        )

        return sorted_findings

    def get_neighbors(
        self,
        collection: str,
        key: str,
        edge_collection: str,
        direction: str = "OUTBOUND",
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """
        Get immediate neighbors of a node (1-hop traversal).

        Used by:
        - EnrichmentService (get CWEs for CVE)
        - CompactionService (get aliases for CVE)
        - Any service needing 1-hop relationships

        Args:
            collection: Node collection
            key: Node key
            edge_collection: Edge to traverse
            direction: OUTBOUND, INBOUND, or ANY
            filters: Optional filters on neighbor nodes

        Returns:
            list: Neighbor documents

        Example:
            # Get all CWEs for a CVE
            cwes = self.get_neighbors(
                collection="vulnerabilities",
                key="cve-2021-44228",
                edge_collection="has_weakness",
                direction="OUTBOUND"
            )
        """
        query = f"""
        FOR v IN 1..1 {direction} @start_doc {edge_collection}
        """

        if filters:
            filter_clauses = []
            for field, value in filters.items():
                if isinstance(value, str):
                    filter_clauses.append(f'FILTER v.{field} == "{value}"')
                else:
                    filter_clauses.append(f'FILTER v.{field} == {value}')
            query += "\n    " + "\n    ".join(filter_clauses)

        query += "\n    RETURN v"

        try:
            cursor = self.db.aql_execute(
                query,
                bind_vars={'start_doc': f'{collection}/{key}'}
            )

            neighbors = list(cursor)

            self.logger.debug(
                "Neighbors retrieved",
                collection=collection,
                key=key,
                neighbors_count=len(neighbors),
            )

            return neighbors

        except Exception as e:
            self.logger.error(
                "Neighbor retrieval failed",
                error=str(e),
            )
            raise
