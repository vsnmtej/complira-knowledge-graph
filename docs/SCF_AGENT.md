# SCF Agent - Secure Controls Framework Integration

**Status**: ✅ **Implemented** (March 2, 2026)

---

## Overview

The **SCFAgent** ingests the Secure Controls Framework (SCF), a comprehensive metaframework that maps to over 100 cybersecurity and privacy laws, regulations, and industry frameworks.

**SCF Features**:
- **~1,200-1,300 controls** organized into **33 domains**
- **Mappings to 100+ frameworks**: NIST SP 800-53, ISO 27001, CIS Controls, PCI-DSS, SOC 2, HIPAA, GDPR, and many more
- **Risk weighting** (1-10 priority scale)
- **NIST CSF functions**: Identify, Protect, Detect, Respond, Recover
- **Assessment objectives** and evidence requests
- **Control maturity levels**

---

## Quick Start

### Just Run the Agent!

The agent **automatically downloads** the SCF Excel file if not present:

```bash
# Run SCF agent - it will auto-download if needed
complira incremental SCFAgent

# Or as part of full seed workflow
complira seed
```

**That's it!** The agent will:
1. Check if `data/scf/scf_2025.xlsx` exists
2. If not, try to download it automatically
3. If download succeeds, proceed with ingestion
4. If download fails, provide manual download instructions

### Manual Download (Fallback)

If automatic download fails, manually download:

1. Visit [https://securecontrolsframework.com/scf-download/](https://securecontrolsframework.com/scf-download/)
2. Download the latest SCF Excel file (e.g., **SCF 2025.4.xlsx**)
3. Place it in the project:

```bash
# Create data directory
mkdir -p data/scf

# Move downloaded file (adjust filename as needed)
mv ~/Downloads/SCF-2025.4.xlsx data/scf/scf_2025.xlsx
```

Then run the agent again.

---

## Data Source

**Official Website**: https://securecontrolsframework.com/
**Download Page**: https://securecontrolsframework.com/scf-download/
**GitHub**: https://github.com/securecontrolsframework/securecontrolsframework
**Format**: Excel (.xlsx)
**License**: Free download (registration may be required)
**Latest Version**: 2025.4 (as of March 2026)

---

## What is SCF?

The **Secure Controls Framework (SCF)** is a metaframework (framework of frameworks) that provides:

### 1. Comprehensive Control Catalog
- **~1,200-1,300 security and privacy controls**
- **33 domains** including:
  - Access Control (ACC)
  - Asset Management (AST)
  - Cryptography (CRY)
  - Data Protection & Privacy (PRI)
  - Incident Response (IRO)
  - Risk Management (RSK)
  - And 27 more...

### 2. Framework Mappings
Maps SCF controls to 100+ frameworks including:
- **Regulatory**: GDPR, HIPAA, CCPA, SOX, GLBA
- **Industry**: PCI-DSS, HITRUST, FedRAMP, StateRAMP
- **Standards**: NIST SP 800-53, ISO 27001/27002, CIS Controls
- **Cloud**: AWS Well-Architected, Azure Security Benchmark, GCP Security Best Practices
- **And many more...**

### 3. Risk-Based Prioritization
- **Risk Weighting**: 1-10 scale for each control
- **NIST CSF Functions**: Identify, Protect, Detect, Respond, Recover
- **Control Types**: Preventive, Detective, Corrective

### 4. Assessment Guidance
- **Assessment Objectives (AOs)**: Criteria for evaluating controls
- **Evidence Request Lists (ERLs)**: Documentation needed for compliance

---

## Agent Implementation

### File Structure

```
src/complira_graph/agents/
└── scf.py                    # SCFAgent implementation
```

### Agent Class

```python
from complira_graph.db import get_db
from complira_graph.agents.scf import SCFAgent

# Initialize agent
db = get_db()
agent = SCFAgent(db)  # Uses default path: data/scf/scf_2025.xlsx

# Or specify custom path
agent = SCFAgent(db, scf_file_path="/path/to/SCF-2025.4.xlsx")

# Run agent
result = agent.run()
```

### Collections Created

#### 1. scf_controls (Document Collection)

Stores SCF control metadata:

```json
{
  "_key": "SCF_ACC_01",
  "scf_id": "SCF-ACC-01",
  "domain": "Access Control",
  "domain_code": "ACC",
  "title": "Access Control Policy",
  "description": "The organization develops, documents, and disseminates access control policies...",
  "assessment_objective": "Determine if access control policy is documented and disseminated...",
  "evidence_request": "Provide access control policy documentation",
  "risk_weighting": 9,
  "function": "Protect",
  "version": "2025"
}
```

**Fields**:
- **scf_id**: Unique SCF control identifier (e.g., `SCF-ACC-01`)
- **domain**: Control domain name (e.g., `Access Control`)
- **domain_code**: Domain abbreviation (e.g., `ACC`)
- **title**: Control title
- **description**: Detailed control objective
- **assessment_objective**: Assessment criteria
- **evidence_request**: Evidence needed for compliance
- **risk_weighting**: Priority (1-10, higher = more important)
- **function**: NIST CSF function (`Identify`, `Protect`, `Detect`, `Respond`, `Recover`)
- **version**: SCF version (e.g., `2025`)

#### 2. cross_framework_mapping (Edge Collection)

Maps SCF controls to other frameworks:

```json
{
  "_from": "scf_controls/SCF_ACC_01",
  "_to": "oscal_controls/AC_1",
  "source_framework": "SCF",
  "target_framework": "NIST SP 800-53",
  "mapping_type": "related",
  "source": "scf"
}
```

**Relationships**:
- **SCF → NIST SP 800-53**: Via `cross_framework_mapping` edges
- **SCF → Regulatory Requirements**: Via `maps_to_requirement` edges (future)

---

## Usage Examples

### Query SCF Controls

```aql
// Get all SCF controls in Access Control domain
FOR control IN scf_controls
    FILTER control.domain == "Access Control"
    RETURN {
        id: control.scf_id,
        title: control.title,
        priority: control.risk_weighting
    }
```

### Find High-Priority Controls

```aql
// Get controls with risk weighting >= 8
FOR control IN scf_controls
    FILTER control.risk_weighting >= 8
    SORT control.risk_weighting DESC
    RETURN control
```

### Map SCF to NIST

```aql
// Find NIST controls mapped to a specific SCF control
FOR control IN scf_controls
    FILTER control.scf_id == "SCF-ACC-01"
    FOR nist IN OUTBOUND control cross_framework_mapping
        RETURN {
            scf: control.scf_id,
            scf_title: control.title,
            nist: nist.control_id,
            nist_title: nist.title
        }
```

### Compliance Gap Analysis

```aql
// Find SCF controls without NIST mappings
FOR control IN scf_controls
    LET mappings = (
        FOR nist IN OUTBOUND control cross_framework_mapping
            RETURN 1
    )
    FILTER LENGTH(mappings) == 0
    RETURN {
        scf_id: control.scf_id,
        title: control.title,
        domain: control.domain
    }
```

---

## CLI Commands

### Run SCF Agent

```bash
# Run SCF agent (requires Excel file in data/scf/scf_2025.xlsx)
complira incremental SCFAgent

# Check results
complira status
```

### Query SCF Data

```bash
# Query all SCF controls
complira query "FOR c IN scf_controls LIMIT 10 RETURN c"

# Count controls by domain
complira query "
FOR c IN scf_controls
    COLLECT domain = c.domain WITH COUNT INTO count
    SORT count DESC
    RETURN {domain, count}
"

# Find high-priority controls
complira query "
FOR c IN scf_controls
    FILTER c.risk_weighting >= 9
    RETURN {id: c.scf_id, title: c.title, priority: c.risk_weighting}
"
```

---

## Excel File Structure

The SCF Excel file typically contains:

### Expected Columns

The agent automatically detects column names (handles variations):

| Column Name | Variations | Required | Description |
|-------------|-----------|----------|-------------|
| **SCF ID** | `scf id`, `scf_id`, `control id`, `id` | ✅ | Control identifier (e.g., `SCF-ACC-01`) |
| **Domain** | `domain`, `control domain`, `category` | ❌ | Control domain name |
| **Title** | `title`, `control title`, `name` | ❌ | Control title |
| **Description** | `description`, `control description`, `objective` | ❌ | Control objective |
| **Assessment Objective** | `assessment objective`, `ao`, `assessment criteria` | ❌ | Assessment criteria |
| **Evidence Request** | `evidence request`, `erl`, `evidence` | ❌ | Evidence needed |
| **Risk Weighting** | `risk weighting`, `weighting`, `priority` | ❌ | Priority (1-10) |
| **Function** | `function`, `control function`, `csf function`, `nist function` | ❌ | NIST CSF function |
| **NIST 800-53** | Columns containing `nist` and `800-53` | ❌ | NIST control mappings |

### Example Row

```
| SCF ID      | Domain          | Title                 | Description              | Risk Weighting | Function |
|-------------|-----------------|----------------------|--------------------------|----------------|----------|
| SCF-ACC-01  | Access Control  | Access Control Policy| The organization develops...| 9              | Protect  |
```

---

## Troubleshooting

### File Not Found Error

```
FileNotFoundError: SCF Excel file not found at: data/scf/scf_2025.xlsx

Please download the SCF Excel file from:
https://securecontrolsframework.com/scf-download/
```

**Solution**:
1. Download SCF Excel file from official website
2. Create directory: `mkdir -p data/scf`
3. Move file: `mv ~/Downloads/SCF-2025.4.xlsx data/scf/scf_2025.xlsx`

### Custom File Path

If you want to use a different location:

```python
from complira_graph.agents.scf import SCFAgent

agent = SCFAgent(db, scf_file_path="/custom/path/scf_file.xlsx")
result = agent.run()
```

### Column Name Mismatch

The agent automatically handles column name variations. If it doesn't find expected columns:

1. Check the Excel file sheet names (agent tries: "SCF Controls", "Controls", "Master", "Control Catalog")
2. Verify column headers match expected patterns
3. Check agent logs for "Detected SCF columns" to see what was found

---

## Performance

- **Controls**: ~1,200-1,300 documents
- **Mappings**: ~2,000-5,000 cross-framework edges (depends on SCF version)
- **Ingestion Time**: ~5-10 seconds
- **Memory**: ~50-100 MB

---

## Updates

SCF releases new versions periodically. To update:

1. Download latest version from [SCF website](https://securecontrolsframework.com/scf-download/)
2. Replace file in `data/scf/scf_2025.xlsx` (or update filename)
3. Re-run agent: `complira incremental SCFAgent`

**Recent Versions**:
- **2025.4**: Minor update (current)
- **2025.3**: Major update
- **2025.2**: Major update (79 new AI/ML controls)
- **2025.1**: Minor update

---

## Integration with Other Agents

SCF integrates with existing framework agents:

### NIST SP 800-53 (OSCAL)
```aql
// SCF → NIST mappings via cross_framework_mapping edges
FOR scf IN scf_controls
    FOR nist IN OUTBOUND scf cross_framework_mapping
        FILTER nist._id LIKE "oscal_controls/%"
        RETURN {scf: scf.scf_id, nist: nist.control_id}
```

### Regulatory Requirements
```aql
// SCF → Regulatory mappings (future enhancement)
FOR scf IN scf_controls
    FOR req IN OUTBOUND scf maps_to_requirement
        RETURN {scf: scf.scf_id, requirement: req.requirement_id}
```

---

## Future Enhancements

1. **Automated Download**: Fetch SCF directly from official source (if API becomes available)
2. **Additional Framework Mappings**: ISO 27001, CIS Controls, PCI-DSS edges
3. **Control Families**: Group controls by family/category
4. **Maturity Levels**: Track control maturity (L1, L2, L3)
5. **Implementation Guidance**: Extract implementation examples from SCF
6. **Compliance Scoring**: Calculate compliance coverage across frameworks

---

## Related Documentation

- **SCF Official Website**: https://securecontrolsframework.com/
- **SCF Overview & Practitioner Guidebook**: [Download PDF](https://securecontrolsframework.com/content/SCF-Recommended-Practices.pdf)
- **SCF GitHub**: https://github.com/securecontrolsframework/securecontrolsframework
- **NIST Cybersecurity Framework**: https://www.nist.gov/cyberframework

---

## Summary

The **SCFAgent** provides:

✅ **~1,200-1,300 security and privacy controls**
✅ **33 domains** covering all cybersecurity areas
✅ **Mappings to 100+ frameworks** (NIST, ISO, CIS, PCI-DSS, etc.)
✅ **Risk-based prioritization** (1-10 weighting)
✅ **Assessment guidance** (AOs and ERLs)
✅ **NIST CSF alignment** (Identify, Protect, Detect, Respond, Recover)

**Usage**:
1. Download SCF Excel from official website (one-time)
2. Place in `data/scf/scf_2025.xlsx`
3. Run `complira incremental SCFAgent`
4. Query `scf_controls` collection for compliance mapping

**Next Steps**:
- Download SCF Excel file
- Run agent to populate controls
- Use for compliance gap analysis
- Map to existing NIST/regulatory frameworks
