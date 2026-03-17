# Complira Cybersecurity Compliance Platform

A production-grade cybersecurity compliance platform combining a knowledge graph engine with a web-based UI for SBOM analysis and vulnerability enrichment.

## Overview

This platform builds a comprehensive ArangoDB knowledge graph (~10M nodes, ~28M edges) from:

- **Vulnerability Intelligence**: NVD, OSV, GHSA, CISA KEV, VulnCheck, EPSS
- **Threat Frameworks**: MITRE ATT&CK, CAPEC, D3FEND, ATLAS
- **Compliance Frameworks**: NIST 800-53, CRA, FDA 524B, IEC 62304, SCF, OpenCRE
- **Software Supply Chain**: deps.dev, Ecosyste.ms, SPDX, endoflife.date
- **Exploit Intelligence**: Metasploit, ExploitDB, Nuclei, PoC-in-GitHub

## Features

- **40+ Data Source Ingestion Agents** with incremental updates
- **LLM Enrichment Layer** (9 agents) for gap-filling and VEX generation
- **DAG-based Orchestration** with dependency ordering
- **Regulatory Mapping** (CWE → compliance requirements)
- **Real-time Monitoring** with Prometheus + Grafana
- **Reference API** for local-first security scanning (no auth, no data upload)
- **Multi-Tenant SaaS API** for cloud-based scan storage and tracking

## Project Structure

```
cybersecurity-compliance-app/
├── src/                          # Backend (FastAPI + Knowledge Graph)
│   ├── api/                      # REST API
│   └── complira_graph/           # Graph data model + agents
├── frontend/                     # Web UI (Next.js 14) [Phase 5]
│   ├── app/                      # Next.js App Router pages
│   ├── components/               # React components (shadcn/ui)
│   └── lib/                      # API client, utilities
├── scripts/                      # Data ingestion scripts
├── docs/                         # Documentation
├── tickets/                      # Development tickets (Phase planning)
└── monitoring/                   # Grafana dashboards
```

## API Access

Complira provides two API modes:

### 1. Reference API (No Authentication, Privacy-First)

Query threat intelligence data **without uploading your scan results**. Perfect for GitHub Actions and local-first workflows.

**Available Endpoints:**
- `GET /v1/reference/cve/{cve_id}` - CVE details + EPSS + KEV + ATT&CK + Controls
- `GET /v1/reference/enrich?cve_ids=...` - Batch enrich multiple CVEs
- `GET /v1/reference/cwe/{cwe_id}` - CWE weakness details
- `GET /v1/reference/controls/{cve_id}` - NIST 800-53 + regulatory mappings

**Example: GitHub Action with Local Scanning**
```bash
# Run Semgrep locally
semgrep --config auto --sarif > scan.sarif

# Extract CVEs
CVE_IDS=$(jq -r '.runs[].results[].ruleId' scan.sarif | grep CVE | tr '\n' ',' | sed 's/,$//')

# Enrich with Complira (no API key needed!)
curl "https://api.complira.dev/v1/reference/enrich?cve_ids=$CVE_IDS" > enriched.json

# Generate compliance report locally - scan results never leave your CI/CD
python generate_report.py scan.sarif enriched.json > report.md
```

See full example: [docs/examples/github-action-local-scan.yml](docs/examples/github-action-local-scan.yml)

**Benefits:**
- ✅ Complete data privacy (scan results stay local)
- ✅ No authentication required
- ✅ Unlimited usage
- ✅ 6-hour cache for fast responses
- ✅ Get EPSS scores, KEV status, ATT&CK techniques, NIST controls, regulatory mappings

### 2. SaaS API (Authentication Required, Full Features)

Upload scan results for centralized tracking, historical analysis, and compliance reporting.

**Available Endpoints:**
- `POST /v1/scan/ingest` - Upload SARIF/CycloneDX scans
- `GET /v1/scans` - List all scans
- `GET /v1/scan/{id}/findings` - Get findings with pagination
- `POST /v1/enrich` - Full knowledge graph enrichment (Phase 1)

**Example:**
```bash
# Upload scan to Complira cloud
curl -X POST https://api.complira.dev/v1/scan/ingest \
  -H "X-API-Key: $COMPLIRA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @scan_payload.json
```

**Documentation:**
- [Quick Reference](docs/QUICK_REFERENCE.md) - One-page cheat sheet
- [API Documentation](docs/API_DOCUMENTATION.md) - Complete API reference
- [Local Development Guide](docs/API_LOCAL_DEVELOPMENT.md) - Run and test APIs locally
- [Multi-Tenant Architecture](docs/MULTI_TENANT_ARCHITECTURE.md) - Database design

## Quick Start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- uv package manager

### Installation

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

### Run Infrastructure

```bash
# Start ArangoDB, Prefect, Prometheus, Grafana
docker compose up -d

# Verify services
docker compose ps
```

### Run Ingestion

```bash
# Initial seed (runs all agents in dependency order)
complira seed

# Skip LLM agents (faster, no API costs)
complira seed --skip-llm

# Incremental update (high-frequency agents only)
complira incremental

# Check status
complira status
```

## Usage

### CLI Commands

```bash
# Seed knowledge graph
complira seed [--skip-llm] [--max-concurrent N]

# Incremental updates
complira incremental [AGENT_NAMES...]

# Regulatory blast radius analysis
complira blast-radius CVE-2024-1234 [--format json] [--output FILE]

# Generate VEX document from SBOM
complira generate-vex sbom.json [--output vex.json]

# Run AQL query
complira query "FOR v IN vulnerabilities LIMIT 10 RETURN v"

# System status
complira status

# Deploy Prefect schedules
complira schedule deploy
complira schedule show
```

### Programmatic Usage

```python
from complira_graph.orchestrator import execute_seed_dag
from complira_graph.db import get_db

# Seed knowledge graph
result = execute_seed_dag(skip_llm=False)
print(f"Processed {result['total_agents_executed']} agents")

# Query database
db = get_db()
cursor = db.aql.execute("""
    FOR cve IN vulnerabilities
        FILTER cve.cvss_v3_score >= 9.0
        RETURN cve.cve_id
""")
critical_cves = list(cursor)
```

## VulnCheck Integration (Phase 3A)

The platform includes 9 VulnCheck API agents for exploit intelligence. **Note:** Most agents require a paid VulnCheck subscription.

### Community Tier (FREE)
- ✅ **VulnCheckKEVAgent** - CISA KEV catalog with lead time analysis (4,600+ entries)

### Paid Tier Required
The following agents require a "Exploit & Vulnerability Intelligence" subscription:

- ⏸️ **VulnCheckNVD2Agent** - 244K CVEs with exploit maturity data
- ⏸️ **VulnCheckExploitsAgent** - On-demand CVE enrichment (< 600ms)
- ⏸️ **VulnCheckRansomwareAgent** - Ransomware family CVE attribution
- ⏸️ **VulnCheckBotnetsAgent** - Botnet campaign CVE attribution
- ⏸️ **VulnCheckThreatActorsAgent** - Threat actor groups and campaigns
- ⏸️ **VulnCheckExploitChainsAgent** - Multi-CVE attack sequences
- ⏸️ **VulnCheckEOLAgent** - End-of-life product tracking (FDA compliance)

All agents are implemented, tested, and ready to use. They gracefully handle 402 errors and will automatically work when you upgrade to a paid tier.

**Alternative:** The `exploit_intelligence` collection can be populated using free NVD/GHSA APIs (already included in Phase 2).

See `tickets/in-progress/phase-3-vulncheck-integration/TIER_REQUIREMENTS_DOCUMENTATION.md` for details.

## Architecture

- **Database**: ArangoDB 3.12 (graph + document + search)
- **Orchestration**: Prefect 3.x (Python-native scheduling)
- **Language**: Python 3.12+ with Pydantic v2
- **Monitoring**: Prometheus + Grafana
- **LLM**: Anthropic Claude (Haiku 4.5 / Sonnet 4.5 / Opus 4)

## Documentation

See `references/` directory for detailed specifications:
- `Data_sources.rtf` - All 40+ data sources and APIs
- `Implementation_stack.rtf` - Technical stack and architecture
- `Unified_Schema.rtf` - ArangoDB schema (36 collections, 41 edges)
- `LLM_Enhancement.rtf` - LLM enrichment agent specifications

## License

[To be determined]
