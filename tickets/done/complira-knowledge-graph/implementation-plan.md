# Implementation Plan: Complira Knowledge Graph Engine

**Status:** `Active`
**Stage:** `6 - Implementation`
**Scope:** `LARGE`
**Last Updated:** 2026-02-28
**Code Edit Permission:** `Unlocked`

---

## Overview

This document provides the detailed implementation plan for the Complira Knowledge Graph Engine. The implementation follows the 7-layer architecture defined in `proposed-design.md` and implements the runtime behaviors documented in `future-state-runtime-call-stack.md`.

**Total Modules:** 30+ Python modules across 7 layers
**Total Lines of Code (estimated):** ~12,000-15,000 LOC
**Implementation Order:** Bottom-up (Layer 1 → Layer 7)
**v1.0 Scope:** Open data sources only (20 doc collections, 21 edge collections)
**Deferred to v2.0:** Scanner evidence, process evidence, document provenance (16 doc, 20 edge collections)

---

## Implementation Phases

### Phase 1: Foundation (Layers 1-2)
**Estimated Effort:** 3-4 days
**Dependencies:** None
**Goal:** Establish database connection, schema, and configuration management

### Phase 2: Data Ingestion (Layer 3)
**Estimated Effort:** 10-12 days
**Dependencies:** Phase 1 complete
**Goal:** Implement all 23 deterministic ingestion agents

### Phase 3: LLM Enrichment (Layer 4)
**Estimated Effort:** 4-5 days
**Dependencies:** Phase 2 complete
**Goal:** Implement 9 LLM enrichment agents with provenance tracking

### Phase 4: Orchestration (Layer 5)
**Estimated Effort:** 3-4 days
**Dependencies:** Phases 2-3 complete
**Goal:** Implement Prefect flows, DAG builder, and schedulers

### Phase 5: User Interface (Layer 6)
**Estimated Effort:** 2-3 days
**Dependencies:** Phase 4 complete
**Goal:** Implement CLI commands for seed, update, query, VEX generation

### Phase 6: Observability (Layer 7)
**Estimated Effort:** 2-3 days
**Dependencies:** All phases
**Goal:** Implement Prometheus metrics, Grafana dashboards, structured logging

---

## Code Quality Principles: SOLID & DRY

### SOLID Principles Compliance

**✅ Single Responsibility Principle (SRP)**
- Each agent class handles exactly ONE data source
- Database layer (`db.py`) handles ONLY connection/schema, not business logic
- LLM agents handle ONLY enrichment, not data ingestion
- CLI layer handles ONLY user interaction, not orchestration

**✅ Open/Closed Principle (OCP)**
- `BaseIngestionAgent` and `BaseLLMAgent` are open for extension, closed for modification
- New data sources = new agent subclass (no base class changes)
- New LLM enrichment = new LLM agent subclass

**✅ Liskov Substitution Principle (LSP)**
- All ingestion agents are interchangeable via `BaseIngestionAgent` interface
- Orchestrator can run any agent through `agent.run()` without knowing concrete type
- LLM agents are interchangeable via `BaseLLMAgent` interface

**✅ Interface Segregation Principle (ISP)**
- Deterministic agents: `fetch_data()`, `transform_data()`, `load_data()`, `run()`
- LLM agents: `find_gaps()`, `enrich()`, `validate()`, `persist()` (different interface)
- No "fat interfaces" forcing unused methods

**✅ Dependency Inversion Principle (DIP)**
- Agents depend on `StandardDatabase` abstraction (ArangoDB interface), not concrete implementation
- Agents depend on `Anthropic` client interface, not implementation details
- Orchestrator depends on agent abstractions, not concrete agent classes

---

### DRY (Don't Repeat Yourself) Improvements

**Problem:** 23 ingestion agents + 9 LLM agents would result in significant code duplication if not carefully designed.

**Solution:** Layered utility modules for common patterns.

---

#### Module: `src/complira_graph/utils/http_client.py`
**Purpose:** Centralized HTTP client creation with rate limiting and retries
**LOC:** ~150 lines

```python
from dataclasses import dataclass
from functools import wraps
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from ratelimit import limits, RateLimitException

@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    calls: int           # Max calls
    period: int          # Period in seconds
    service_name: str    # For circuit breaker tracking

@dataclass
class RetryConfig:
    """Retry configuration"""
    max_attempts: int = 3
    min_wait: int = 2    # seconds
    max_wait: int = 10   # seconds

class ResilientHTTPClient:
    """HTTP client with built-in rate limiting, retries, and circuit breaker"""

    def __init__(
        self,
        rate_limit: RateLimitConfig,
        retry_config: RetryConfig = RetryConfig(),
        timeout: float = 30.0,
        circuit_breaker: bool = False
    ):
        self.rate_limit = rate_limit
        self.retry_config = retry_config
        self.client = httpx.Client(timeout=timeout)
        self.circuit_breaker_enabled = circuit_breaker

    @property
    def get(self):
        """Get method with automatic rate limiting and retries"""
        func = self._make_request("GET")
        func = self._apply_rate_limit(func)
        func = self._apply_retry(func)
        if self.circuit_breaker_enabled:
            func = self._apply_circuit_breaker(func)
        return func

    def _make_request(self, method: str):
        """Core request method"""
        def request(url: str, **kwargs):
            response = self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        return request

    def _apply_rate_limit(self, func):
        """Apply rate limiting decorator"""
        return limits(
            calls=self.rate_limit.calls,
            period=self.rate_limit.period
        )(func)

    def _apply_retry(self, func):
        """Apply retry decorator"""
        return retry(
            stop=stop_after_attempt(self.retry_config.max_attempts),
            wait=wait_exponential(
                multiplier=1,
                min=self.retry_config.min_wait,
                max=self.retry_config.max_wait
            )
        )(func)

    def _apply_circuit_breaker(self, func):
        """Apply circuit breaker if enabled"""
        from .circuit_breaker import circuit_breaker
        return circuit_breaker(
            failure_threshold=5,
            recovery_timeout=1800,
            service_name=self.rate_limit.service_name
        )(func)

# Factory function for agent use
def create_http_client(
    service_name: str,
    calls_per_period: int,
    period_seconds: int,
    circuit_breaker: bool = False
) -> ResilientHTTPClient:
    """
    Factory function to create HTTP client with sensible defaults

    Example:
        client = create_http_client("nvd", calls_per_period=50, period_seconds=30, circuit_breaker=True)
        response = client.get("https://services.nvd.nist.gov/rest/json/cves/2.0")
    """
    return ResilientHTTPClient(
        rate_limit=RateLimitConfig(calls_per_period, period_seconds, service_name),
        circuit_breaker=circuit_breaker
    )
```

**Usage in agents:**
```python
# Before (repeated in every agent):
@limits(calls=50, period=30)
@retry(stop=stop_after_attempt(3))
@circuit_breaker(...)
def fetch_data(self):
    self.client = httpx.Client(timeout=30.0)
    response = self.client.get(url)
    response.raise_for_status()

# After (DRY):
from complira_graph.utils.http_client import create_http_client

class NVDAgent(BaseIngestionAgent):
    def __init__(self, db):
        super().__init__(db)
        self.client = create_http_client("nvd", calls_per_period=50, period_seconds=30, circuit_breaker=True)

    def fetch_data(self):
        response = self.client.get("https://services.nvd.nist.gov/rest/json/cves/2.0")
        return response.json()
```

---

#### Module: `src/complira_graph/utils/keys.py`
**Purpose:** Deterministic key generation and normalization
**LOC:** ~100 lines

```python
import re
from typing import Optional

def normalize_cve_id(cve_id: str) -> str:
    """
    CVE-2024-1234 → CVE_2024_1234
    """
    return cve_id.replace("-", "_")

def normalize_cwe_id(cwe_id: str) -> str:
    """
    CWE-79 → CWE_79
    """
    return cwe_id.replace("-", "_")

def normalize_attack_id(attack_id: str) -> str:
    """
    T1059.001 → T1059_001
    """
    return attack_id.replace(".", "_")

def normalize_capec_id(capec_id: str) -> str:
    """
    CAPEC-66 → CAPEC_66
    """
    return capec_id.replace("-", "_")

def normalize_purl(purl: str) -> str:
    """
    pkg:pypi/django@4.2.0 → pkg_pypi_django_4_2_0
    Hash-based for very long PURLs
    """
    if len(purl) > 254:  # ArangoDB _key max length
        import hashlib
        return f"purl_{hashlib.sha256(purl.encode()).hexdigest()[:32]}"
    return re.sub(r'[^a-zA-Z0-9_]', '_', purl)

def normalize_ghsa_id(ghsa_id: str) -> str:
    """
    GHSA-xxxx-xxxx-xxxx → GHSA_xxxx_xxxx_xxxx
    """
    return ghsa_id.replace("-", "_")

# Generic normalizer
def normalize_key(id_value: str, id_type: str) -> str:
    """
    Dispatch to appropriate normalizer based on type
    """
    normalizers = {
        "cve": normalize_cve_id,
        "cwe": normalize_cwe_id,
        "attack": normalize_attack_id,
        "capec": normalize_capec_id,
        "purl": normalize_purl,
        "ghsa": normalize_ghsa_id,
    }
    normalizer = normalizers.get(id_type)
    if normalizer:
        return normalizer(id_value)
    # Default: replace hyphens and dots with underscores
    return id_value.replace("-", "_").replace(".", "_")
```

**Usage:**
```python
from complira_graph.utils.keys import normalize_key

# In transform_data():
_key = normalize_key(cve["id"], "cve")  # CVE-2024-1234 → CVE_2024_1234
```

---

#### Module: `src/complira_graph/utils/transforms.py`
**Purpose:** Common transformation patterns
**LOC:** ~200 lines

```python
from typing import Iterator, Any, Callable
from datetime import datetime

def extract_nested_array(data: dict, path: str, default: list = None) -> list:
    """
    Extract nested array from JSON path

    Example:
        extract_nested_array(data, "vulnerabilities") → data.get("vulnerabilities", [])
        extract_nested_array(data, "cve.weaknesses") → data.get("cve", {}).get("weaknesses", [])
    """
    if "." not in path:
        return data.get(path, default or [])

    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default or [])
        else:
            return default or []
    return current if isinstance(current, list) else [current]

def safe_date_parse(date_str: str | None, default: datetime | None = None) -> datetime | None:
    """
    Parse ISO datetime with fallback
    """
    if not date_str:
        return default
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return default

def batch_iterator(items: Iterator[Any], batch_size: int = 10000) -> Iterator[list[Any]]:
    """
    Batch items for bulk import

    Usage:
        for batch in batch_iterator(transform_data(raw_data), batch_size=10000):
            db.collection("vulnerabilities").import_bulk(batch)
    """
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch

def safe_extract(data: dict, key: str, default: Any = None, transform: Callable = None) -> Any:
    """
    Safe extraction with optional transformation

    Example:
        cvss_score = safe_extract(cve, "metrics.cvssMetricV31[0].cvssData.baseScore", default=0.0, transform=float)
    """
    value = data.get(key, default)
    if transform and value is not None:
        try:
            return transform(value)
        except (ValueError, TypeError):
            return default
    return value
```

**Usage:**
```python
from complira_graph.utils.transforms import extract_nested_array, batch_iterator, safe_date_parse

def transform_data(self, raw_data):
    for cve_item in extract_nested_array(raw_data, "vulnerabilities"):
        yield {
            "_key": normalize_key(cve_item["cve"]["id"], "cve"),
            "published": safe_date_parse(cve_item["cve"]["published"]),
            # ...
        }

def load_data(self, records):
    for batch in batch_iterator(records, batch_size=10000):
        self.db.collection("vulnerabilities").import_bulk(batch, on_duplicate="update")
```

---

#### Module: `src/complira_graph/utils/circuit_breaker.py`
**Purpose:** Reusable circuit breaker implementation
**LOC:** ~200 lines

```python
from enum import Enum
from functools import wraps
from datetime import datetime, timedelta
import threading

class CircuitState(Enum):
    CLOSED = 0      # Normal operation
    OPEN = 1        # Failures exceeded threshold, reject requests
    HALF_OPEN = 2   # Recovery attempt

class CircuitBreaker:
    """
    Reusable circuit breaker for unreliable external services
    """
    def __init__(self, failure_threshold: int, recovery_timeout: int, service_name: str):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self.service_name = service_name
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        self.lock = threading.Lock()

    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        with self.lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerOpen(f"Circuit breaker open for {self.service_name}")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed for recovery attempt"""
        if not self.last_failure_time:
            return False
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)

    def _on_success(self):
        """Reset failure count on success"""
        with self.lock:
            self.failure_count = 0
            self.state = CircuitState.CLOSED

    def _on_failure(self):
        """Increment failure count, open circuit if threshold exceeded"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open"""
    pass

# Global registry for circuit breakers per service
_circuit_breakers = {}

def circuit_breaker(failure_threshold: int, recovery_timeout: int, service_name: str):
    """
    Decorator for circuit breaker

    Usage:
        @circuit_breaker(failure_threshold=5, recovery_timeout=1800, service_name="nvd")
        def fetch_nvd_data():
            # ...
    """
    def decorator(func):
        # Get or create circuit breaker for this service
        if service_name not in _circuit_breakers:
            _circuit_breakers[service_name] = CircuitBreaker(
                failure_threshold, recovery_timeout, service_name
            )
        cb = _circuit_breakers[service_name]

        @wraps(func)
        def wrapper(*args, **kwargs):
            return cb.call(func, *args, **kwargs)
        return wrapper
    return decorator
```

---

### DRY Benefits Summary

**Before DRY improvements:**
- 32 agents × 50 lines of boilerplate = **1,600 lines of duplicated code**
- Inconsistent error handling across agents
- Difficult to change rate limiting logic globally

**After DRY improvements:**
- Shared utilities: ~650 lines
- Agent-specific code only: ~50-200 lines per agent
- **Total reduction: ~1,000 lines**
- Centralized error handling and resilience patterns
- Single source of truth for HTTP client, key normalization, circuit breakers

---

## Layer-by-Layer Implementation Plan

---

## Layer 1: Database Foundation

### Module 1.1: `src/complira_graph/db.py`
**Purpose:** ArangoDB connection management and schema initialization
**LOC:** ~400 lines
**Dependencies:** None
**Priority:** P0 (blocking)

**Functions to implement:**
- `get_db() -> StandardDatabase` - Connection pool management with retry logic
- `init_schema(db: StandardDatabase) -> None` - Create all 20 document + 21 edge collections (v1.0 scope)
- `create_indexes(db: StandardDatabase) -> None` - Create persistent indexes for performance
- `drop_indexes(collection: str) -> None` - Temporary index dropping for bulk import
- `rebuild_indexes(collection: str) -> None` - Restore indexes after bulk import
- `health_check() -> bool` - Database connectivity check

**Collections to create - v1.0 Scope (20 document):**
```python
# Validated against references/Unified_Schema.rtf
# v1.0 scope: Open data sources only (NO scanner evidence, NO process evidence, NO document provenance)

DOCUMENT_COLLECTIONS = [
    # ========== Core Vulnerability Intelligence (6 collections) ==========
    "vulnerabilities",           # CVE records (NVD, OSV, GHSA)
    "weaknesses",                # CWE records with hierarchy
    "kev_entries",               # CISA Known Exploited Vulnerabilities
    "vulncheck_kev_entries",     # VulnCheck extended KEV data
    "exploit_modules",           # Metasploit, ExploitDB, Nuclei, PoC-in-GitHub
    "epss_history",              # Time-series EPSS scores

    # ========== Threat & Attack Frameworks (5 collections) ==========
    "attack_techniques",         # MITRE ATT&CK techniques (Enterprise/ICS/Mobile)
    "attack_patterns",           # CAPEC attack patterns
    "atlas_techniques",          # MITRE ATLAS AI/ML techniques
    "d3fend_techniques",         # MITRE D3FEND defensive techniques
    "threat_groups",             # ATT&CK threat actor groups

    # ========== Compliance & Regulatory (4 collections) ==========
    "regulatory_requirements",   # CRA, FDA 524B, IEC 62304, NIST SSDF, ISO 21434
    "oscal_controls",            # NIST SP 800-53 Rev 5 controls
    "scf_controls",              # Secure Controls Framework 2025.4
    "opencre_nodes",             # OWASP OpenCRE nodes

    # ========== Software Identity & Supply Chain (5 collections) ==========
    "components",                # Software packages keyed by PURL
    "cpe_entries",               # NVD CPE dictionary
    "scorecard_results",         # OpenSSF Scorecard results
    "licenses",                  # SPDX license definitions
    "package_health",            # Package ecosystem health (deps.dev, Ecosyste.ms)

    # ========== Infrastructure (internal collections) ==========
    # Note: llm_enrichments will be added in Phase 3 (LLM agents)
]
```

**Edge collections to create - v1.0 Scope (21 edges):**
```python
EDGE_COLLECTIONS = [
    # ========== Core Vulnerability Intelligence (7 edges) ==========
    "has_weakness",              # Vulnerability → CWE
    "exploited_in_wild",         # Vulnerability → KEV entry (CISA or VulnCheck)
    "has_exploit",               # Vulnerability → exploit module/PoC
    "aliases",                   # Vulnerability ↔ Vulnerability (CVE/GHSA/OSV equivalence)
    "affects",                   # Vulnerability → component/CPE (with version ranges)
    "has_epss_history",          # Vulnerability → EPSS history entry
    "has_epss",                  # Vulnerability → current EPSS (lightweight edge)

    # ========== Threat & Attack Frameworks (6 edges) ==========
    "technique_exploits_weakness",  # ATT&CK technique → CWE
    "capec_relates_to_cwe",         # CAPEC → CWE
    "capec_maps_to_attack",         # CAPEC → ATT&CK
    "technique_mitigated_by_control", # ATT&CK → NIST 800-53 control
    "atlas_maps_to_attack",         # ATLAS → ATT&CK
    "d3fend_counters_technique",    # D3FEND → ATT&CK

    # ========== Compliance & Regulatory (3 edges) ==========
    "maps_to_requirement",       # CWE → regulatory requirement
    "cross_framework_mapping",   # Framework ↔ framework equivalence
    "opencre_links",             # OpenCRE → standards/requirements

    # ========== Software Identity & Supply Chain (5 edges) ==========
    "depends_on",                # Component → component (dependency DAG)
    "matched_by_cpe",            # Component (PURL) → CPE
    "same_as",                   # Component ↔ component (identity equivalence)
    "scored_by",                 # Component → Scorecard result
    "licensed_under",            # Component → license
]
```

**Deferred to v2.0 (16 doc, 20 edge collections):**
- Scanner Evidence Layers 0-4: `tool_runs`, `sast_findings`, `dast_findings`, `sbom_artifacts`, `binary_hardening_profiles`, `code_metrics`, `secret_findings`, `license_findings` (8 doc + 10 edges)
- Process Evidence Layer 5: `remediation_tickets`, `code_changes`, `scan_results`, `compliance_events` (4 doc + 6 edges)
- Document Provenance Layer 6: `generated_documents`, `document_claims`, `evidence_chains` (3 doc + 3 edges)
- Full LLM infrastructure: `llm_enrichments` (1 doc + 1 edge) - partial in v1.0 for open data enrichment only

**Indexes to create:**
```python
INDEXES = {
    "vulnerabilities": [
        {"type": "persistent", "fields": ["cve_id"], "unique": True},
        {"type": "persistent", "fields": ["published_date"]},
        {"type": "persistent", "fields": ["cvss_severity"]},
    ],
    "weaknesses": [
        {"type": "persistent", "fields": ["cwe_id"], "unique": True},
    ],
    "components": [
        {"type": "persistent", "fields": ["purl"], "unique": True},
        {"type": "persistent", "fields": ["name", "version"]},
    ],
    # ... (all collections need indexes)
}
```

**Acceptance Criteria:**
- [ ] All 20 document collections created (v1.0 scope)
- [ ] All 21 edge collections created with `_from`/`_to` validation (v1.0 scope)
- [ ] All indexes created with `persistent` type and `cacheEnabled: true`
- [ ] Connection pooling works with 10 concurrent connections
- [ ] Health check returns success when ArangoDB is running
- [ ] Schema validated against `references/Unified_Schema.rtf`

---

### Module 1.2: `src/complira_graph/models.py`
**Purpose:** Pydantic models for data validation
**LOC:** ~800 lines
**Dependencies:** None
**Priority:** P0 (blocking)

**Models to implement:**
- `CVERecord` - NVD CVE schema
- `CWERecord` - CWE weakness schema
- `ATTACKTechnique` - ATT&CK technique schema
- `CAPECPattern` - CAPEC pattern schema
- `Component` - SBOM component schema
- `VEXDocument` - VEX document schema
- `LLMEnrichment` - Provenance tracking schema
- ... (30+ models total)

**Example:**
```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CVERecord(BaseModel):
    _key: str = Field(..., description="CVE ID (e.g., CVE_2024_1234)")
    cve_id: str = Field(..., description="CVE-2024-1234 format")
    published_date: datetime
    last_modified_date: datetime
    description: str
    cvss_v3_score: Optional[float] = None
    cvss_severity: Optional[str] = None
    cwe_ids: list[str] = []
    source: str = Field(..., description="nvd|osv|ghsa")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
```

**Acceptance Criteria:**
- [ ] All 36 document types have Pydantic models
- [ ] All models have field validation (required vs optional)
- [ ] All models support JSON serialization
- [ ] Deterministic `_key` generation for all models

---

### Module 1.3: `src/complira_graph/config.py`
**Purpose:** Settings management with pydantic-settings
**LOC:** ~200 lines
**Dependencies:** None
**Priority:** P0 (blocking)

**Settings to implement:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ArangoDB
    ARANGO_URL: str = "http://localhost:8529"
    ARANGO_USERNAME: str = "root"
    ARANGO_PASSWORD: str
    ARANGO_DATABASE: str = "complira_graph"

    # Anthropic API
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MAX_TOKENS: int = 4096

    # NVD API
    NVD_API_KEY: str
    NVD_RATE_LIMIT: int = 50  # requests per 30 seconds

    # GitHub API
    GITHUB_TOKEN: str
    GITHUB_RATE_LIMIT: int = 5000  # per hour

    # Prefect
    PREFECT_API_URL: str = "http://localhost:4200"

    # Monitoring
    PROMETHEUS_PORT: int = 9090
    GRAFANA_PORT: int = 3000

    class Config:
        env_file = ".env"
        case_sensitive = True

def load_settings() -> Settings:
    return Settings()
```

**Acceptance Criteria:**
- [ ] All required API keys loaded from `.env`
- [ ] Default values for optional settings
- [ ] Validation errors raised for missing required keys

---

## Layer 2: Base Agent Framework

### Module 2.1: `src/complira_graph/agents/base.py`
**Purpose:** Base classes for all ingestion agents
**LOC:** ~300 lines
**Dependencies:** Layer 1
**Priority:** P0 (blocking)

**Classes to implement:**
- `BaseIngestionAgent` - Abstract base for all deterministic agents
- `BaseLLMAgent` - Abstract base for all LLM agents

```python
from abc import ABC, abstractmethod
from typing import Any, Generator
from arango.database import StandardDatabase

class BaseIngestionAgent(ABC):
    def __init__(self, db: StandardDatabase):
        self.db = db
        self.agent_name = self.__class__.__name__

    @abstractmethod
    def fetch_data(self) -> Any:
        """Fetch data from external source"""
        pass

    @abstractmethod
    def transform_data(self, raw_data: Any) -> Generator[dict, None, None]:
        """Transform raw data to graph nodes/edges"""
        pass

    def load_data(self, records: list[dict], collection: str) -> None:
        """Bulk load into ArangoDB"""
        self.db.collection(collection).import_bulk(
            records,
            on_duplicate="update",
            batch_size=10000
        )

    def run(self) -> dict:
        """Main execution flow"""
        raw_data = self.fetch_data()
        records = list(self.transform_data(raw_data))
        # Drop indexes before bulk import
        # Load data
        # Rebuild indexes
        return {"records_loaded": len(records)}
```

**Acceptance Criteria:**
- [ ] `BaseIngestionAgent` has `fetch_data()`, `transform_data()`, `load_data()`, `run()` methods
- [ ] `BaseLLMAgent` has `find_gaps()`, `enrich()`, `validate()`, `persist()` methods
- [ ] All agents inherit from appropriate base class

---

## Layer 3: Data Ingestion Agents (23 Agents)

### Implementation Order (follows DAG dependencies):

**Batch 1: Foundation Agents (no dependencies)**
1. `src/complira_graph/agents/cwe.py` - CWE weakness data
2. `src/complira_graph/agents/attack.py` - MITRE ATT&CK
3. `src/complira_graph/agents/capec.py` - CAPEC patterns
4. `src/complira_graph/agents/d3fend.py` - D3FEND techniques
5. `src/complira_graph/agents/atlas.py` - ATLAS ML attacks
6. `src/complira_graph/agents/spdx_licenses.py` - SPDX license list
7. `src/complira_graph/agents/oscal.py` - NIST 800-53 controls
8. `src/complira_graph/agents/scf.py` - Secure Controls Framework
9. `src/complira_graph/agents/opencre.py` - OpenCRE mappings

**Batch 2: Vulnerability Data (depends on CWE)**
10. `src/complira_graph/agents/nvd.py` - NVD CVE data (⚠️ circuit breaker required)
11. `src/complira_graph/agents/osv.py` - OSV.dev data
12. `src/complira_graph/agents/ghsa.py` - GitHub Security Advisories
13. `src/complira_graph/agents/epss.py` - EPSS scores (depends on NVD)
14. `src/complira_graph/agents/kev.py` - CISA KEV (depends on NVD)
15. `src/complira_graph/agents/vulnrichment.py` - CISA Vulnrichment (depends on NVD)

**Batch 3: Exploit Data (depends on CVE, CAPEC)**
16. `src/complira_graph/agents/metasploit.py` - Metasploit modules
17. `src/complira_graph/agents/exploitdb.py` - ExploitDB
18. `src/complira_graph/agents/nuclei.py` - Nuclei templates
19. `src/complira_graph/agents/poc_in_github.py` - PoC-in-GitHub

**Batch 4: Component Data (no dependencies)**
20. `src/complira_graph/agents/deps_dev.py` - deps.dev API
21. `src/complira_graph/agents/ecosystems.py` - Ecosyste.ms
22. `src/complira_graph/agents/endoflife.py` - endoflife.date
23. `src/complira_graph/agents/scorecard.py` - OpenSSF Scorecard

---

### Agent Implementation Template (Example: NVD Agent)

**Module:** `src/complira_graph/agents/nvd.py`
**LOC:** ~400 lines
**Priority:** P0 (critical path)
**Special Requirements:** Circuit breaker, rate limiting

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from ratelimit import limits, RateLimitException
from datetime import datetime, timedelta
from .base import BaseIngestionAgent

class NVDAgent(BaseIngestionAgent):
    BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def __init__(self, db, api_key: str):
        super().__init__(db)
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)

    @limits(calls=50, period=30)  # 50 requests per 30 seconds
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    @circuit_breaker(failure_threshold=5, recovery_timeout=1800)
    def fetch_data(self, start_date: datetime = None, end_date: datetime = None):
        """Fetch CVE data from NVD API 2.0"""
        params = {
            "apiKey": self.api_key,
            "resultsPerPage": 2000
        }
        if start_date:
            params["lastModStartDate"] = start_date.isoformat()
        if end_date:
            params["lastModEndDate"] = end_date.isoformat()

        response = self.client.get(self.BASE_URL, params=params)
        response.raise_for_status()
        return response.json()

    def transform_data(self, raw_data: dict):
        """Transform NVD JSON to CVERecord + edges"""
        for cve_item in raw_data.get("vulnerabilities", []):
            cve = cve_item["cve"]

            # Normalize CVE ID to _key format
            cve_id = cve["id"]  # CVE-2024-1234
            _key = cve_id.replace("-", "_")  # CVE_2024_1234

            # Extract CVSS score
            cvss_data = cve.get("metrics", {}).get("cvssMetricV31", [{}])[0]
            cvss_score = cvss_data.get("cvssData", {}).get("baseScore")
            cvss_severity = cvss_data.get("cvssData", {}).get("baseSeverity")

            # Extract CWE IDs
            cwe_ids = []
            for weakness in cve.get("weaknesses", []):
                for desc in weakness.get("description", []):
                    if desc["value"].startswith("CWE-"):
                        cwe_ids.append(desc["value"])

            # CVE document
            yield {
                "_key": _key,
                "cve_id": cve_id,
                "published_date": cve["published"],
                "last_modified_date": cve["lastModified"],
                "description": cve["descriptions"][0]["value"],
                "cvss_v3_score": cvss_score,
                "cvss_severity": cvss_severity,
                "source": "nvd"
            }

            # has_weakness edges
            for cwe_id in cwe_ids:
                cwe_key = cwe_id.replace("-", "_")  # CWE_79
                yield {
                    "_from": f"vulnerabilities/{_key}",
                    "_to": f"weaknesses/{cwe_key}",
                    "_collection": "has_weakness",
                    "confidence": 1.0,
                    "source": "nvd"
                }

    def load_data(self, records: list[dict]) -> None:
        """Bulk load CVEs and edges"""
        cve_docs = [r for r in records if "_collection" not in r]
        edges = [r for r in records if "_collection" in r]

        # Load CVE documents
        self.db.collection("vulnerabilities").import_bulk(
            cve_docs,
            on_duplicate="update"
        )

        # Load has_weakness edges
        weakness_edges = [e for e in edges if e["_collection"] == "has_weakness"]
        self.db.collection("has_weakness").import_bulk(
            weakness_edges,
            on_duplicate="update"
        )
```

**Acceptance Criteria (per agent):**
- [ ] `fetch_data()` implemented with retry logic
- [ ] `transform_data()` produces valid Pydantic models
- [ ] `load_data()` uses `import_bulk()` for performance
- [ ] Rate limiting enforced
- [ ] Incremental update support via checkpoints
- [ ] Unit tests with mocked API responses

---

## Layer 4: LLM Enrichment Agents (9 Agents)

### Module 4.1: `src/complira_graph/llm_agents/cwe_classifier.py`
**Purpose:** Classify CVEs without CWE using Claude Haiku 4.5
**LOC:** ~300 lines
**Priority:** P1
**Dependencies:** Layer 3 (NVD agent)

```python
from anthropic import Anthropic
from .base import BaseLLMAgent

class CWEClassifierAgent(BaseLLMAgent):
    def __init__(self, db, anthropic_client: Anthropic):
        super().__init__(db)
        self.client = anthropic_client

    def find_gaps(self) -> list[dict]:
        """Find CVEs without CWE classification"""
        query = """
        FOR cve IN vulnerabilities
            FILTER cve.source == "nvd"
            LET has_cwe = (
                FOR v, e IN 1..1 OUTBOUND cve has_weakness
                    RETURN 1
            )
            FILTER LENGTH(has_cwe) == 0
            LIMIT 25000
            RETURN {
                cve_id: cve.cve_id,
                description: cve.description
            }
        """
        cursor = self.db.aql.execute(query)
        return list(cursor)

    def enrich(self, cve: dict) -> dict:
        """Call Claude Haiku 4.5 to classify CWE"""
        prompt = f"""
        Analyze this CVE description and determine the most appropriate CWE classification.

        CVE ID: {cve["cve_id"]}
        Description: {cve["description"]}

        Return JSON with:
        - cwe_id: CWE-XXX format
        - confidence: float 0.0-1.0
        - reasoning: brief explanation
        """

        response = self.client.messages.create(
            model="claude-haiku-4.5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        result = json.loads(response.content[0].text)

        # Add provenance
        return {
            "cve_id": cve["cve_id"],
            "cwe_id": result["cwe_id"],
            "confidence": result["confidence"],
            "reasoning": result["reasoning"],
            "model": "claude-haiku-4.5",
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "timestamp": datetime.utcnow()
        }

    def validate(self, enrichment: dict) -> bool:
        """Validate confidence threshold"""
        return enrichment["confidence"] >= 0.85

    def persist(self, enrichment: dict) -> None:
        """Save edge + provenance"""
        cve_key = enrichment["cve_id"].replace("-", "_")
        cwe_key = enrichment["cwe_id"].replace("-", "_")

        # Create has_weakness edge
        edge = {
            "_from": f"vulnerabilities/{cve_key}",
            "_to": f"weaknesses/{cwe_key}",
            "confidence": enrichment["confidence"],
            "source": "llm"
        }
        self.db.collection("has_weakness").insert(edge)

        # Create provenance record
        provenance = {
            "entity_type": "has_weakness",
            "entity_id": f"{cve_key}->{cwe_key}",
            "model": enrichment["model"],
            "input_tokens": enrichment["input_tokens"],
            "output_tokens": enrichment["output_tokens"],
            "confidence": enrichment["confidence"],
            "reasoning": enrichment["reasoning"],
            "timestamp": enrichment["timestamp"]
        }
        self.db.collection("llm_enrichments").insert(provenance)
```

**Other LLM Agents to implement:**
- `src/complira_graph/llm_agents/purl_to_cpe.py` - Resolve PURL → CPE (Sonnet 4.5)
- `src/complira_graph/llm_agents/vex_synthesizer.py` - Generate VEX justifications (Sonnet 4.5)
- `src/complira_graph/llm_agents/regulatory_mapper.py` - Map CWE → regulations (Opus 4)
- `src/complira_graph/llm_agents/cve_entity_extractor.py` - Extract structured metadata (Haiku 4.5)
- `src/complira_graph/llm_agents/component_deduplicator.py` - Resolve component aliases (Haiku 4.5)
- `src/complira_graph/llm_agents/llm_agent_7.py` - Reserved for future use
- `src/complira_graph/llm_agents/llm_agent_8.py` - Reserved for future use
- `src/complira_graph/llm_agents/llm_agent_9.py` - Reserved for future use

**Acceptance Criteria:**
- [ ] All 9 LLM agents implemented
- [ ] Provenance tracking for all LLM outputs
- [ ] Confidence thresholds enforced
- [ ] Token usage tracked in Prometheus
- [ ] Dead letter queue integration for failures

---

## Layer 5: Orchestration

### Module 5.1: `src/complira_graph/orchestrator/dag.py`
**Purpose:** Build DAG for agent dependencies
**LOC:** ~250 lines
**Priority:** P0 (blocking)

```python
from typing import Dict, List, Set
from collections import defaultdict

class DAGBuilder:
    """Build topologically sorted DAG for agent execution"""

    AGENT_DEPENDENCIES = {
        # Layer 1: No dependencies
        "CWEAgent": [],
        "ATTACKAgent": [],
        "CAPECAgent": [],
        "D3FENDAgent": [],
        "ATLASAgent": [],
        "SPDXLicenseAgent": [],
        "OSCALAgent": [],
        "SCFAgent": [],
        "OpenCREAgent": [],

        # Layer 2: Depend on Layer 1
        "NVDAgent": ["CWEAgent"],
        "OSVAgent": ["CWEAgent"],
        "GHSAAgent": ["CWEAgent"],
        "MetasploitAgent": ["CAPECAgent"],

        # Layer 3: Depend on Layer 2
        "EPSSAgent": ["NVDAgent"],
        "KEVAgent": ["NVDAgent"],
        "VulnrichmentAgent": ["NVDAgent"],
        "ExploitDBAgent": ["NVDAgent", "CAPECAgent"],
        "NucleiAgent": ["NVDAgent"],
        "PoCInGitHubAgent": ["NVDAgent"],

        # Component agents (no dependencies)
        "DepsDevAgent": [],
        "EcosystemsAgent": [],
        "EndOfLifeAgent": [],
        "ScorecardAgent": [],
    }

    def build(self) -> List[List[str]]:
        """Return list of batches (agents that can run in parallel)"""
        # Topological sort with Kahn's algorithm
        in_degree = defaultdict(int)
        graph = defaultdict(list)

        for agent, deps in self.AGENT_DEPENDENCIES.items():
            for dep in deps:
                graph[dep].append(agent)
                in_degree[agent] += 1

        # Start with agents that have no dependencies
        queue = [agent for agent in self.AGENT_DEPENDENCIES if in_degree[agent] == 0]
        batches = []

        while queue:
            batch = queue[:]
            batches.append(batch)
            queue = []

            for agent in batch:
                for neighbor in graph[agent]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return batches
```

### Module 5.2: `src/complira_graph/orchestrator/seed.py`
**Purpose:** Execute full knowledge graph seeding
**LOC:** ~200 lines
**Priority:** P0

```python
from prefect import flow, task
from asyncio import Semaphore
from .dag import DAGBuilder

@task(retries=3, retry_delay_seconds=60)
def run_agent(agent_name: str, db) -> dict:
    """Execute single agent"""
    agent_class = globals()[agent_name]
    agent = agent_class(db)
    return agent.run()

@flow(name="seed-knowledge-graph")
def execute_seed_dag(db):
    """Execute all agents in dependency order with parallelism"""
    dag = DAGBuilder().build()
    semaphore = Semaphore(4)  # Max 4 concurrent agents

    for batch in dag:
        # Run batch in parallel (within semaphore limit)
        futures = []
        for agent_name in batch:
            async with semaphore:
                future = run_agent.submit(agent_name, db)
                futures.append(future)

        # Wait for batch to complete
        results = [f.result() for f in futures]

        # Log batch completion
        for agent_name, result in zip(batch, results):
            print(f"{agent_name}: {result}")

    # Run LLM agents sequentially after deterministic agents
    llm_agents = [
        "CWEClassifierAgent",
        "PURLToCPEAgent",
        "VEXSynthesizerAgent",
        # ... (all 9 LLM agents)
    ]

    for agent_name in llm_agents:
        result = run_agent(agent_name, db)
        print(f"{agent_name}: {result}")
```

### Module 5.3: `src/complira_graph/orchestrator/scheduler.py`
**Purpose:** Prefect schedules for incremental updates
**LOC:** ~150 lines

```python
from prefect import flow
from prefect.schedules import IntervalSchedule
from datetime import timedelta

@flow(
    name="update-kev",
    schedule=IntervalSchedule(interval=timedelta(hours=1))
)
def update_kev_hourly():
    """Update CISA KEV every hour"""
    agent = KEVAgent(get_db())
    return agent.run()

@flow(
    name="update-nvd",
    schedule=IntervalSchedule(interval=timedelta(hours=2))
)
def update_nvd_incremental():
    """Update NVD every 2 hours"""
    agent = NVDAgent(get_db())
    return agent.run()

# ... (schedules for all agents)
```

**Acceptance Criteria:**
- [ ] DAG builder correctly orders agents by dependencies
- [ ] Semaphore limits concurrent agents to 4
- [ ] Prefect flows register successfully
- [ ] Incremental update schedules work

---

## Layer 6: User Interface (CLI)

### Module 6.1: `src/complira_graph/cli.py`
**Purpose:** Click-based CLI
**LOC:** ~400 lines
**Priority:** P1

```python
import click
from .db import get_db
from .orchestrator.seed import execute_seed_dag

@click.group()
def cli():
    """Complira Knowledge Graph CLI"""
    pass

@cli.command()
def seed():
    """Seed the knowledge graph from all data sources"""
    db = get_db()
    click.echo("Starting full knowledge graph seed...")
    execute_seed_dag(db)
    click.echo("Seed complete!")

@cli.command()
@click.argument("cve_id")
def blast_radius(cve_id: str):
    """Query regulatory blast radius for a CVE"""
    db = get_db()
    query = """
    FOR cve IN vulnerabilities
        FILTER cve.cve_id == @cve_id
        FOR cwe IN 1..1 OUTBOUND cve has_weakness
            FOR req IN 1..2 OUTBOUND cwe maps_to_requirement
                FOR framework IN 1..1 INBOUND req control_addresses_requirement
                    RETURN DISTINCT {
                        framework: framework.name,
                        requirement: req.title,
                        cwe: cwe.cwe_id,
                        evidence_chain: [cve.cve_id, cwe.cwe_id, req.id, framework.name]
                    }
    """
    results = db.aql.execute(query, bind_vars={"cve_id": cve_id})
    for result in results:
        click.echo(f"Framework: {result['framework']}")
        click.echo(f"Requirement: {result['requirement']}")
        click.echo(f"CWE: {result['cwe']}")
        click.echo("---")

@cli.command()
@click.argument("sbom_path", type=click.Path(exists=True))
def generate_vex(sbom_path: str):
    """Generate VEX document for SBOM"""
    # Parse SBOM
    # For each component+CVE pair:
    #   - Collect evidence
    #   - Call VEX synthesizer agent
    #   - Export VEX document
    click.echo(f"Generated VEX for {sbom_path}")

if __name__ == "__main__":
    cli()
```

**Acceptance Criteria:**
- [ ] `complira seed` works
- [ ] `complira blast_radius <CVE>` returns results in <5s
- [ ] `complira generate_vex <sbom.json>` produces valid VEX document

---

## Layer 7: Observability

### Module 7.1: `src/complira_graph/monitoring/metrics.py`
**Purpose:** Prometheus metrics
**LOC:** ~200 lines

```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Metrics
agent_records_loaded = Counter(
    "agent_records_loaded_total",
    "Total records loaded by agent",
    ["agent_name"]
)

agent_execution_time = Histogram(
    "agent_execution_seconds",
    "Agent execution time",
    ["agent_name"]
)

llm_tokens_used = Counter(
    "llm_tokens_used_total",
    "LLM tokens consumed",
    ["agent_name", "model"]
)

circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["service"]
)

def start_metrics_server(port: int = 9090):
    """Start Prometheus metrics HTTP server"""
    start_http_server(port)
```

### Module 7.2: `src/complira_graph/monitoring/logging.py`
**Purpose:** Structured logging with structlog
**LOC:** ~100 lines

```python
import structlog

def configure_logging():
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ]
    )

logger = structlog.get_logger()
```

**Acceptance Criteria:**
- [ ] Prometheus metrics exposed on port 9090
- [ ] Grafana dashboards created (agent status, LLM costs, circuit breaker)
- [ ] Structured JSON logs written to stdout

---

## Testing Strategy

### Unit Tests
**Location:** `tests/unit/`
**Coverage Target:** 80%+

- `tests/unit/test_db.py` - Database connection, schema creation
- `tests/unit/test_agents/` - All 32 agents (mocked API responses)
- `tests/unit/test_models.py` - Pydantic model validation
- `tests/unit/test_dag.py` - DAG topological sort

### Integration Tests
**Location:** `tests/integration/`
**Dependencies:** Docker Compose (ArangoDB, Prefect)

- `tests/integration/test_seed_flow.py` - Full seed workflow
- `tests/integration/test_incremental_update.py` - Checkpoint-based updates
- `tests/integration/test_vex_generation.py` - End-to-end VEX workflow

### Performance Tests
**Location:** `tests/performance/`

- `tests/performance/test_bulk_import.py` - 10M nodes, 28M edges import time
- `tests/performance/test_query_performance.py` - <5s blast radius, <30s VEX

---

## Acceptance Criteria Summary

From `requirements.md`, all must be validated:

**Functional Requirements:**
- [ ] FR-1: All 40+ data sources have functional agents
- [ ] FR-2: All 36 document + 41 edge collections created
- [ ] FR-3: 9 LLM agents implemented with provenance
- [ ] FR-4: Query performance targets met

**Non-Functional Requirements:**
- [ ] NFR-1: 10M nodes + 28M edges supported
- [ ] NFR-2: Retry logic + circuit breaker + DLQ implemented
- [ ] NFR-3: Prometheus + Grafana + structlog configured
- [ ] NFR-4: No secrets in git, API keys in .env
- [ ] NFR-5: Infrastructure cost <€100/month

---

## Infrastructure Setup

### Docker Compose
**File:** `docker-compose.yml`

```yaml
version: "3.8"

services:
  arangodb:
    image: arangodb:3.12
    ports:
      - "8529:8529"
    environment:
      ARANGO_ROOT_PASSWORD: ${ARANGO_PASSWORD}
    volumes:
      - arangodb_data:/var/lib/arangodb3

  prefect:
    image: prefecthq/prefect:3-latest
    ports:
      - "4200:4200"
    command: prefect server start

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards

volumes:
  arangodb_data:
  grafana_data:
```

---

## Next Steps

1. **Mark this plan as reviewed**
2. **Create `implementation-progress.md`** to track completion
3. **Begin Phase 1 implementation** (Layer 1: Database Foundation)
4. **Update `implementation-progress.md`** after each module completion
5. **Run tests** after each layer completion
6. **Move to Stage 7** once all acceptance criteria met
