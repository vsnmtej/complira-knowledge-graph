"""
Regulatory compliance models (SOLID compliant).

Implements:
- Single Responsibility Principle (SRP): Composition over God Object
- Interface Segregation Principle (ISP): Discriminated unions for requirement types
- Open/Closed Principle (OCP): Easy to extend with new frameworks

Usage:
    from complira_graph.models.regulatory import (
        RegulatoryFramework,
        NormativeRequirement,
        ClassificationRequirement,
        InformativeRequirement
    )

    # Create a normative requirement (CRA essential requirement)
    req = NormativeRequirement(
        identity=RequirementIdentity(
            key="CRA_I_1",
            requirement_id="Annex I, Part I, §1",
            framework="CRA"
        ),
        content=RequirementContent(
            title="Security by design",
            text="Products shall be designed, developed..."
        ),
        classification=RequirementClassification(
            requirement_type="essential",
            obligation_level="shall"
        )
    )

    # Convert to ArangoDB document (backward compatible)
    doc = req.to_arango_doc()
"""

from typing import List, Dict, Optional, Any, Literal, Union
from datetime import date, datetime
from pydantic import BaseModel, Field
import hashlib


# ========== Single Responsibility Components (SRP) ==========

class RequirementIdentity(BaseModel):
    """
    Requirement identification (SRP: Identity only).

    Responsibility: Uniquely identify a requirement.
    """
    key: str = Field(alias="_key", description="Unique requirement key (e.g., CRA_I_1_a)")
    requirement_id: str = Field(description="Original numbering from regulation (e.g., 'Annex I, Part I, §1(a)')")
    framework: str = Field(description="FK to regulatory_frameworks._key")

    class Config:
        populate_by_name = True


class RequirementHierarchy(BaseModel):
    """
    Hierarchical structure (SRP: Hierarchy only).

    Responsibility: Define parent-child relationships and depth.
    """
    parent_key: Optional[str] = Field(None, description="Parent requirement key for hierarchy")
    depth: int = Field(0, description="Depth in hierarchy (0=top-level, 1=article, 2=paragraph, etc.)")
    children_count: int = Field(0, description="Number of direct children (denormalized for performance)")


class RequirementContent(BaseModel):
    """
    Requirement text and metadata (SRP: Content only).

    Responsibility: Store the actual requirement text.
    """
    title: str = Field(description="Short descriptive title")
    text: str = Field(description="Full requirement text (verbatim from regulation)")
    text_hash: Optional[str] = Field(None, description="SHA-256 of text for change detection")

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of requirement text."""
        return hashlib.sha256(self.text.encode()).hexdigest()

    def model_post_init(self, __context: Any) -> None:
        """Automatically compute text_hash if not provided."""
        if self.text and not self.text_hash:
            self.text_hash = self.compute_hash()


class RequirementClassification(BaseModel):
    """
    Regulatory classification (SRP: Classification only).

    Responsibility: Classify the requirement type and obligation level.
    """
    requirement_type: Literal["essential", "procedural", "reporting", "documentation", "testing", "classification", "informative"]
    obligation_level: Literal["shall", "should", "may", "informative"]
    applies_to: List[str] = Field(default_factory=list, description="Who this applies to (manufacturer, distributor, etc.)")
    product_scope: List[str] = Field(default_factory=list, description="Product types this applies to (class_I, class_II, etc.)")


class EvidenceRequirement(BaseModel):
    """
    Single evidence type needed to satisfy a requirement.

    Responsibility: Define what evidence is required.
    """
    type: str = Field(description="Evidence type (SBOM, SAST, DAST, threat_model, etc.)")
    format: Optional[str] = Field(None, description="Required format (CycloneDX 1.6, SPDX 2.3, etc.)")
    required: bool = Field(True, description="Is this evidence required or optional?")
    description: str = Field("", description="Human-readable description of evidence requirement")
    scanner_tools: List[str] = Field(default_factory=list, description="Complira tools that produce this evidence")
    cwe_coverage: List[str] = Field(default_factory=list, description="CWEs this evidence must cover")
    manual_attestation: bool = Field(False, description="Requires human sign-off (no automated check)")

    # Structured validation spec (NOT raw AQL - prevents injection)
    validation_spec: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured query spec for automated validation",
        example={
            "collection": "sast_findings",
            "filters": {"tenant_id": "@tenant", "tool_name": ["semgrep", "bandit"]},
            "aggregation": "exists"
        }
    )


class EvidenceSpecification(BaseModel):
    """
    Evidence requirements (SRP: Evidence only).

    Responsibility: Define what evidence satisfies this requirement.
    """
    evidence_types: List[EvidenceRequirement] = Field(default_factory=list)
    testability: Literal["automated", "semi_automated", "manual_only", "not_testable"] = "semi_automated"
    verification_method: Optional[str] = Field(None, description="inspection | analysis | test | demonstration")


class RequirementTemporal(BaseModel):
    """
    Time-based attributes (SRP: Temporal only).

    Responsibility: Track effective dates and deadlines.
    """
    effective_date: Optional[date] = Field(None, description="When this requirement takes effect")
    deadline: Optional[date] = Field(None, description="Compliance deadline")
    transition_period: Optional[str] = Field(None, description="Transition period description (e.g., '36 months from entry into force')")


class RequirementProvenance(BaseModel):
    """
    Source and curation metadata (SRP: Provenance only).

    Responsibility: Track where this requirement came from and who curated it.
    """
    source: str = Field("manual_curation", description="manual_curation | llm_extraction | oscal_import | html_parsing")
    confidence: float = Field(1.0, description="Confidence score (1.0 for manual, 0.85+ for LLM)", ge=0.0, le=1.0)
    curator: Optional[str] = Field(None, description="Who curated this (human or agent name)")
    version: Optional[str] = Field(None, description="Requirement version (tracks amendments)")
    notes: Optional[str] = Field(None, description="Implementation notes, interpretation guidance")


# ========== Interface Segregation (ISP) - Discriminated Unions ==========

class BaseRequirement(BaseModel):
    """
    Minimal interface all requirements must implement.

    This is the abstract base - concrete types below implement only relevant fields.
    """
    identity: RequirementIdentity
    hierarchy: Optional[RequirementHierarchy] = None
    provenance: Optional[RequirementProvenance] = None

    def to_arango_doc(self) -> Dict[str, Any]:
        """
        Flatten to ArangoDB document (backward compatible with existing schema).

        Returns:
            Flattened dict ready for ArangoDB import
        """
        doc = {**self.identity.dict(by_alias=True)}

        if self.hierarchy:
            doc.update(self.hierarchy.dict())
        if self.provenance:
            doc.update(self.provenance.dict())

        return doc

    @classmethod
    def from_arango_doc(cls, doc: Dict[str, Any]) -> "BaseRequirement":
        """
        Reconstitute from flattened ArangoDB document.

        Args:
            doc: ArangoDB document

        Returns:
            Appropriate requirement subclass based on requirement_type
        """
        requirement_type = doc.get("requirement_type", "normative")

        if requirement_type == "classification":
            return ClassificationRequirement.from_arango_doc(doc)
        elif requirement_type == "informative":
            return InformativeRequirement.from_arango_doc(doc)
        else:
            return NormativeRequirement.from_arango_doc(doc)


class NormativeRequirement(BaseRequirement):
    """
    Full normative requirement with obligations (SHALL/SHOULD/MAY).

    Use for: CRA essential requirements, FDA 524B requirements, IEC 62304 clauses

    These requirements have:
    - Normative text (SHALL/SHOULD/MAY)
    - Evidence requirements
    - Deadlines
    - Testability
    """
    content: RequirementContent
    classification: RequirementClassification
    evidence: Optional[EvidenceSpecification] = None
    temporal: Optional[RequirementTemporal] = None

    def to_arango_doc(self) -> Dict[str, Any]:
        """Flatten with all normative fields."""
        doc = super().to_arango_doc()

        doc.update(self.content.dict())
        doc.update(self.classification.dict())

        if self.evidence:
            doc.update(self.evidence.dict())
        if self.temporal:
            temporal_dict = self.temporal.dict()
            # Convert date objects to ISO strings for JSON serialization
            if temporal_dict.get('effective_date'):
                temporal_dict['effective_date'] = temporal_dict['effective_date'].isoformat()
            if temporal_dict.get('deadline'):
                temporal_dict['deadline'] = temporal_dict['deadline'].isoformat()
            doc.update(temporal_dict)

        return doc

    @classmethod
    def from_arango_doc(cls, doc: Dict[str, Any]) -> "NormativeRequirement":
        """Reconstitute from ArangoDB document."""
        return cls(
            identity=RequirementIdentity(**{k: doc[k] for k in ["_key", "requirement_id", "framework"]}),
            hierarchy=RequirementHierarchy(
                parent_key=doc.get("parent_key"),
                depth=doc.get("depth", 0),
                children_count=doc.get("children_count", 0)
            ) if "parent_key" in doc or "depth" in doc else None,
            content=RequirementContent(
                title=doc["title"],
                text=doc["text"],
                text_hash=doc.get("text_hash")
            ),
            classification=RequirementClassification(
                requirement_type=doc["requirement_type"],
                obligation_level=doc["obligation_level"],
                applies_to=doc.get("applies_to", []),
                product_scope=doc.get("product_scope", [])
            ),
            evidence=EvidenceSpecification(
                evidence_types=doc.get("evidence_types", []),
                testability=doc.get("testability", "semi_automated"),
                verification_method=doc.get("verification_method")
            ) if "evidence_types" in doc else None,
            temporal=RequirementTemporal(
                effective_date=doc.get("effective_date"),
                deadline=doc.get("deadline"),
                transition_period=doc.get("transition_period")
            ) if any(k in doc for k in ["effective_date", "deadline", "transition_period"]) else None,
            provenance=RequirementProvenance(
                source=doc.get("source", "manual_curation"),
                confidence=doc.get("confidence", 1.0),
                curator=doc.get("curator"),
                version=doc.get("version"),
                notes=doc.get("notes")
            ) if "source" in doc else None
        )


class ClassificationRequirement(BaseRequirement):
    """
    Safety/security classification node (e.g., IEC 62304 Class A/B/C).

    Use for: IEC 62304 safety classes, ISO 62443 security levels, device risk classes

    These requirements:
    - Define classification levels (A/B/C, I/II/III, low/medium/high/critical)
    - Do NOT have normative text or evidence requirements
    - Are referenced by process events (triggers_classification edge)
    - Do NOT have deadlines or testability
    """
    classification_level: str = Field(description="Classification level (A | B | C | I | II | III)")
    risk_category: str = Field(description="Risk category (low | medium | high | critical)")
    description: str = Field(description="Classification criteria")

    # NO: evidence_types, NO: deadline, NO: testability
    # This is Interface Segregation - classifications don't have these fields

    def to_arango_doc(self) -> Dict[str, Any]:
        """Flatten with classification-specific fields only."""
        doc = super().to_arango_doc()

        doc.update({
            "requirement_type": "classification",
            "classification_level": self.classification_level,
            "risk_category": self.risk_category,
            "description": self.description
        })

        return doc

    @classmethod
    def from_arango_doc(cls, doc: Dict[str, Any]) -> "ClassificationRequirement":
        """Reconstitute from ArangoDB document."""
        return cls(
            identity=RequirementIdentity(**{k: doc[k] for k in ["_key", "requirement_id", "framework"]}),
            hierarchy=RequirementHierarchy(
                parent_key=doc.get("parent_key"),
                depth=doc.get("depth", 0),
                children_count=doc.get("children_count", 0)
            ) if "parent_key" in doc or "depth" in doc else None,
            classification_level=doc["classification_level"],
            risk_category=doc["risk_category"],
            description=doc["description"],
            provenance=RequirementProvenance(
                source=doc.get("source", "manual_curation"),
                confidence=doc.get("confidence", 1.0),
                curator=doc.get("curator"),
                version=doc.get("version"),
                notes=doc.get("notes")
            ) if "source" in doc else None
        )


class InformativeRequirement(BaseRequirement):
    """
    Informational/guidance requirement (non-normative).

    Use for: Regulatory preambles, guidance notes, informative annexes

    These requirements:
    - Have descriptive text (informative, not normative)
    - Do NOT have evidence requirements (can't be tested)
    - Do NOT have deadlines (not enforceable)
    - Used for context and guidance only
    """
    content: RequirementContent
    obligation_level: Literal["informative"] = "informative"

    # NO: evidence_types, NO: deadline

    def to_arango_doc(self) -> Dict[str, Any]:
        """Flatten with informative fields only."""
        doc = super().to_arango_doc()

        doc.update(self.content.dict())
        doc.update({
            "requirement_type": "informative",
            "obligation_level": "informative"
        })

        return doc

    @classmethod
    def from_arango_doc(cls, doc: Dict[str, Any]) -> "InformativeRequirement":
        """Reconstitute from ArangoDB document."""
        return cls(
            identity=RequirementIdentity(**{k: doc[k] for k in ["_key", "requirement_id", "framework"]}),
            hierarchy=RequirementHierarchy(
                parent_key=doc.get("parent_key"),
                depth=doc.get("depth", 0),
                children_count=doc.get("children_count", 0)
            ) if "parent_key" in doc or "depth" in doc else None,
            content=RequirementContent(
                title=doc["title"],
                text=doc["text"],
                text_hash=doc.get("text_hash")
            ),
            provenance=RequirementProvenance(
                source=doc.get("source", "manual_curation"),
                confidence=doc.get("confidence", 1.0),
                curator=doc.get("curator"),
                version=doc.get("version"),
                notes=doc.get("notes")
            ) if "source" in doc else None
        )


# Discriminated union type
RegulatoryRequirement = Union[NormativeRequirement, ClassificationRequirement, InformativeRequirement]


# ========== Regulatory Framework Model ==========

class RegulatoryFramework(BaseModel):
    """
    Top-level regulatory framework metadata.

    Responsibility: Define the framework itself (CRA, FDA 524B, IEC 62304, etc.)
    """
    key: str = Field(alias="_key", description="Framework identifier (CRA | FDA_524B | IEC_62304)")
    name: str = Field(description="Full framework name")
    short_name: str = Field(description="Short name for UI display")

    jurisdiction: Literal["EU", "US", "international", "industry"] = Field(description="Regulatory jurisdiction")
    issuing_body: str = Field(description="Organization that issued this (European Parliament, FDA, IEC, ISO, NIST)")
    document_type: Literal["regulation", "standard", "guidance", "framework"] = Field(description="Type of document")

    version: str = Field(description="Version identifier (Regulation (EU) 2024/2847, Rev 5, Edition 2.0)")
    publication_date: Optional[date] = Field(None, description="Official publication date")
    effective_date: Optional[date] = Field(None, description="When obligations begin")
    enforcement_date: Optional[date] = Field(None, description="When penalties apply")

    source_url: str = Field(description="Authoritative URL (EUR-Lex, FDA.gov, etc.)")
    source_format: str = Field(description="html | pdf | xml | oscal_json | yaml")
    machine_readable: bool = Field(False, description="Does official structured format exist?")

    applicability: Dict[str, Any] = Field(default_factory=dict, description="Product types and sectors this applies to")
    status: Literal["draft", "adopted", "in_force", "superseded", "withdrawn"] = Field("in_force")

    supersedes: Optional[str] = Field(None, description="_key of prior version if applicable")
    document_hash: Optional[str] = Field(None, description="SHA-256 of source document for change detection")

    last_ingested: Optional[datetime] = Field(None, description="When Complira last parsed this framework")
    ingestion_method: str = Field("manual_curation", description="manual_curation | llm_extraction | oscal_import | html_parsing | yaml_config")

    class Config:
        populate_by_name = True

    def to_arango_doc(self) -> Dict[str, Any]:
        """Convert to ArangoDB document."""
        doc = self.dict(by_alias=True)
        # Convert dates to ISO strings
        if self.publication_date:
            doc["publication_date"] = self.publication_date.isoformat()
        if self.effective_date:
            doc["effective_date"] = self.effective_date.isoformat()
        if self.enforcement_date:
            doc["enforcement_date"] = self.enforcement_date.isoformat()
        if self.last_ingested:
            doc["last_ingested"] = self.last_ingested.isoformat()

        return doc
