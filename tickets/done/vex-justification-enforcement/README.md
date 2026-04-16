# Complira Knowledge Graph Engine

A production-grade cybersecurity compliance knowledge graph platform that ingests 40+ open data sources and maps vulnerabilities to regulatory requirements.

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

# Incremental update
complira update

# Check status
complira status
```

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
