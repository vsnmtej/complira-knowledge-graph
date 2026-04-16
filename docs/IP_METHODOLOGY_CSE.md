# Complira Simulation Engine (CSE)
## Intellectual Property Documentation — Confidential & Proprietary

**Document Classification:** TRADE SECRET / CONFIDENTIAL  
**Owner:** Complira Ltd.  
**Authors:** Complira Engineering Team  
**Version:** 1.0  
**Date:** 2026-04-16  
**Status:** Draft for Legal Review  

> **NOTICE:** This document describes proprietary methods and architectures developed exclusively by Complira Ltd. The methodologies described herein constitute trade secrets and are candidates for patent protection. Do not distribute outside the organisation without written authorisation.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Background & Prior Art Distinction](#2-background--prior-art-distinction)
3. [Core Invention: Multi-Agent Adversarial Cybersecurity Simulation](#3-core-invention-multi-agent-adversarial-cybersecurity-simulation)
4. [Graph-Derived Attack Surface Extraction](#4-graph-derived-attack-surface-extraction)
5. [LLM-Per-Round Adversarial Decision Engine](#5-llm-per-round-adversarial-decision-engine)
6. [Regulatory Deadline Integration](#6-regulatory-deadline-integration)
7. [Real-Time Knowledge Graph Writeback](#7-real-time-knowledge-graph-writeback)
8. [Situation Abstraction Layer](#8-situation-abstraction-layer)
9. [Extension: AI Agent Security Simulation (AASS)](#9-extension-ai-agent-security-simulation-aass)
10. [Novel Contributions Summary](#10-novel-contributions-summary)
11. [Claim Scope](#11-claim-scope)
12. [Trade Secret Designations](#12-trade-secret-designations)
13. [Prior Art Search Memo](#13-prior-art-search-memo)

---

## 1. Executive Summary

The **Complira Simulation Engine (CSE)** is a novel multi-agent adversarial cybersecurity simulation system that models real-world attack and defence dynamics against a specific organisation's actual vulnerability exposure, regulatory obligations, and asset topology — all derived in real-time from a property graph database.

Unlike conventional simulation tools (purple-team exercises, red team emulation, static risk models), CSE:

- Grounds every simulation in the **live organisational knowledge graph** — the attack surface is not hypothetical but derived from actual scanned components, CVE ingestion, and MITRE ATT&CK mappings specific to the tenant.
- Uses **Large Language Model (LLM) agents** for per-round adversarial and defensive decision-making, producing emergent behaviours not achievable with scripted or rule-based simulation.
- Enforces **regulatory deadline mechanics** natively (CRA Article 14, FDA 524B 30-day window, HIPAA 72-hour rule), making compliance breach simulation a first-class simulation outcome.
- Writes simulation findings back into the **same knowledge graph** from which the attack surface was derived, creating a closed-loop enrichment cycle.
- Abstracts results into **persona-safe business intelligence** (CISO posture scores, Board financial exposure, Engineering patch priority, Regulatory compliance deadlines) with zero CVE ID leakage across trust boundaries.

The system is further extensible to **AI Agent Security** — simulating adversarial attacks against AI-powered systems including prompt injection, model extraction, RAG poisoning, and agentic tool misuse — using the same multi-agent loop architecture.

---

## 2. Background & Prior Art Distinction

### 2.1 Existing Approaches and Limitations

| Category | Examples | Limitation |
|----------|----------|------------|
| Attack simulation tools | Cobalt Strike, Metasploit, CALDERA | Require human operators; non-regulatory-aware; no writeback to risk graph |
| Breach & attack simulation (BAS) | Cymulate, AttackIQ, SafeBreach | Script-based scenarios; no LLM-driven emergence; vendor CVE libraries not tenant-specific |
| Risk quantification | FAIR, RiskLens | Statistical models only; no dynamic simulation; no regulatory integration |
| AI red teaming | Garak, PyRIT | Focused on LLM safety, not organisational security posture or compliance |
| Threat modelling | STRIDE, PASTA, Microsoft TMT | Manual, static; no live data integration |

### 2.2 What Makes CSE Novel

CSE is the first known system to combine:

1. **Tenant-specific, graph-derived attack surfaces** (real CVEs from real scanned components, not vendor scenario libraries)
2. **LLM-per-round adversarial agents** operating in a shared stateful game environment
3. **Native regulatory deadline mechanics** as first-class simulation events
4. **Closed-loop knowledge graph enrichment** — findings feed back into the same graph that produced the attack surface
5. **Persona-safe abstraction layer** separating CVE-level findings from board/CISO/engineering views
6. **AI Agent Security extension** — the same adversarial loop models attacks on AI systems themselves

---

## 3. Core Invention: Multi-Agent Adversarial Cybersecurity Simulation

### 3.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    COMPLIRA KNOWLEDGE GRAPH                  │
│   (ArangoDB: 338k+ CVEs, ATT&CK, CWE, Compliance, Assets)  │
└──────────────────────┬──────────────────────────────────────┘
                       │  Attack Surface Extraction
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 SIMULATION PREPARE PIPELINE                  │
│  1. Graph Reader → tenant CVEs + components                  │
│  2. Profile Generator → LLM-authored agent profiles (×5)    │
│  3. Config Generator → rounds, deadlines, scheduled events   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              PARALLEL AGENT SIMULATION SUBPROCESS            │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐  │
│  │ Attacker │  │   SOC    │  │ DevSecOps │  │ Regulator│  │
│  │  Agent   │  │ Analyst  │  │   Agent   │  │  Agent   │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └────┬─────┘  │
│       │              │               │              │        │
│       └──────────────┴───────────────┴──────────────┘        │
│                              │                               │
│                   ┌──────────▼──────────┐                    │
│                   │  Attack Surface      │                    │
│                   │  Server (in-process  │                    │
│                   │  shared state)       │                    │
│                   └──────────┬──────────┘                    │
│                              │                               │
│                   cyber_actions.jsonl (append-only log)      │
└──────────────────────┬──────────────────────────────────────┘
                       │  Report Agent + Writeback
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              KNOWLEDGE GRAPH ENRICHMENT                      │
│  attack_chain_findings · threat_category_rollups             │
│  business_impact_findings · compliance_gap_findings          │
│  response_playbook_steps · simulation_runs                   │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              SITUATION ABSTRACTION LAYER                     │
│  CISO View · Board/CFO View · Engineering View · RegAffairs  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 The Simulation Clock

Each simulation tick ("round") represents one unit of simulated time (default: 1 hour). Every round, each agent independently observes the shared game state and issues exactly one action. This models:

- **Temporal dynamics** — an attacker exploiting a CVE at hour 3 vs. a defender patching at hour 5 has materially different outcomes than the reverse
- **Regulatory deadlines** — CRA Article 14 notification must file by round 24 (24-hour deadline); FDA 524B by round 720 (30-day deadline)
- **Detection lag** — SOC blind spots emerge when the attacker acts in rounds the defender fails to detect

### 3.3 Shared Game State Machine

The `AttackSurfaceServer` (in-process shared state) maintains:

```
attack_surface: list[CyberEntityNode]     # tenant CVEs + components
patched_cves: set[str]                    # CVEs the defender has patched
chain_steps: list[ChainStep]              # successful attacker exploits in sequence
privilege_level: int (0→1→2)             # attacker privilege escalation depth
ciso_alerted: bool                        # escalation state
cra_notified: bool                        # regulatory notification state
compliance_gaps: list[ComplianceGap]      # regulator-issued findings
controls_deployed: list[str]              # deployed defensive controls
```

This shared state — not any agent's private state — determines simulation outcomes. Agents observe it, act on it, and mutate it. This is the **novel game-theoretic mechanism** that produces emergent attack/defence dynamics.

---

## 4. Graph-Derived Attack Surface Extraction

### 4.1 Method

Rather than using static CVE scenario libraries, CSE extracts the attack surface dynamically from the organisation's property graph at simulation start time:

```aql
FOR edge IN component_has_vuln
    FILTER edge.tenant_id == @tenant_id
    LET vuln = DOCUMENT(edge._to)
    FILTER vuln != null
    RETURN {
        entity_id:     vuln._key,
        severity:      vuln.cvss_v3_score,
        is_kev:        vuln.is_kev,
        component_name: ...
    }
```

### 4.2 Novel Aspects

1. **Tenant isolation** — each simulation is scoped to a specific organisation's real CVE exposure, not a vendor-curated scenario set
2. **KEV prioritisation** — CISA Known Exploited Vulnerabilities carry elevated significance (0.9 vs. 0.75) in the simulation, reflecting real-world exploitability
3. **Graceful fallback** — when tenant data is sparse, the system falls back to highest-severity global CVEs, maintaining simulation validity
4. **Live graph binding** — as new CVEs are ingested (NVD, VulnCheck, OSV), subsequent simulations automatically reflect the updated exposure without reconfiguration

### 4.3 ATT&CK Technique Enrichment (Pending Full Implementation)

The knowledge graph contains 567 `technique_exploits_weakness` edges mapping CWE → ATT&CK techniques. Future versions will resolve CVE → CWE → ATT&CK at surface extraction time, providing per-CVE technique mappings that drive:
- Attacker technique selection diversity (beyond T1190)
- ATT&CK coverage calculation accuracy
- MITRE ATT&CK Navigator export

---

## 5. LLM-Per-Round Adversarial Decision Engine

### 5.1 Method

Each simulation round, every active agent makes a **real LLM inference call** to decide its action. The prompt includes:

- Agent role, tactics, goals, and constraints (from LLM-generated profile)
- Current game state (exploitable CVEs, chain depth, deadlines, controls)
- Round number and time pressure
- Historical context (what the agent has done recently)

The LLM returns structured JSON specifying the chosen action and target.

### 5.2 Why This Is Novel

Existing BAS tools (Cymulate, SafeBreach, AttackIQ) use **scripted playbooks** — deterministic sequences of actions defined by a human operator. CSE uses **LLM inference per round**, producing:

- **Emergent strategy** — the attacker may pivot to a less-obvious CVE if the obvious one gets patched; the defender may prioritise CRA notification over patching if the deadline is near
- **Context-sensitive decisions** — the attacker responds to what the defender actually did, not a pre-planned scenario
- **Unique simulation runs** — every execution produces a different outcome even on the same attack surface, modelling the stochastic nature of real attacks
- **Human-readable rationale** — agent decisions can be explained in natural language, not just logged as opaque rule firings

### 5.3 Profile Generation

Before the simulation runs, Claude generates a **bespoke personality profile** for each agent based on the specific attack surface:

```
Given the attack surface: [CVE-2021-44228 (CVSS 10, KEV), CVE-2022-22965 (CVSS 9.8), ...]
Generate an attacker profile for a sophisticated threat actor targeting this environment.
Return JSON: {role, tactics, constraints, goals, llm_context}
```

This means an attacker facing a healthcare IoT environment behaves differently from one facing a cloud-native SaaS — **the simulation is contextualised to the specific organisation** without manual configuration.

---

## 6. Regulatory Deadline Integration

### 6.1 Method

Regulatory reporting deadlines are encoded as **first-class simulation events** in the configuration:

```python
SCHEDULED_EVENTS = {
    "CRA_ART14_DEADLINE":  {"round": 24,   "framework": "CRA",     "requirement": "Art.14"},
    "FDA_524B_30DAY":      {"round": 720,  "framework": "FDA_524B","requirement": "Sec.524B"},
    "HIPAA_72HR":          {"round": 72,   "framework": "HIPAA",   "requirement": "164.410"},
    "NIS2_24HR":           {"round": 24,   "framework": "NIS2",    "requirement": "Art.23"},
}
```

### 6.2 Novel Aspects

1. **Deadline-aware defender behaviour** — the Regulator agent observes the approaching deadline and files compliance notifications at the appropriate round; failure to do so registers as a compliance gap
2. **Multi-framework simultaneous simulation** — a single simulation run can violate CRA, FDA, and HIPAA simultaneously if the attacker succeeds and the defender fails to notify in time
3. **Breach outcome taxonomy** — simulation outcomes are classified as `technical_breach`, `regulatory_breach`, or `operational_breach`, providing the precise language needed for board reporting
4. **Timeline reconstruction** — the `cyber_actions.jsonl` log enables exact reconstruction of which regulatory deadline was missed at which round, supporting post-incident forensic analysis

### 6.3 Regulatory Gap Findings

Every `ISSUE_COMPLIANCE_FINDING` action by the Regulator agent writes a structured finding:

```json
{
  "framework":      "CRA",
  "requirement_key": "CRA_art_24",
  "severity":       "critical",
  "description":    "Exploited vulnerability not reported within 24-hour window",
  "run_id":         "...",
  "tenant_id":      "..."
}
```

These findings feed directly into the `compliance_gap_findings` collection, driving the RegAffairs persona view and regulatory SLA countdown timers.

---

## 7. Real-Time Knowledge Graph Writeback

### 7.1 Method

Upon simulation completion, a **Report Agent** (Claude LLM call) synthesises the raw event log into business-level narratives, which are then written back into the same knowledge graph that supplied the attack surface:

```
simulation completes
    → Report Agent: generate board_narrative, tef_estimate, soc_miss_probability
    → Writeback Service:
        Step 1: attack_chain_findings (chain_nodes, chain_edges, confidence)
        Step 2: simulation_playbook_steps (ranked response actions)
        Step 3: chain_calibrates_fair (FAIR risk calibration edges)
        Step 4: threat_category_rollups (ATT&CK tactic bucket aggregates)
        Step 5: business_impact_findings (CFO financial exposure, board reputational risk)
        Step 6: compliance_gap_findings (framework-specific regulatory gaps)
        Step 7: simulation_runs (summary metadata)
```

### 7.2 Novel Aspects

**Closed-loop enrichment** — the graph that contained `CVE-2021-44228 → CWE-20 → T1190` before the simulation now also contains `CVE-2021-44228 → attack_chain_finding (confidence 0.91, soc_miss: true)` after it. Each simulation enriches the graph with empirical risk evidence specific to the organisation.

**FAIR calibration edges** — the `chain_calibrates_fair` edge type links simulated chain outcomes to FAIR loss scenarios, enabling quantitative risk (ALE, TEF, LEFF) to be grounded in simulation evidence rather than expert estimates alone.

**Idempotent upserts** — all writeback operations use ArangoDB UPSERT semantics, making the writeback pipeline safe under retry (Prefect workflow failures, network interruptions).

---

## 8. Situation Abstraction Layer

### 8.1 Method

The Situation Abstraction Layer (SAL) translates raw simulation graph data into **persona-appropriate views** that enforce trust boundary rules:

| Persona | Sees | Does Not See |
|---------|------|--------------|
| CISO | ATT&CK tactic buckets, posture score, MTTD, control failures | Individual CVE IDs, exploit details |
| Board/CFO | Breach probability %, financial exposure range, regulatory fine risk | Technique names, CVE specifics |
| Engineering | CVE IDs, CVSS, EPSS, patch urgency score | Board financial figures |
| RegAffairs | Compliance gaps by framework, SLA countdowns | Attack chain details |

### 8.2 Novel Aspects

**Zero CVE leakage across personas** — CVE identifiers are intentionally excluded from CISO and Board views. This is both a security principle (need-to-know) and a regulatory requirement (GDPR, NDA obligations to third-party vendors).

**Pull model, not push** — the SAL computes views on request, not on simulation completion. This decouples simulation cadence from reporting cadence and ensures views always reflect the latest graph state.

**Posture score formula**:
```
posture_score = 100
    - round(mean_chain_probability × 40)   [chain risk penalty]
    - (compliance_gap_count × 3)            [compliance gap penalty]
    - round(soc_miss_rate × 20)             [detection gap penalty]
    + round(attck_coverage_pct × 0.1)       [coverage bonus]
    clamped to [0, 100]
```

This formula is a **proprietary risk scoring methodology** combining simulated chain probability, compliance posture, and detection capability into a single executive metric.

---

## 9. Extension: AI Agent Security Simulation (AASS)

### 9.1 Motivation

As organisations deploy AI agents — RAG pipelines, LLM-powered copilots, autonomous orchestration agents — a new class of attack surface emerges that traditional CVE-based simulation cannot model. The AASS extension applies CSE's multi-agent adversarial loop to **AI system security**, treating AI components as first-class attack targets.

### 9.2 Novel Attack Surface: AI Agent Topology

For AI Agent Security simulation, the attack surface is extracted from the **AI agent topology graph** rather than the CVE graph:

```
AI Agent Topology Graph nodes:
  - LLM endpoints (model, provider, context window, tool access)
  - RAG pipelines (vector DB, document sources, chunking strategy)
  - Tool integrations (API calls, code execution, file system access)
  - Memory systems (short-term context, long-term vector store)
  - Orchestration layer (agent scheduler, inter-agent communication)
  - Data sources (training data lineage, fine-tune datasets)
  - Human-in-the-loop gates (approval workflows, confidence thresholds)
```

### 9.3 AI-Specific Attack Taxonomy

The AASS introduces a new set of attack and defence actions extending the CSE action space:

**Attacker Actions (AI-specific):**

| Action | Description | ATLAS Technique |
|--------|-------------|-----------------|
| `PROMPT_INJECTION` | Inject adversarial instructions into LLM context via user input, documents, or tool responses | AML.T0051 |
| `INDIRECT_PROMPT_INJECTION` | Plant malicious instructions in external content the agent will retrieve (web pages, emails, database records) | AML.T0051.001 |
| `RAG_POISONING` | Insert adversarial documents into the vector store to corrupt retrieval | AML.T0054 |
| `TOOL_MISUSE` | Craft prompts that cause the agent to invoke tools with attacker-controlled parameters | AML.T0043 |
| `CONTEXT_OVERFLOW` | Flood the context window to suppress safety instructions or force instruction truncation | Novel |
| `MODEL_EXTRACTION` | Reconstruct proprietary model behaviour through systematic querying | AML.T0036 |
| `TRAINING_DATA_INFERENCE` | Extract memorised training data through membership inference attacks | AML.T0024 |
| `MULTI_AGENT_COLLUSION` | Compromise one agent in a pipeline to propagate malicious instructions to downstream agents | Novel |
| `JAILBREAK_ESCALATION` | Progressively escalate prompts to bypass safety alignment | AML.T0048 |
| `SUPPLY_CHAIN_INJECTION` | Compromise the LLM provider, fine-tune dataset, or plugin at the supply chain level | AML.T0010 |

**Defender Actions (AI-specific):**

| Action | Description |
|--------|-------------|
| `DEPLOY_INPUT_SANITISER` | Add prompt injection detection layer at the agent input boundary |
| `ENFORCE_TOOL_ALLOWLIST` | Restrict which tools the agent can invoke to a declared allowlist |
| `ISOLATE_AGENT` | Quarantine a compromised agent from the multi-agent pipeline |
| `ROTATE_SYSTEM_PROMPT` | Replace system prompt with hardened version after injection detected |
| `ENABLE_RAG_PROVENANCE` | Activate document provenance tracking to detect poisoned retrievals |
| `ENFORCE_HITL_GATE` | Require human approval before high-risk tool invocations |
| `MONITOR_SEMANTIC_DRIFT` | Deploy embedding-based output monitoring for behavioural anomalies |
| `INVALIDATE_CONTEXT` | Clear agent context/memory after suspected compromise |

**Regulator Actions (AI-specific):**

| Action | Description | Regulation |
|--------|-------------|------------|
| `AUDIT_AI_SYSTEM` | Assess AI system against EU AI Act risk category classification | EU AI Act Art.9 |
| `FILE_AI_INCIDENT` | Report AI system failure under EU AI Act incident notification | EU AI Act Art.73 |
| `ENFORCE_TRANSPARENCY` | Issue transparency obligation finding (user disclosure, logging) | EU AI Act Art.13 |
| `ISSUE_BIAS_FINDING` | Record discriminatory output or fairness gap | EU AI Act Art.10 |
| `MANDATE_HUMAN_OVERSIGHT` | Require human-in-the-loop for high-risk AI decisions | EU AI Act Art.14 |

### 9.4 AI Agent Security Posture Score

The AASS extends the CSE posture formula with AI-specific penalty terms:

```
ai_posture_score = 100
    - round(injection_success_rate × 35)        [prompt injection penalty]
    - round(rag_contamination_depth × 25)        [RAG poisoning penalty]
    - (unmitigated_tool_misuse_count × 5)        [tool misuse penalty]
    - round(multi_agent_propagation_depth × 20)  [lateral propagation penalty]
    + round(hitl_coverage_pct × 0.15)            [human oversight bonus]
    + round(monitoring_coverage_pct × 0.10)      [observability bonus]
    clamped to [0, 100]
```

### 9.5 MITRE ATLAS Integration

The AASS maps attack outcomes to [MITRE ATLAS](https://atlas.mitre.org) techniques (the AI/ML equivalent of ATT&CK). The knowledge graph already contains `atlas_techniques` and `atlas_maps_to_attack` edges, enabling:

- Cross-mapping of AI attacks to traditional ATT&CK techniques (e.g. prompt injection → T1059 Command Execution)
- Coverage calculation across the ATLAS technique universe
- Regulatory mapping (ATLAS technique → EU AI Act article → compliance gap)

### 9.6 Regulatory Deadlines: EU AI Act

The AASS introduces EU AI Act deadlines as first-class simulation events:

| Deadline | Round | Requirement |
|----------|-------|-------------|
| Serious incident notification | 72 | Art.73 — notify market surveillance authority within 15 days |
| Fundamental rights impact assessment | 48 | Art.27 — document before high-risk deployment |
| Conformity assessment refresh | 720 | Art.43 — annual re-assessment for high-risk systems |
| Transparency disclosure | 1 | Art.13 — users must be informed they are interacting with AI |

### 9.7 Multi-Agent Pipeline Threat Model

The most novel aspect of AASS is the **multi-agent pipeline threat model** — the simulation models not just individual AI component compromise but **lateral propagation** through orchestrated agent pipelines:

```
Agent A (compromised via prompt injection)
    → passes tainted output to Agent B (tool orchestrator)
    → Agent B invokes external API with attacker-controlled parameters
    → Agent C (downstream analyst) receives poisoned context
    → Agent C produces attacker-desired output to human user
```

This models the emerging class of "multi-hop AI supply chain attacks" not addressed by any existing security framework.

### 9.8 AI Agent Security Graph Schema (Proposed)

New collections and edges for the AASS extension:

**Document Collections:**
- `ai_systems` — deployed AI system metadata (model, provider, risk category, deployment context)
- `ai_agents` — individual agent definitions (role, tools, memory type, context window)
- `ai_pipelines` — multi-agent orchestration topology
- `ai_incidents` — recorded AI security incidents
- `hitl_gates` — human-in-the-loop checkpoints
- `atlas_findings` — ATLAS technique observations from simulation

**Edge Collections:**
- `pipeline_invokes_agent` — orchestration graph edges
- `agent_has_tool` — agent → tool allowlist
- `agent_reads_from` — agent → data source (vector DB, API, file)
- `injection_propagates_to` — chain edges for multi-hop injection paths
- `atlas_maps_to_cve` — AI attack → traditional vulnerability linkage

---

## 10. Novel Contributions Summary

| Contribution | Description | IP Category |
|--------------|-------------|-------------|
| Graph-derived attack surface | Tenant-specific CVE/component extraction from property graph at simulation time | Patent candidate |
| LLM-per-round adversarial agents | Per-round Claude inference for emergent attack/defence decisions | Patent candidate |
| Shared game-state machine | In-process `AttackSurfaceServer` enabling true multi-agent interaction | Trade secret |
| Regulatory deadline mechanics | First-class simulation events for CRA, FDA, HIPAA, NIS2 deadlines | Patent candidate |
| Closed-loop knowledge graph enrichment | Simulation findings written back to the same graph that supplied the attack surface | Patent candidate |
| Posture score formula | Composite risk metric combining chain probability, SOC miss rate, compliance gaps, ATT&CK coverage | Trade secret |
| Persona-safe abstraction layer | CVE-free CISO/Board views derived from tactic-bucket rollups | Copyright / Trade secret |
| AI Agent Security Simulation | ATLAS-mapped adversarial simulation for AI systems and multi-agent pipelines | Patent candidate |
| Multi-hop AI injection propagation | Graph-modelled lateral propagation through orchestrated AI agent pipelines | Patent candidate |
| EU AI Act deadline mechanics | Real-time regulatory obligation simulation for AI Act Art.13/14/27/43/73 | Patent candidate |

---

## 11. Claim Scope

The following independent claims are proposed for patent prosecution:

### Claim 1 — Graph-Derived Simulation Method
A computer-implemented method for cybersecurity simulation comprising:
(a) extracting, from a property graph database, a tenant-specific attack surface comprising real vulnerability records linked to scanned software components via edge relationships;
(b) generating, using a large language model, bespoke behavioural profiles for a plurality of adversarial and defensive simulation agents based on said attack surface;
(c) executing a multi-round simulation wherein each round each agent makes an independent inference call to a large language model to determine its action on a shared game-state object;
(d) writing simulation findings back into the same property graph database as enrichment edges; and
(e) computing persona-safe abstracted views from the enriched graph that exclude raw vulnerability identifiers.

### Claim 2 — Regulatory Deadline Simulation
The method of Claim 1, further comprising encoding statutory reporting deadlines as scheduled simulation events such that failure of a simulation agent to file the required notification by the scheduled round produces a compliance gap finding attributed to the specific regulatory framework and article.

### Claim 3 — Closed-Loop Graph Enrichment
The method of Claim 1, wherein the property graph writeback comprises: attack chain findings including chain node and edge sequences; threat category rollups keyed by ATT&CK tactic bucket; FAIR-calibration edges linking chain outcomes to quantitative risk scenarios; and business impact findings authored by specialised financial and governance agents.

### Claim 4 — AI Agent Security Simulation
A computer-implemented method for simulating adversarial attacks against AI systems comprising:
(a) constructing an AI agent topology graph representing deployed AI systems, their tool integrations, memory systems, and pipeline connections;
(b) executing a multi-round simulation wherein attacker agents attempt prompt injection, RAG poisoning, tool misuse, and multi-agent propagation attacks against said topology;
(c) enforcing regulatory deadline events corresponding to EU AI Act notification obligations; and
(d) producing an AI security posture score and ATLAS technique coverage metric from simulation outcomes.

### Claim 5 — Multi-Hop AI Injection Propagation
The method of Claim 4, wherein multi-agent propagation attacks are modelled as directed graph traversals wherein a compromised agent's tainted output becomes the input context for downstream agents, and wherein the simulation records the propagation depth and affected agent count as a simulation outcome metric.

---

## 12. Trade Secret Designations

The following specific implementations are designated trade secrets and should not be disclosed in patent applications, academic publications, or open-source releases without explicit legal review:

| Component | File(s) | Secret |
|-----------|---------|--------|
| Game state mutation logic | `attack_surface_server.py` | Exact algorithm for chain step accumulation, privilege escalation thresholds, blind spot detection heuristics |
| Posture score formula | `abstraction_layer.py` | Specific coefficients and penalty weights |
| Profile generation prompts | `profile_generator.py` | Exact Claude prompt templates for agent profile generation |
| Attacker LLM context | `attacker_simulation.py` | Full system prompt and few-shot examples |
| Defender heuristic fallback | `defender_simulation.py` | Exact priority ordering for fallback decisions |
| Writeback AQL queries | `writeback_service.py` | Full AQL for chain finding structure, FAIR edge schema |
| Report agent prompt | `report_agent.py` | Full board narrative generation prompt |
| FAIR calibration method | `writeback_service.py` | Edge schema and calibration formula linking chain confidence to FAIR TEF |

---

## 13. Prior Art Search Memo

### 13.1 Searches Recommended

Before patent filing, search for:

- US patents on "cybersecurity simulation" + "knowledge graph" — likely clear
- US patents on "LLM agent" + "adversarial simulation" — field is nascent (2023–2025 applications likely)
- CALDERA (MITRE) — open-source BAS tool; does not use LLM-per-round or graph-derived surfaces
- Microsoft's AI Red Teaming tooling (PyRIT) — focused on LLM safety, not organisational posture
- IBM QRadar SOAR — automated playbooks but not adversarial simulation
- AttackIQ, Cymulate — commercial BAS; scripted scenarios, no graph integration

### 13.2 Recommended Filing Strategy

1. **Provisional patent (US)** — file within 12 months of first public disclosure to establish priority date; covers Claims 1–5 above
2. **PCT application** — extend to EU/UK/AU within 12 months of provisional filing
3. **Trade secret register** — maintain a dated, signed register of the specific implementations listed in §12 to establish proof of creation date
4. **Employee IP agreements** — ensure all engineers who contributed to CSE have signed IP assignment agreements
5. **Non-disclosure** — do not open-source the `cse/` directory; maintain as proprietary

---

*Document prepared: 2026-04-16*  
*Next review: 2026-07-16*  
*Legal contact: [Insert IP counsel]*  
*Confidentiality: Do not distribute outside Complira Ltd.*
