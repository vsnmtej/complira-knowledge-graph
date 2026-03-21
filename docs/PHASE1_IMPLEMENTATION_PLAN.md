# Phase 1: Advanced Enrichment with LLM Agents

**Status**: 🚧 In Progress
**Goal**: Leverage LLM agents (Claude) for intelligent vulnerability analysis, attack path discovery, and compliance mapping

---

## Overview

Phase 1 builds on Phase 0's foundation by adding **AI-powered enrichment capabilities** using Claude (Anthropic) to provide:

1. **Intelligent Vulnerability Analysis** - Deep dive into CVE impact, exploitation scenarios, and mitigation strategies
2. **Attack Path Discovery** - Map full attack chains from CVE → CWE → CAPEC → ATT&CK → Threat Groups
3. **Compliance Mapping** - Automatically map findings to regulatory requirements (FDA 524B, EU CRA, IEC 62304, NIST 800-53)
4. **Blast Radius Analysis** - Calculate full impact scope of a vulnerability

---

## Architecture

### LLM Service Layer

```
┌──────────────────────────────────────────────────────────┐
│                    FastAPI Endpoint                       │
│  POST /v1/enrich, /v1/map-controls, /v1/blast-radius     │
└─────────────────────┬────────────────────────────────────┘
                      │
                      ↓
┌──────────────────────────────────────────────────────────┐
│                  Enrichment Service                       │
│  • Orchestrates LLM agents                                │
│  • Manages context gathering from graph DB                │
│  • Combines LLM insights with graph data                  │
└─────────────────────┬────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ CVE Analysis │ │ Attack Path  │ │ Compliance   │
│    Agent     │ │    Agent     │ │    Agent     │
│  (Claude)    │ │  (Claude)    │ │  (Claude)    │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       └────────────────┼────────────────┘
                        ↓
              ┌──────────────────┐
              │  Knowledge Graph │
              │   (ArangoDB)     │
              │  699K+ documents │
              └──────────────────┘
```

---

## Component Design

### 1. LLM Service (`src/api/services/llm.py`)

**Purpose**: Abstract Claude API integration with caching, rate limiting, and error handling

```python
class ClaudeLLMService:
    """
    Claude API integration for vulnerability enrichment.

    Features:
    - Structured output with JSON mode
    - Automatic retry with exponential backoff
    - Token usage tracking
    - Response caching (Redis)
    """

    async def analyze_vulnerability(
        self,
        cve_id: str,
        context: Dict[str, Any]
    ) -> VulnerabilityAnalysis:
        """
        Analyze CVE with Claude.

        Context includes:
        - CVE description, CVSS score
        - CWE weaknesses
        - ATT&CK techniques
        - Existing exploits

        Returns structured analysis:
        - Exploitation difficulty
        - Real-world impact scenarios
        - Recommended mitigations
        - Compliance implications
        """

    async def map_to_controls(
        self,
        findings: List[Finding],
        frameworks: List[str]
    ) -> ControlMapping:
        """
        Map findings to compliance controls using Claude.

        Returns:
        - NIST 800-53 control mappings
        - FDA 524B requirement mappings
        - EU CRA article mappings
        - Gap analysis
        """

    async def trace_attack_path(
        self,
        cve_id: str,
        graph_data: Dict[str, Any]
    ) -> AttackPath:
        """
        Trace full attack path using Claude + graph traversal.

        Returns:
        - CVE → CWE → CAPEC → ATT&CK → Threat Groups
        - Likelihood scores at each stage
        - Defensive countermeasures (D3FEND)
        """
```

---

### 2. Enrichment Agents

#### a. CVE Analysis Agent (`src/api/agents/cve_analysis_agent.py`)

**Input**: CVE ID + context from graph
**Output**: Rich analysis with exploitation scenarios

**Prompt Template**:
```
You are a cybersecurity expert analyzing CVE-{cve_id}.

Context:
- Description: {description}
- CVSS Score: {cvss_score}
- CWE: {cwe_list}
- EPSS: {epss_score}
- KEV Status: {in_kev}
- Known Exploits: {exploit_count}

Provide:
1. **Exploitation Difficulty** (1-5 scale): How hard is this to exploit?
2. **Real-World Impact**: What could an attacker actually do?
3. **Mitigation Priority**: Based on EPSS + KEV + impact
4. **Recommended Actions**: Concrete steps to remediate
5. **Compliance Impact**: Which frameworks care about this?

Respond in JSON format.
```

#### b. Attack Path Agent (`src/api/agents/attack_path_agent.py`)

**Input**: CVE ID + full graph context
**Output**: Attack chain with likelihoods

**Approach**:
1. **Graph Traversal**: Get CVE → CWE → CAPEC → ATT&CK → Threat Groups
2. **LLM Enhancement**: Claude explains each hop and assigns likelihood
3. **Defensive Mapping**: Add D3FEND countermeasures

**Output Format**:
```json
{
  "attack_path": [
    {
      "stage": "vulnerability",
      "node": "CVE-2024-1234",
      "description": "SQL Injection in login form",
      "likelihood": 0.85
    },
    {
      "stage": "weakness",
      "node": "CWE-89",
      "description": "Improper Neutralization of SQL Commands",
      "likelihood": 0.90
    },
    {
      "stage": "attack_pattern",
      "node": "CAPEC-66",
      "description": "SQL Injection",
      "likelihood": 0.80
    },
    {
      "stage": "technique",
      "node": "T1190",
      "description": "Exploit Public-Facing Application",
      "tactics": ["initial-access"],
      "likelihood": 0.75
    },
    {
      "stage": "threat_groups",
      "nodes": ["APT28", "APT29"],
      "description": "Known groups exploiting this technique",
      "likelihood": 0.60
    }
  ],
  "defenses": [
    {
      "d3fend_id": "D3-IAA",
      "name": "Input validation",
      "coverage": ["CWE-89", "CAPEC-66"]
    }
  ]
}
```

#### c. Compliance Mapping Agent (`src/api/agents/compliance_agent.py`)

**Input**: Scan findings + target frameworks
**Output**: Control mappings with gap analysis

**Approach**:
1. **Graph Query**: Get all findings → CVEs → CWEs → ATT&CK → Controls
2. **LLM Enhancement**: Claude explains why each control applies
3. **Gap Analysis**: Claude identifies missing controls

---

### 3. API Endpoints

#### `POST /v1/enrich`

**Purpose**: Deep enrichment of CVEs with AI analysis

**Request**:
```json
{
  "cve_ids": ["CVE-2024-1234", "CVE-2023-44487"],
  "include_llm_analysis": true,
  "include_attack_paths": true
}
```

**Response**:
```json
{
  "enriched": [
    {
      "cve_id": "CVE-2024-1234",
      "basic_data": {
        "cvss_score": 9.8,
        "epss_score": 0.85,
        "in_kev": true
      },
      "llm_analysis": {
        "exploitation_difficulty": 2,
        "real_world_impact": "Attacker can extract entire database...",
        "mitigation_priority": "CRITICAL",
        "recommended_actions": [
          "Patch immediately to version 2.5.0",
          "Enable prepared statements",
          "Deploy WAF rules"
        ],
        "compliance_impact": {
          "FDA_524B": "Violates V.C.1 (cybersecurity testing)",
          "EU_CRA": "Violates Annex I Part II (security requirements)"
        }
      },
      "attack_path": { /* full attack chain */ }
    }
  ]
}
```

#### `POST /v1/map-controls`

**Purpose**: Map scan findings to compliance frameworks

**Request**:
```json
{
  "scan_session_id": "scan_abc123",
  "frameworks": ["NIST_800_53", "FDA_524B", "ISO_27001"],
  "include_gap_analysis": true
}
```

**Response**:
```json
{
  "mappings": {
    "NIST_800_53": {
      "controls": [
        {
          "control_id": "SI-2",
          "title": "Flaw Remediation",
          "findings_count": 42,
          "critical_findings": 5,
          "rationale": "These findings require timely patching per SI-2"
        }
      ],
      "coverage": 85.2,
      "gaps": [
        {
          "control_id": "RA-5",
          "issue": "No vulnerability scanning evidence for network services"
        }
      ]
    }
  }
}
```

#### `POST /v1/blast-radius`

**Purpose**: Calculate full impact of a vulnerability

**Request**:
```json
{
  "cve_id": "CVE-2024-1234",
  "customer_context": true
}
```

**Response**:
```json
{
  "cve_id": "CVE-2024-1234",
  "blast_radius": {
    "affected_components": 15,
    "affected_codebases": ["api-server", "web-app"],
    "attack_surface": {
      "entry_points": ["login endpoint", "search API"],
      "data_at_risk": ["user credentials", "PII"],
      "business_impact": "SEVERE"
    },
    "threat_landscape": {
      "active_exploits": 3,
      "threat_groups": ["APT28", "FIN7"],
      "ransomware_risk": "HIGH"
    },
    "compliance_impact": {
      "frameworks_affected": ["FDA_524B", "HIPAA"],
      "regulatory_deadlines": ["FDA CVE disclosure within 72h"]
    }
  }
}
```

---

## Implementation Phases

### Phase 1A: Foundation (Week 1)
- ✅ LLM Service with Claude integration
- ✅ Basic CVE Analysis Agent
- ✅ `POST /v1/enrich` endpoint
- ✅ Caching layer for LLM responses
- ✅ Token usage tracking

### Phase 1B: Attack Paths (Week 2)
- ✅ Attack Path Agent
- ✅ Graph traversal optimization
- ✅ `POST /v1/blast-radius` endpoint
- ✅ D3FEND defense mapping

### Phase 1C: Compliance (Week 3)
- ✅ Compliance Mapping Agent
- ✅ `POST /v1/map-controls` endpoint
- ✅ Gap analysis logic
- ✅ Multi-framework support

### Phase 1D: Testing & Polish (Week 4)
- ✅ Integration tests
- ✅ Performance optimization
- ✅ Rate limiting
- ✅ Documentation

---

## Technical Specifications

### LLM Configuration

**Model**: Claude 3.5 Sonnet (claude-3-5-sonnet-20241022)
**Max Tokens**: 4096
**Temperature**: 0.3 (for consistency)
**Response Format**: JSON (structured output)

### Caching Strategy

```python
# Cache LLM responses in Redis
# Key: llm:cve_analysis:{cve_id}:{context_hash}
# TTL: 24 hours (analysis stays relatively stable)

# Cache graph queries
# Key: graph:attack_path:{cve_id}
# TTL: 6 hours (graph data updates less frequently)
```

### Rate Limiting

- **LLM API**: 50 requests/minute (Anthropic tier limit)
- **Queue batching**: Group multiple CVEs into single prompt when possible
- **Fallback**: Return basic enrichment if LLM quota exceeded

### Cost Estimation

**Per Enrichment Request**:
- Input tokens: ~2,000 (CVE context + graph data)
- Output tokens: ~1,500 (structured analysis)
- Cost per request: ~$0.015 (Claude Sonnet pricing)

**For 1,000 enrichment requests/month**: ~$15/month

---

## Acceptance Criteria

### AC-P1-001: LLM Service Integration
- ✅ Claude API integration with retry logic
- ✅ Structured JSON output parsing
- ✅ Token usage tracking and logging
- ✅ Error handling with graceful degradation

### AC-P1-002: CVE Analysis Agent
- ✅ Exploitation difficulty scoring (1-5)
- ✅ Real-world impact description
- ✅ Mitigation recommendations
- ✅ Compliance impact summary

### AC-P1-003: Attack Path Agent
- ✅ Full CVE → Threat Group chain
- ✅ Likelihood scores at each stage
- ✅ D3FEND defensive mappings
- ✅ Visualization-ready output

### AC-P1-004: Compliance Mapping Agent
- ✅ Multi-framework support (NIST, FDA, ISO)
- ✅ Control-to-finding mappings
- ✅ Coverage percentage calculation
- ✅ Gap analysis with recommendations

### AC-P1-005: API Endpoints
- ✅ `POST /v1/enrich` returns LLM analysis
- ✅ `POST /v1/blast-radius` returns impact analysis
- ✅ `POST /v1/map-controls` returns compliance mappings
- ✅ All endpoints handle errors gracefully

### AC-P1-006: Performance
- ✅ Average response time < 5 seconds
- ✅ 95th percentile < 10 seconds
- ✅ Cache hit rate > 60% after warmup
- ✅ LLM cost < $0.02 per enrichment

---

## Next Steps

1. **Start with LLM Service**: Create `src/api/services/llm.py`
2. **Build CVE Analysis Agent**: Create `src/api/agents/cve_analysis_agent.py`
3. **Implement `/enrich` Endpoint**: Enable basic AI enrichment
4. **Iterate**: Add attack paths, then compliance mapping

---

## Resources

- **Anthropic Claude Docs**: https://docs.anthropic.com/en/api
- **Existing Agents**: `src/complira_graph/agents/` (37+ data ingestion agents)
- **Graph Schema**: `docs/MULTI_TENANT_ARCHITECTURE.md`
- **Phase 0 Foundation**: `docs/API_DOCUMENTATION.md`
