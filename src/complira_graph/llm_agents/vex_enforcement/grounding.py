"""
VEX Evidence Grounding Module.

Provides evidence bundle models and justification-to-evidence mapping rules
for grounded VEX synthesis. Enforces that every VEX justification code is
backed by deterministic knowledge graph evidence.

Key Features:
- Evidence node abstraction with deterministic classification
- Justification-to-evidence mapping rules (REQUIRED_EVIDENCE_FOR_JUSTIFICATION)
- Evidence sufficiency validation before LLM synthesis

Compliance:
- FDA 524B: Justifications must cite deterministic evidence
- EU CRA: Evidence traceability required for regulatory submissions

Author: Complira Development Team
Version: 1.0
Ticket: vex-justification-enforcement
"""

from typing import List, Dict, Optional, Set, Any
from pydantic import BaseModel, Field
from enum import Enum


# ========== Evidence Node Model ==========


class EvidenceNode(BaseModel):
    """
    Single knowledge graph node with deterministic classification.

    Represents one piece of evidence from the knowledge graph with metadata
    about its deterministic vs probabilistic nature.

    Fields:
        - node_id: ArangoDB _id in collection/key format
        - node_key: ArangoDB document _key
        - collection: ArangoDB collection name
        - summary: Human-readable evidence summary
        - source: Evidence source system (e.g., "has_weakness", "kev", "epss")
        - deterministic: True if scanner/curated, False if LLM/ML-sourced
        - confidence: Optional confidence score (0.0-1.0) for probabilistic evidence

    Deterministic Classification Logic:
        - CWE evidence → Deterministic (curated MITRE graph)
        - KEV evidence → Deterministic (CISA official catalog)
        - EPSS evidence → Probabilistic (ML-based prediction)
        - LLM-sourced evidence → Probabilistic (generated content)

    Example:
        >>> node = EvidenceNode(
        ...     node_id="cwes/CWE_502",
        ...     node_key="CWE_502",
        ...     collection="cwes",
        ...     summary="CWE-502: Deserialization of Untrusted Data",
        ...     source="has_weakness",
        ...     deterministic=True
        ... )
    """
    node_id: str = Field(
        description="ArangoDB _id (collection/key format)",
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*/[a-zA-Z0-9_\-]+$"
    )
    node_key: str = Field(
        description="ArangoDB document _key"
    )
    collection: str = Field(
        description="ArangoDB collection name"
    )
    summary: str = Field(
        description="Human-readable evidence summary",
        min_length=1
    )
    source: str = Field(
        description="Evidence source system",
        min_length=1
    )
    deterministic: bool = Field(
        description="True if deterministic (scanner/curated), False if probabilistic (LLM/ML)"
    )
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence score for probabilistic evidence (0.0-1.0)"
    )

    @property
    def evidence_type(self) -> str:
        """
        Infer evidence type from collection name.

        Returns:
            Evidence type identifier (e.g., "cwe_evidence", "kev_evidence")
        """
        # Map collection names to evidence types
        type_mapping = {
            "cwes": "cwe_evidence",
            "kev": "kev_evidence",
            "vulnerabilities": "cve_metadata",
            "exploit_intelligence": "exploitability_evidence",
        }
        return type_mapping.get(self.collection, f"{self.collection}_evidence")

    @classmethod
    def from_evidence_model(
        cls,
        evidence: Any,
        collection: str,
        source: str,
        deterministic: Optional[bool] = None
    ) -> "EvidenceNode":
        """
        Create EvidenceNode from existing evidence Pydantic model.

        Args:
            evidence: Evidence model instance (CWEEvidence, KEVEvidence, etc.)
            collection: ArangoDB collection name
            source: Evidence source system
            deterministic: Override deterministic classification (if None, infer from collection)

        Returns:
            EvidenceNode instance

        Example:
            >>> from complira_graph.models.vex_evidence import CWEEvidence
            >>> cwe = CWEEvidence(cwe_id="CWE-502", graph_id="cwes/CWE_502", ...)
            >>> node = EvidenceNode.from_evidence_model(cwe, "cwes", "has_weakness")
        """
        # Infer deterministic classification if not provided
        if deterministic is None:
            deterministic = cls._infer_deterministic_from_collection(collection, source)

        # Extract node_id from graph_id field if available
        node_id = getattr(evidence, 'graph_id', None)
        if not node_id:
            # Fallback: construct from collection and key
            node_key = getattr(evidence, 'node_key', getattr(evidence, 'cwe_id', getattr(evidence, 'cve_id', 'unknown')))
            node_id = f"{collection}/{node_key}"

        # Extract node_key from node_id
        node_key = node_id.split('/')[-1] if '/' in node_id else node_id

        # Build summary from evidence
        summary = cls._build_summary(evidence)

        # Extract confidence if available
        confidence = getattr(evidence, 'confidence', None) or getattr(evidence, 'epss_score', None)

        return cls(
            node_id=node_id,
            node_key=node_key,
            collection=collection,
            summary=summary,
            source=source,
            deterministic=deterministic,
            confidence=confidence
        )

    @staticmethod
    def _infer_deterministic_from_collection(collection: str, source: str) -> bool:
        """
        Infer deterministic classification from collection/source.

        Deterministic Evidence (curated/official data):
            - cwes → True (MITRE curated graph)
            - kev → True (CISA official catalog)
            - vulnerabilities → True (NVD/GHSA official CVE data)

        Probabilistic Evidence (ML/LLM-sourced):
            - exploit_intelligence → False (EPSS ML model)
            - llm_* collections → False (LLM-generated)

        Args:
            collection: ArangoDB collection name
            source: Evidence source system

        Returns:
            True if deterministic, False if probabilistic
        """
        deterministic_collections = {"cwes", "kev", "vulnerabilities", "cwe"}
        probabilistic_collections = {"exploit_intelligence"}

        if collection in deterministic_collections:
            return True
        elif collection in probabilistic_collections:
            return False
        elif source.startswith("llm_") or source == "epss":
            return False
        else:
            # Default: assume deterministic for unknown collections
            return True

    @staticmethod
    def _build_summary(evidence: Any) -> str:
        """
        Build human-readable summary from evidence model.

        Args:
            evidence: Evidence model instance

        Returns:
            Summary string
        """
        # Try common summary fields
        if hasattr(evidence, 'description') and evidence.description:
            return evidence.description[:200]  # Truncate long descriptions
        elif hasattr(evidence, 'name') and evidence.name:
            return evidence.name
        elif hasattr(evidence, 'cwe_id'):
            return f"{evidence.cwe_id}: {getattr(evidence, 'name', 'CWE weakness')}"
        elif hasattr(evidence, 'cve_id'):
            return f"{evidence.cve_id}: {getattr(evidence, 'description', 'CVE vulnerability')[:100]}"
        else:
            return str(evidence)[:200]


# ========== Justification Code Enum ==========


class JustificationCode(str, Enum):
    """
    VEX justification codes (MVP subset).

    MVP scope supports only justification codes that can be backed by existing
    evidence types in the knowledge graph. Full CycloneDX justification code
    support requires SBOM and static analysis evidence (future enhancement).

    Supported Codes (MVP):
        - VULNERABLE_CODE_NOT_CONTROLLABLE: KEV + CWE evidence available
        - INLINE_MITIGATIONS_EXIST: KEV absence + low EPSS indicates mitigations

    Future Enhancement (requires SBOM/SAST):
        - component_not_present (requires SBOM evidence)
        - vulnerable_code_not_present (requires static analysis)
        - vulnerable_code_not_in_execute_path (requires reachability analysis)

    Standards Compliance:
        - CycloneDX VEX 1.5
        - CSAF 2.0 (compatible subset)
    """
    VULNERABLE_CODE_NOT_CONTROLLABLE = "vulnerable_code_cannot_be_controlled_by_adversary"
    INLINE_MITIGATIONS_EXIST = "inline_mitigations_already_exist"


# ========== Justification-to-Evidence Mapping Rules ==========


REQUIRED_EVIDENCE_FOR_JUSTIFICATION: Dict[JustificationCode, List[str]] = {
    JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE: [
        "kev_evidence",  # Requires KEV absence (not in CISA catalog)
        "cwe_evidence",  # Requires CWE classification for control analysis
    ],
    JustificationCode.INLINE_MITIGATIONS_EXIST: [
        "kev_evidence",  # Requires KEV absence (mitigations prevent exploitation)
        "exploitability_evidence",  # Requires low EPSS score
    ],
}


# ========== Evidence Bundle Model ==========


class VEXEvidenceBundle(BaseModel):
    """
    Pre-fetched evidence bundle for one CVE-component pair.

    Contains all knowledge graph evidence nodes for a single CVE affecting a
    specific component. Provides validation methods to check if evidence is
    sufficient to support specific VEX justification codes.

    Fields:
        - cve_id: CVE identifier
        - component_purl: Component Package URL
        - component_cpe: Optional CPE identifier
        - nodes: List of evidence nodes from graph traversal

    Validation Methods:
        - available_evidence_types(): Returns set of evidence types in bundle
        - deterministic_nodes(): Filters nodes to deterministic evidence only
        - can_support_justification(): Checks if bundle has required evidence for code

    Example:
        >>> bundle = VEXEvidenceBundle(
        ...     cve_id="CVE-2021-44228",
        ...     component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        ...     nodes=[cwe_node, kev_node, epss_node]
        ... )
        >>> bundle.can_support_justification(JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE)
        True
    """
    cve_id: str = Field(
        description="CVE identifier (e.g., CVE-2021-44228)",
        pattern=r"^CVE-\d{4}-\d{4,}$"
    )
    component_purl: str = Field(
        description="Component Package URL",
        min_length=1
    )
    component_cpe: Optional[str] = Field(
        None,
        description="Component CPE identifier (optional)"
    )
    nodes: List[EvidenceNode] = Field(
        default_factory=list,
        description="Evidence nodes from knowledge graph traversal"
    )

    def available_evidence_types(self) -> Set[str]:
        """
        Get set of evidence types available in bundle.

        Returns:
            Set of evidence type identifiers

        Example:
            >>> bundle.available_evidence_types()
            {'cwe_evidence', 'kev_evidence', 'exploitability_evidence'}
        """
        return {node.evidence_type for node in self.nodes}

    def deterministic_nodes(self) -> List[EvidenceNode]:
        """
        Filter nodes to deterministic evidence only.

        Returns:
            List of nodes where deterministic=True

        Example:
            >>> det_nodes = bundle.deterministic_nodes()
            >>> all(node.deterministic for node in det_nodes)
            True
        """
        return [node for node in self.nodes if node.deterministic]

    def probabilistic_nodes(self) -> List[EvidenceNode]:
        """
        Filter nodes to probabilistic evidence only.

        Returns:
            List of nodes where deterministic=False
        """
        return [node for node in self.nodes if not node.deterministic]

    def can_support_justification(self, code: JustificationCode) -> bool:
        """
        Check if bundle has required evidence for justification code.

        Validates that all required evidence types for the given justification
        code are present in the bundle. For most justifications, requires
        deterministic evidence. For INLINE_MITIGATIONS_EXIST, allows
        probabilistic exploitability evidence (EPSS) since it's ML-based.

        Args:
            code: VEX justification code to validate

        Returns:
            True if bundle has all required evidence, False otherwise

        Example:
            >>> bundle.can_support_justification(JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE)
            True
        """
        required_evidence_types = REQUIRED_EVIDENCE_FOR_JUSTIFICATION.get(code, [])
        available_types = self.available_evidence_types()

        # Check if all required evidence types are present
        for required_type in required_evidence_types:
            if required_type not in available_types:
                return False

        # Check if at least one deterministic node exists for each required type
        # Exception: INLINE_MITIGATIONS_EXIST allows probabilistic exploitability_evidence (EPSS)
        for required_type in required_evidence_types:
            type_nodes = [node for node in self.nodes if node.evidence_type == required_type]

            # Special case: INLINE_MITIGATIONS_EXIST allows probabilistic EPSS evidence
            if (code == JustificationCode.INLINE_MITIGATIONS_EXIST and
                required_type == "exploitability_evidence"):
                # Just check that exploitability evidence exists (deterministic or probabilistic)
                if not type_nodes:
                    return False
            else:
                # Default: Require at least one deterministic node
                if not any(node.deterministic for node in type_nodes):
                    return False

        return True

    def get_nodes_by_type(self, evidence_type: str) -> List[EvidenceNode]:
        """
        Get all nodes of a specific evidence type.

        Args:
            evidence_type: Evidence type identifier (e.g., "cwe_evidence")

        Returns:
            List of matching evidence nodes
        """
        return [node for node in self.nodes if node.evidence_type == evidence_type]

    def node_id_index(self) -> Set[str]:
        """
        Build set of all node IDs in bundle for fast lookup.

        Used for hallucination detection (validating cited node IDs exist).

        Returns:
            Set of node_id strings

        Example:
            >>> node_ids = bundle.node_id_index()
            >>> "cwes/CWE_502" in node_ids
            True
        """
        return {node.node_id for node in self.nodes}

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "cve_id": "CVE-2021-44228",
                "component_purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
                "component_cpe": "cpe:2.3:a:apache:log4j:2.14.1:*:*:*:*:*:*:*",
                "nodes": [
                    {
                        "node_id": "cwes/CWE_502",
                        "node_key": "CWE_502",
                        "collection": "cwes",
                        "summary": "CWE-502: Deserialization of Untrusted Data",
                        "source": "has_weakness",
                        "deterministic": True
                    },
                    {
                        "node_id": "kev/CVE_2021_44228",
                        "node_key": "CVE_2021_44228",
                        "collection": "kev",
                        "summary": "CVE-2021-44228 in CISA KEV catalog",
                        "source": "kev",
                        "deterministic": True
                    }
                ]
            }]
        }
    }
