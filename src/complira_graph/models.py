"""
Pydantic models for all document collections in the knowledge graph.

Provides type validation, _key generation, and serialization for all 20 document types (v1.0 scope).
Models correspond 1:1 with collections defined in db.py.

Architecture:
- BaseDocument: Common fields for all documents (_key, timestamps)
- Specific models: One per collection (20 total)
- Deterministic _key generation: Ensures idempotent upserts
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import hashlib

from .utils.keys import (
    normalize_cve_id,
    normalize_cwe_id,
    normalize_attack_id,
    normalize_purl,
)


# ========== Base Models ==========

class BaseDocument(BaseModel):
    """Base class for all document models."""

    _key: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


# ========== Vulnerability Intelligence (6 models) ==========

class Vulnerability(BaseDocument):
    """
    CVE vulnerability record from NVD, OSV, GHSA.

    Collection: vulnerabilities
    """

    # Primary identifiers
    vulnerability_id: str  # CVE-2024-1234, GHSA-xxxx-yyyy-zzzz, etc.
    cve_id: Optional[str] = None  # Canonical CVE ID if available

    # Content
    summary: Optional[str] = None
    description: Optional[str] = None

    # Dates
    published: Optional[str] = None  # ISO datetime
    modified: Optional[str] = None
    last_modified: Optional[str] = None
    withdrawn: Optional[str] = None

    # CVSS Scores
    cvss_v2_score: Optional[float] = None
    cvss_v2_vector: Optional[str] = None
    cvss_v2_severity: Optional[str] = None
    cvss_v3_score: Optional[float] = None
    cvss_v3_vector: Optional[str] = None
    cvss_v3_severity: Optional[str] = None

    # Relationships (stored as arrays, edges created separately)
    cwe_ids: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)

    # References
    references: List[Dict[str, Any]] = Field(default_factory=list)

    # CPE matches (vulnerable configurations)
    cpe_matches: List[Dict[str, Any]] = Field(default_factory=list)

    # Affected packages (from OSV/GHSA)
    affected_packages: List[Dict[str, Any]] = Field(default_factory=list)

    # Metadata
    source: str  # nvd, osv, ghsa
    cisa_enriched: bool = False
    cisa_cwe_ids: List[str] = Field(default_factory=list)

    @staticmethod
    def generate_key(vulnerability_id: str) -> str:
        """Generate deterministic _key from vulnerability ID."""
        if vulnerability_id.startswith('CVE-'):
            return normalize_cve_id(vulnerability_id)
        # For non-CVE IDs (GHSA, PYSEC, etc.), replace hyphens
        return vulnerability_id.replace('-', '_')


class Weakness(BaseDocument):
    """
    CWE weakness record.

    Collection: weaknesses
    """

    cwe_id: str  # CWE-79
    name: str
    abstraction: str  # Pillar, Class, Base, Variant, Compound
    status: str  # Incomplete, Draft, Stable, Deprecated

    description: str
    extended_description: Optional[str] = None

    likelihood_of_exploit: Optional[str] = None

    # Structured data
    common_consequences: List[Dict[str, Any]] = Field(default_factory=list)
    detection_methods: List[Dict[str, Any]] = Field(default_factory=list)
    mitigations: List[Dict[str, Any]] = Field(default_factory=list)

    @staticmethod
    def generate_key(cwe_id: str) -> str:
        """Generate deterministic _key from CWE ID."""
        return normalize_cwe_id(cwe_id)


class KEVEntry(BaseDocument):
    """
    CISA Known Exploited Vulnerability entry.

    Collection: kev_entries
    """

    cve_id: str
    vendor_project: str
    product: str
    vulnerability_name: str
    short_description: str
    required_action: str

    date_added: Optional[str] = None  # ISO date
    due_date: Optional[str] = None

    known_ransomware_campaign_use: str  # Yes, No, Unknown
    notes: Optional[str] = None

    source: str = 'cisa_kev'

    @staticmethod
    def generate_key(cve_id: str) -> str:
        """Generate deterministic _key from CVE ID."""
        return normalize_cve_id(cve_id)


class VulnCheckKEVEntry(BaseDocument):
    """
    VulnCheck extended KEV data.

    Collection: vulncheck_kev_entries

    VulnCheck provides broader KEV coverage than CISA with additional enrichment:
    - Exploit database cross-references (XDB)
    - Reported exploitation evidence
    - Ransomware campaign tracking
    - Canary detection
    """

    cve_ids: List[str] = Field(default_factory=list)  # Can have multiple CVEs
    primary_cve_id: str
    vendor_project: str = ''
    product: str = ''
    vulnerability_name: str = ''
    short_description: str = ''
    required_action: str = ''
    known_ransomware_campaign_use: str = 'Unknown'
    date_added: Optional[str] = None
    due_date: Optional[str] = None
    cisa_date_added: Optional[str] = None  # If also in CISA KEV

    # VulnCheck enrichment
    vulncheck_xdb: List[Dict[str, Any]] = Field(default_factory=list)  # Exploit DB references
    vulncheck_reported_exploitation: List[Dict[str, Any]] = Field(default_factory=list)
    reported_exploited_by_canaries: bool = False

    source: str = 'vulncheck'

    @staticmethod
    def generate_key(cve_id: str) -> str:
        """Generate deterministic _key from primary CVE ID."""
        return f"{normalize_cve_id(cve_id)}_vulncheck"


class ExploitModule(BaseDocument):
    """
    Exploit module from Metasploit, ExploitDB, Nuclei, PoC-in-GitHub.

    Collection: exploit_modules
    """

    # Type-specific IDs
    module_path: Optional[str] = None  # Metasploit
    edb_id: Optional[str] = None  # ExploitDB
    template_id: Optional[str] = None  # Nuclei
    repository_url: Optional[str] = None  # PoC-in-GitHub

    name: Optional[str] = None
    description: Optional[str] = None

    # Metasploit-specific
    author: Optional[List[str]] = Field(default_factory=list)
    platform: Optional[List[str]] = Field(default_factory=list)
    arch: Optional[List[str]] = Field(default_factory=list)
    targets: Optional[List[str]] = Field(default_factory=list)
    rank: Optional[str] = None  # Excellent, Great, Good, Normal, Average, Low, Manual

    # ExploitDB-specific
    file_path: Optional[str] = None
    date_published: Optional[str] = None
    exploit_type: Optional[str] = None  # remote, local, webapps, dos
    port: Optional[str] = None

    # Nuclei-specific
    severity: Optional[str] = None  # info, low, medium, high, critical
    tags: List[str] = Field(default_factory=list)

    # PoC-in-GitHub-specific
    created_at: Optional[str] = None
    pushed_at: Optional[str] = None
    stars: Optional[int] = None
    watchers: Optional[int] = None

    # Common fields
    cve_ids: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    disclosure_date: Optional[str] = None

    source: str  # metasploit, exploitdb, nuclei, poc_in_github


class EPSSHistory(BaseDocument):
    """
    EPSS (Exploit Prediction Scoring System) time-series record.

    Collection: epss_history
    """

    cve_id: str
    cve_key: str

    epss_score: float  # 0.0 to 1.0
    percentile: float  # 0.0 to 1.0

    score_date: str  # ISO date (YYYY-MM-DD)

    source: str = 'epss'

    @staticmethod
    def generate_key(cve_id: str, score_date: str) -> str:
        """Generate deterministic _key from CVE ID and date."""
        cve_key = normalize_cve_id(cve_id)
        date_key = score_date.replace('-', '_')
        return f"{cve_key}_{date_key}"


# ========== Threat Intelligence (5 models) ==========

class ATTACKTechnique(BaseDocument):
    """
    MITRE ATT&CK technique or sub-technique.

    Collection: attack_techniques
    """

    technique_id: str  # T1059.001
    name: str
    description: str

    tactic_names: List[str] = Field(default_factory=list)  # execution, persistence, etc.

    is_subtechnique: bool
    parent_technique: Optional[str] = None  # T1059 for T1059.001

    platforms: List[str] = Field(default_factory=list)  # Windows, Linux, macOS, etc.
    data_sources: List[str] = Field(default_factory=list)
    detection: Optional[str] = None

    url: str
    stix_id: str
    deprecated: bool = False
    mitre_version: Optional[str] = None

    @staticmethod
    def generate_key(technique_id: str) -> str:
        """Generate deterministic _key from technique ID."""
        return normalize_attack_id(technique_id)


class AttackPattern(BaseDocument):
    """
    CAPEC attack pattern.

    Collection: attack_patterns
    """

    capec_id: str  # CAPEC-1
    name: str
    abstraction: str  # Meta, Standard, Detailed
    status: str

    description: str

    likelihood: Optional[str] = None
    severity: Optional[str] = None

    prerequisites: List[str] = Field(default_factory=list)
    mitigations: List[str] = Field(default_factory=list)
    execution_flow: List[Dict[str, Any]] = Field(default_factory=list)

    attack_technique_ids: List[str] = Field(default_factory=list)  # ATT&CK mappings

    @staticmethod
    def generate_key(capec_id: str) -> str:
        """Generate deterministic _key from CAPEC ID."""
        return capec_id.replace('-', '_')


class ATLASTechnique(BaseDocument):
    """
    ATLAS (AI/ML attack) technique.

    Collection: atlas_techniques
    """

    atlas_id: str  # AML.T0001
    name: str
    description: str

    tactic_ids: List[str] = Field(default_factory=list)
    tactic_names: List[str] = Field(default_factory=list)

    platforms: List[str] = Field(default_factory=list)

    case_studies: List[Dict[str, str]] = Field(default_factory=list)
    mitigations: List[Dict[str, str]] = Field(default_factory=list)
    detections: List[Dict[str, str]] = Field(default_factory=list)
    references: List[Dict[str, str]] = Field(default_factory=list)

    @staticmethod
    def generate_key(atlas_id: str) -> str:
        """Generate deterministic _key from ATLAS ID."""
        return atlas_id.replace('.', '_')


class D3FENDTechnique(BaseDocument):
    """
    D3FEND defensive technique.

    Collection: d3fend_techniques
    """

    d3fend_id: str
    name: str
    description: Optional[str] = None

    parent_technique: Optional[str] = None
    uri: str

    @staticmethod
    def generate_key(d3fend_id: str) -> str:
        """Generate deterministic _key from D3FEND ID."""
        return d3fend_id.replace('.', '_')


class ThreatGroup(BaseDocument):
    """
    MITRE ATT&CK threat actor group.

    Collection: threat_groups
    """

    group_id: str  # G0001
    name: str
    description: str

    aliases: List[str] = Field(default_factory=list)

    url: str
    stix_id: str
    mitre_version: Optional[str] = None

    @staticmethod
    def generate_key(group_id: str) -> str:
        """Generate deterministic _key from group ID."""
        return group_id  # Already in valid format


# ========== Compliance & Frameworks (4 models) ==========

class RegulatoryRequirement(BaseDocument):
    """
    Generic regulatory requirement (placeholder for future).

    Collection: regulatory_requirements
    """

    requirement_id: str
    framework: str  # GDPR, HIPAA, SOC2, etc.
    title: str
    description: str

    category: Optional[str] = None
    control_objectives: List[str] = Field(default_factory=list)


class OSCALControl(BaseDocument):
    """
    NIST 800-53 control in OSCAL format.

    Collection: oscal_controls
    """

    control_id: str  # ac-1
    title: str

    family_id: str
    family_title: str

    parent_control_id: Optional[str] = None  # For enhancements

    statement: Optional[str] = None
    guidance: Optional[str] = None

    parameters: List[Dict[str, Any]] = Field(default_factory=list)

    priority: Optional[str] = None  # P1, P2, P3
    baseline_impact: List[str] = Field(default_factory=list)  # LOW, MODERATE, HIGH
    related_controls: List[str] = Field(default_factory=list)

    @staticmethod
    def generate_key(control_id: str) -> str:
        """Generate deterministic _key from control ID."""
        return control_id.replace('.', '_')


class SCFControl(BaseDocument):
    """
    Secure Controls Framework control.

    Collection: scf_controls
    """

    scf_id: str  # SCF-001
    title: str
    description: str

    domain: Optional[str] = None
    subdomain: Optional[str] = None
    version: Optional[str] = None

    # Framework mappings
    nist_800_53_mappings: List[str] = Field(default_factory=list)
    iso_27001_mappings: List[str] = Field(default_factory=list)
    pci_dss_mappings: List[str] = Field(default_factory=list)
    cis_controls_mappings: List[str] = Field(default_factory=list)

    @staticmethod
    def generate_key(scf_id: str) -> str:
        """Generate deterministic _key from SCF ID."""
        return scf_id.replace('-', '_')


class OpenCRENode(BaseDocument):
    """
    OpenCRE (Open Common Requirement Enumeration) node.

    Collection: opencre_nodes
    """

    cre_id: str
    name: str
    description: Optional[str] = None
    cre_type: str  # CRE, Standard, etc.

    linked_standards: Dict[str, List[Dict[str, str]]] = Field(default_factory=dict)

    @staticmethod
    def generate_key(cre_id: str) -> str:
        """Generate deterministic _key from CRE ID."""
        return str(cre_id).replace('-', '_')


# ========== Supply Chain & Components (5 models) ==========

class Component(BaseDocument):
    """
    Software component (package) from deps.dev.

    Collection: components
    """

    purl: str  # Package URL: pkg:npm/lodash@4.17.21
    ecosystem: str  # npm, pypi, maven, cargo, etc.
    name: str

    latest_version: Optional[str] = None
    versions_count: int = 0

    source: str = 'deps_dev'

    @staticmethod
    def generate_key(purl: str) -> str:
        """Generate deterministic _key from PURL."""
        return normalize_purl(purl)


class CPEEntry(BaseDocument):
    """
    CPE (Common Platform Enumeration) entry (placeholder for future).

    Collection: cpe_entries
    """

    cpe_uri: str  # cpe:2.3:a:vendor:product:version:*:*:*:*:*:*:*
    vendor: str
    product: str
    version: Optional[str] = None

    @staticmethod
    def generate_key(cpe_uri: str) -> str:
        """Generate deterministic _key from CPE URI."""
        # Hash long CPE URIs
        if len(cpe_uri) > 200:
            return f"cpe_{hashlib.sha256(cpe_uri.encode()).hexdigest()[:32]}"
        return cpe_uri.replace(':', '_').replace('.', '_')


class ScorecardResult(BaseDocument):
    """
    OpenSSF Scorecard security assessment result.

    Collection: scorecard_results
    """

    repository: str  # github.com/owner/repo
    commit: str

    scorecard_date: str
    scorecard_version: str

    overall_score: float

    checks: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: List[Any] = Field(default_factory=list)

    source: str = 'openssf_scorecard'


class License(BaseDocument):
    """
    SPDX license record.

    Collection: licenses
    """

    license_id: str  # Apache-2.0, MIT
    name: str

    reference: str
    reference_number: int = 0
    details_url: str
    see_also: List[str] = Field(default_factory=list)

    is_osi_approved: bool = False
    is_fsf_libre: bool = False
    is_deprecated: bool = False

    @staticmethod
    def generate_key(license_id: str) -> str:
        """Generate deterministic _key from license ID."""
        return license_id.replace('.', '_').replace('-', '_').replace('+', '_plus')


class PackageHealth(BaseDocument):
    """
    Package health metrics from ecosyste.ms and endoflife.date.

    Collection: package_health
    """

    purl: Optional[str] = None
    ecosystem: Optional[str] = None
    name: Optional[str] = None

    # Ecosyste.ms metrics
    health_score: Optional[float] = None
    scorecard_date: Optional[str] = None

    repository_url: Optional[str] = None
    stars: Optional[int] = None
    forks: Optional[int] = None
    open_issues: Optional[int] = None

    latest_release: Optional[str] = None
    latest_release_date: Optional[str] = None
    downloads: Optional[int] = None

    # endoflife.date metrics
    product_id: Optional[str] = None
    cycle_version: Optional[str] = None
    release_date: Optional[str] = None
    eol_date: Optional[str] = None
    support_end_date: Optional[str] = None
    is_lts: Optional[bool] = None
    is_active: Optional[bool] = None
    eol_status: Optional[str] = None  # active, end_of_support, end_of_life

    source: str  # ecosystems, endoflife_date


# ========== Multi-Tenant SaaS (3 models - Phase 0) ==========

class CustomerProfile(BaseDocument):
    """
    Customer profile for multi-tenant SaaS.

    Collection: customer_profiles (reference database)

    Stored in reference database, shared across all customers.
    Used by authentication layer to validate API keys and route to customer databases.
    """

    _key: str = Field(
        ...,
        description="Customer identifier (unique)",
        min_length=1,
        max_length=100,
    )
    name: str = Field(
        ...,
        description="Customer name (e.g., 'Acme Corp')",
        min_length=1,
        max_length=255,
    )
    api_key_hash: str = Field(
        ...,
        description="Bcrypt hash of API key",
        min_length=60,
        max_length=60,  # Bcrypt hashes are always 60 chars
    )
    database_name: str = Field(
        ...,
        description="Customer database name (e.g., 'complira_customer_acme')",
        min_length=1,
        max_length=128,
    )
    tier: str = Field(
        default="free",
        description="Subscription tier (free, pro, enterprise)",
    )
    created_at: Optional[str] = Field(
        None,
        description="Profile creation timestamp (ISO 8601)",
    )

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        """Validate tier is one of allowed values."""
        allowed_tiers = ["free", "pro", "enterprise"]
        if v not in allowed_tiers:
            raise ValueError(f"tier must be one of {allowed_tiers}")
        return v

    @field_validator("database_name")
    @classmethod
    def validate_database_name(cls, v: str) -> str:
        """Validate database name format."""
        if not v.startswith("complira_customer_"):
            raise ValueError("database_name must start with 'complira_customer_'")
        return v

    @staticmethod
    def generate_key(customer_id: str) -> str:
        """Generate deterministic _key from customer ID."""
        return customer_id.lower().replace(' ', '_').replace('-', '_')


class ScanSession(BaseDocument):
    """
    Scan session metadata.

    Collection: scan_sessions (customer database)

    Represents a single scan execution from CI/CD pipeline.
    Stored in customer-specific database for data isolation.
    """

    _key: Optional[str] = Field(
        None,
        description="Session identifier (auto-generated if not provided)",
    )
    customer_id: str = Field(
        ...,
        description="Customer identifier",
        min_length=1,
    )
    tool_name: str = Field(
        ...,
        description="Scanner tool name (e.g., 'Snyk', 'Trivy', 'Semgrep')",
        min_length=1,
    )
    tool_version: str = Field(
        ...,
        description="Scanner tool version",
        min_length=1,
    )
    scan_timestamp: str = Field(
        ...,
        description="Scan execution timestamp (ISO 8601)",
    )
    scan_type: str = Field(
        ...,
        description="Scan format type (sarif, cyclonedx)",
    )
    status: str = Field(
        default="processing",
        description="Scan processing status (pending, processing, completed, failed)",
    )
    findings_count: int = Field(
        default=0,
        description="Number of findings in this scan",
        ge=0,
    )
    components_count: int = Field(
        default=0,
        description="Number of SBOM components in this scan",
        ge=0,
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional scan metadata",
    )
    created_at: Optional[str] = Field(
        None,
        description="Session creation timestamp (ISO 8601)",
    )
    updated_at: Optional[str] = Field(
        None,
        description="Session last update timestamp (ISO 8601)",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is one of allowed values."""
        allowed_statuses = ["pending", "processing", "completed", "failed"]
        if v not in allowed_statuses:
            raise ValueError(f"status must be one of {allowed_statuses}")
        return v

    @field_validator("scan_type")
    @classmethod
    def validate_scan_type(cls, v: str) -> str:
        """Validate scan_type is supported."""
        supported_types = ["sarif", "cyclonedx"]
        if v not in supported_types:
            raise ValueError(f"scan_type must be one of {supported_types}")
        return v


class ScanFinding(BaseDocument):
    """
    Individual scan finding (vulnerability or issue).

    Collection: scan_findings (customer database)

    Represents a single vulnerability or issue discovered by scanner.
    Stored in customer-specific database for data isolation.
    """

    _key: Optional[str] = Field(
        None,
        description="Finding identifier (auto-generated if not provided)",
    )
    customer_id: str = Field(
        ...,
        description="Customer identifier",
        min_length=1,
    )
    scan_session_id: str = Field(
        ...,
        description="Scan session _key this finding belongs to",
        min_length=1,
    )
    cve_id: Optional[str] = Field(
        None,
        description="CVE identifier (e.g., 'CVE-2021-44228') if applicable",
    )
    severity: str = Field(
        ...,
        description="Normalized severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO, UNKNOWN)",
    )
    description: str = Field(
        ...,
        description="Finding description",
        min_length=1,
    )
    location: str = Field(
        ...,
        description="Finding location (file:line or component@version)",
        min_length=1,
    )
    tool_name: str = Field(
        ...,
        description="Scanner tool that reported this finding",
        min_length=1,
    )
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Original finding data from scanner",
    )
    created_at: Optional[str] = Field(
        None,
        description="Finding creation timestamp (ISO 8601)",
    )

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """Validate severity is normalized."""
        allowed_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]
        if v.upper() not in allowed_severities:
            raise ValueError(f"severity must be one of {allowed_severities}")
        return v.upper()

    @field_validator("cve_id")
    @classmethod
    def validate_cve_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate CVE ID format if provided."""
        if v and not v.upper().startswith("CVE-"):
            raise ValueError("cve_id must start with 'CVE-' if provided")
        return v.upper() if v else None


# ========== Model Registry ==========

MODEL_REGISTRY: Dict[str, type[BaseDocument]] = {
    'vulnerabilities': Vulnerability,
    'weaknesses': Weakness,
    'kev_entries': KEVEntry,
    'vulncheck_kev_entries': VulnCheckKEVEntry,
    'exploit_modules': ExploitModule,
    'epss_history': EPSSHistory,
    'attack_techniques': ATTACKTechnique,
    'attack_patterns': AttackPattern,
    'atlas_techniques': ATLASTechnique,
    'd3fend_techniques': D3FENDTechnique,
    'threat_groups': ThreatGroup,
    'regulatory_requirements': RegulatoryRequirement,
    'oscal_controls': OSCALControl,
    'scf_controls': SCFControl,
    'opencre_nodes': OpenCRENode,
    'components': Component,
    'cpe_entries': CPEEntry,
    'scorecard_results': ScorecardResult,
    'licenses': License,
    'package_health': PackageHealth,
    # Multi-Tenant SaaS (Phase 0)
    'customer_profiles': CustomerProfile,
    'scan_sessions': ScanSession,
    'scan_findings': ScanFinding,
}


def get_model(collection_name: str) -> type[BaseDocument]:
    """
    Get Pydantic model class for a collection.

    Args:
        collection_name: Name of the collection

    Returns:
        Pydantic model class

    Raises:
        KeyError: If collection not found
    """
    if collection_name not in MODEL_REGISTRY:
        raise KeyError(f"No model registered for collection: {collection_name}")

    return MODEL_REGISTRY[collection_name]
