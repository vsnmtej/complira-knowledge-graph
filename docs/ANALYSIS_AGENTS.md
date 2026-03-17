# Analysis Agents - Agentic Architecture for Reporting

**Status**: ✅ **Implemented** (2026-03-02)

## Overview

Analysis agents provide agentic intelligence for vulnerability analysis and reporting. Unlike ingestion agents (which fetch and load data), analysis agents **query existing data** in the knowledge graph to generate insights, reports, and prioritization recommendations.

---

## Architecture

### BaseAnalysisAgent

All analysis agents inherit from `BaseAnalysisAgent`, which provides:

```python
class BaseAnalysisAgent(ABC):
    """
    Abstract base class for analysis and reporting agents.

    Lifecycle:
    1. query_data() - Query relevant data from graph
    2. analyze() - Analyze queried data
    3. format_output() - Format results for presentation
    4. run() - Orchestrate the workflow
    """
```

**Key Differences from BaseIngestionAgent**:
- **Read-only**: Never modifies the knowledge graph
- **Query-based**: Retrieves data using AQL queries
- **Multi-format**: Supports text, JSON, and Markdown output
- **Stateless**: No checkpointing needed (queries are fast)

---

## Available Analysis Agents

### 1. CISAReportAgent

**Purpose**: Generate prioritized vulnerability patching reports

**Command**:
```bash
# Text report (default)
complira report

# JSON output
complira report --format json

# Markdown report
complira report --format markdown > report.md
```

**Data Sources**:
- CISA-enriched vulnerabilities (`cisa_enriched == true`)
- KEV status (`in_cisa_kev`)
- SSVC scores (`cisa_ssvc`)
- CVSS severity (`cisa_cvss`)

**Prioritization Algorithm**:
```python
Priority Score (0-110):
  KEV status:              +50 points
  Active exploitation:     +30 points
  PoC exploitation:        +15 points
  Automatable (yes):       +10 points
  Total technical impact:  +10 points
  CVSS >= 9.0 (Critical):  +10 points
  CVSS >= 7.0 (High):       +5 points
```

**Output Sections**:
1. 🚨 **CRITICAL**: KEV vulnerabilities (immediate action required)
2. 🔥 **HIGH PRIORITY**: Active exploitation detected
3. 💣 **MEDIUM-HIGH**: Automatable + total impact
4. ⚠️ **MEDIUM**: PoC available
5. 📊 **Top 25**: Overall prioritization
6. 📈 **Summary Statistics**: Risk breakdown
7. 💡 **Recommendations**: Action plan

**Example Output**:
```
================================================================================
  CISA-Enhanced Vulnerability Prioritization Report
================================================================================

🚨 CRITICAL: Known Exploited Vulnerabilities (KEV)
ACTION REQUIRED: Patch 8 KEV vulnerabilities immediately per CISA directive.

#    CVE ID             Score Exploit  Auto  Impact  CVSS
--------------------------------------------------------------------------------
  1. CVE-2024-4040      110 active   yes   total   9.8
  2. CVE-2025-54236     110 active   yes   total   9.1
...

📊 Top 25 Vulnerabilities by Priority Score
...

💡 Recommendations
1. IMMEDIATE ACTION (Next 7 Days):
   - Patch all 8 KEV vulnerabilities (CISA directive)
...
```

---

### 2. VulnerabilityAnalysisAgent

**Purpose**: Explore and analyze CISA-enriched vulnerability data

**Command**:
```bash
# Text analysis (default)
complira analyze

# JSON output
complira analyze --format json

# Markdown analysis
complira analyze --format markdown > analysis.md
```

**Data Sources**:
- Overall enrichment statistics
- KEV vulnerabilities (top 10 by date)
- Active exploitation trends
- Automatable + total impact combinations
- SSVC score distribution
- Sample enrichment examples

**Output Sections**:
1. 📊 **CISA Enrichment Statistics**: Coverage and high-priority counts
2. ⚠️ **KEV Vulnerabilities**: Top 10 by date added
3. 🔥 **Active Exploitation**: Top 10 by CVSS score
4. 💣 **Dangerous Combinations**: Automatable + total impact
5. 📈 **SSVC Distribution**: Exploitation, automatable, impact stats
6. 🔍 **Sample Enrichment**: Detailed example of CISA data
7. 💡 **Tips**: Recommended actions

**Example Output**:
```
======================================================================
  CISA Enrichment Data Analysis
======================================================================

📊 CISA Enrichment Statistics
----------------------------------------------------------------------
Total Vulnerabilities:        3,238
CISA Enriched:                802 (24.8%)

🚨 HIGH PRIORITY:
  In KEV Catalog:             8
  Active Exploitation:        8
  PoC Available:              401
  Automatable:                258
  Total Technical Impact:     231

⚠️  Known Exploited Vulnerabilities (KEV) - Top 10
----------------------------------------------------------------------
CVE ID             KEV Date     Exploit  Auto  Impact   CVSS
----------------------------------------------------------------------
CVE-2025-68461     2026-02-20   active   yes   total    7.2
...
```

---

## Usage Examples

### Basic Usage

```bash
# Generate prioritized patching report
complira report

# Explore CISA enrichment data
complira analyze
```

### Advanced Usage

```bash
# Export JSON for dashboards/integrations
complira report --format json > priority_report.json
complira analyze --format json > analysis_data.json

# Generate Markdown documentation
complira report --format markdown > docs/patching_priority.md
complira analyze --format markdown > docs/cisa_analysis.md

# Combine with other commands
complira analyze --format text | grep "KEV"
complira report --format json | jq '.categories.kev.count'
```

### Integration with CI/CD

```yaml
# .github/workflows/security-report.yml
name: Weekly Security Report

on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9 AM

jobs:
  generate-report:
    runs-on: ubuntu-latest
    steps:
      - name: Generate CISA Report
        run: |
          complira report --format markdown > weekly_report.md

      - name: Upload to Confluence/Slack
        uses: slack-notify-action@v1
        with:
          file: weekly_report.md
```

---

## File Structure

```
src/complira_graph/agents/analysis/
├── __init__.py                    # Analysis agents package
├── base.py                        # BaseAnalysisAgent abstract class
├── cisa_report.py                 # CISAReportAgent implementation
└── vulnerability_analysis.py      # VulnerabilityAnalysisAgent implementation
```

---

## Creating Custom Analysis Agents

Follow the BaseAnalysisAgent pattern:

```python
from complira_graph.agents.analysis import BaseAnalysisAgent

class MyCustomAnalysisAgent(BaseAnalysisAgent):
    """Custom analysis agent for specific use case."""

    def query_data(self, **kwargs):
        """Query data from knowledge graph."""
        query = """
        FOR vuln IN vulnerabilities
            FILTER vuln.custom_field == true
            RETURN vuln
        """
        return list(self.db.aql.execute(query))

    def analyze(self, data):
        """Analyze queried data."""
        return {
            "total": len(data),
            "insights": "..."
        }

    def format_output(self, analysis):
        """Format analysis results."""
        if self.output_format == "json":
            return json.dumps(analysis, indent=2)
        else:
            return f"Total: {analysis['total']}"
```

**Register in CLI** (`src/complira_graph/cli.py`):

```python
@cli.command()
@click.option('--format', 'output_format', type=click.Choice(['text', 'json', 'markdown']), default='text')
def my_analysis(output_format: str):
    """Run custom analysis."""
    from .agents.analysis import MyCustomAnalysisAgent

    db = get_db()
    agent = MyCustomAnalysisAgent(db, output_format=output_format)
    result = agent.run()
    print(result['output'])
```

---

## Benefits of Agentic Architecture

### 1. **Modularity**
- Each agent has a single responsibility
- Easy to add new analysis types
- Reusable base class

### 2. **Consistency**
- All agents follow the same pattern
- Uniform CLI interface
- Predictable output formats

### 3. **Flexibility**
- Multiple output formats (text, JSON, markdown)
- Extensible query parameters
- Custom formatting per agent

### 4. **Maintainability**
- Agents live in codebase (not standalone scripts)
- Versioned with the project
- Testable and debuggable

### 5. **Integration**
- CLI commands (`complira report`, `complira analyze`)
- Python API (`agent.run()`)
- Workflow orchestration (future: Prefect tasks)

---

## Comparison: Old vs New

### ❌ Old Approach (Standalone Scripts)

```bash
# Scattered scripts in project root
python generate_patching_report.py
python explore_cisa_data.py
python some_other_analysis.py

# Problems:
# - Not integrated with CLI
# - No consistent interface
# - Hard to maintain
# - Not versioned properly
# - Limited output formats
```

### ✅ New Approach (Agentic Architecture)

```bash
# Unified CLI commands
complira report
complira analyze

# Benefits:
# - Integrated with CLI
# - Consistent interface
# - Easy to maintain
# - Properly versioned
# - Multiple output formats
# - Extensible architecture
```

---

## Performance

Analysis agents are **fast** because they:
- Query data that's already in the graph (no external API calls)
- Use ArangoDB's optimized AQL engine
- Return results in milliseconds

**Typical execution times**:
- `complira report`: 0.03-0.1 seconds
- `complira analyze`: 0.04-0.1 seconds

---

## Future Enhancements

### Planned Analysis Agents

1. **ComplianceReportAgent**
   - Analyze compliance gaps across frameworks
   - Generate compliance status reports
   - Map vulnerabilities to requirements

2. **ThreatIntelligenceAgent**
   - Analyze exploitation trends over time
   - Correlate with threat actor activity
   - Predict emerging threats

3. **AttackSurfaceAgent**
   - Analyze attack paths through the knowledge graph
   - Identify high-risk attack chains
   - Generate attack surface reduction recommendations

4. **ROIAnalysisAgent**
   - Calculate risk reduction from patching
   - Prioritize based on business impact
   - Cost-benefit analysis for remediation

### Workflow Integration

Future: Register analysis agents with Prefect for scheduled reports

```python
# Future: Scheduled reports via Prefect
@flow(name="weekly-security-report")
def weekly_report():
    db = get_db()

    # Run multiple analysis agents
    cisa_report = CISAReportAgent(db, format="markdown")
    compliance_report = ComplianceReportAgent(db, format="markdown")

    # Combine reports
    full_report = combine_reports([
        cisa_report.run(),
        compliance_report.run()
    ])

    # Send to stakeholders
    send_email(full_report)
```

---

## Related Documentation

- `docs/CISA_ADP_AGENT.md` - CISA data ingestion
- `docs/BUG_FIXES.md` - Bug fixes and improvements
- `docs/SESSION_SUMMARY_2026_03_02.md` - Implementation session summary
- `src/complira_graph/agents/base.py` - BaseIngestionAgent pattern
- `src/complira_graph/agents/analysis/base.py` - BaseAnalysisAgent pattern

---

## Testing

```bash
# Test report generation
complira report --format text
complira report --format json
complira report --format markdown

# Test analysis
complira analyze --format text
complira analyze --format json
complira analyze --format markdown

# Verify JSON schema
complira report --format json | jq '.categories.kev.count'
complira analyze --format json | jq '.overview.total_vulnerabilities'
```

---

## Summary

Analysis agents transform raw data into actionable intelligence using:
- **BaseAnalysisAgent** pattern for consistency
- **CLI integration** for ease of use
- **Multiple output formats** for flexibility
- **Fast queries** for performance
- **Extensible architecture** for future growth

**Commands**:
- `complira report` - Prioritized patching report
- `complira analyze` - CISA enrichment analysis

**Next Steps**:
1. Run weekly: `complira incremental CISAADPAgent` (enrich new CVEs)
2. Generate reports: `complira report` (prioritize patching)
3. Monitor trends: `complira analyze` (track changes)
