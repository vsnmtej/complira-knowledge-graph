# Phase 5: SBOM/SARIF Upload & Analysis UI

**Date**: 2026-03-16
**Status**: 📋 PLANNING
**Priority**: HIGH (Core product feature)
**Dependencies**: Phase 5 Web UI (Auth, Tokens)

---

## Executive Summary

Build an interactive web UI for uploading SBOM (CycloneDX/SPDX) and SARIF files, visualizing vulnerability analysis, compliance violations, and regulatory impact. This transforms Complira from an API-only service into a self-service platform where users can upload files and instantly see actionable insights.

---

## User Flow

### Happy Path
1. **Login** → User authenticates with organization credentials
2. **Upload** → Drag-and-drop SBOM or SARIF file (or paste JSON)
3. **Processing** → File sent to `/v1/scan/ingest`, enrichment pipeline runs
4. **Results** → Real-time dashboard shows:
   - Vulnerability summary (Critical/High/Medium/Low)
   - Compliance violations by framework (FDA, CRA, IEC, NIST)
   - Exploitability analysis (EPSS scores, KEV status)
   - Component inventory with risk scores
   - Recommended remediations
5. **Export** → Download VEX document, compliance report, or CSV

### Time to Insight
- **Upload to results**: < 30 seconds (for typical SBOM with 200 components)
- **Real-time progress**: WebSocket updates during enrichment
- **Cached re-analysis**: Instant (if same SBOM re-uploaded)

---

## Architecture

### Technology Stack

**Frontend**:
- **File Upload**: react-dropzone (drag-and-drop)
- **Real-time Updates**: WebSockets (or Server-Sent Events)
- **Charts**: Recharts (pie, bar, line charts)
- **Data Tables**: TanStack Table (sortable, filterable)
- **Export**: jsPDF (PDF reports), xlsx (Excel export)

**Backend Extensions**:
- WebSocket endpoint: `/ws/scan/{session_id}` (real-time progress)
- Results endpoint: `/v1/scan/{session_id}/analysis` (dashboard data)
- Export endpoint: `/v1/scan/{session_id}/report` (PDF/XLSX generation)

**Processing Flow**:
```
User uploads file → `/v1/scan/ingest`
                  ↓
            Scan session created
                  ↓
        WebSocket connection established
                  ↓
  Background enrichment (CVE → CWE → ATT&CK → NIST → Regulatory)
                  ↓
    WebSocket sends progress updates (10%, 30%, 60%, 100%)
                  ↓
         Frontend updates dashboard in real-time
                  ↓
            Analysis complete → Show full results
```

---

## Web UI Pages

### 1. **Scans Dashboard** (`/dashboard/scans`)

**Purpose**: List all uploaded scans for the organization

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│ Scans                                        [+ Upload] │
├─────────────────────────────────────────────────────────┤
│ Filters: [All ▾] [Last 7 days ▾] [Search...]           │
├─────────────────────────────────────────────────────────┤
│ Scan Name        │ Type    │ Findings │ Date     │ •••│
├─────────────────────────────────────────────────────────┤
│ app-v1.2.3       │ SBOM    │ 🔴 42 H  │ 2h ago   │    │
│ CycloneDX        │         │ 🟠 156 M │          │    │
│                                                          │
│ backend-api      │ SARIF   │ 🔴 12 H  │ 1 day ago│    │
│ Semgrep scan     │         │ 🟠 43 M  │          │    │
│                                                          │
│ mobile-ios       │ SBOM    │ 🟢 0 H   │ 3 days   │    │
│ SPDX 2.3         │         │ 🟠 89 M  │          │    │
└─────────────────────────────────────────────────────────┘
```

**Features**:
- Sort by: Date, Severity, Findings count
- Filter by: Type (SBOM/SARIF), Date range, Severity
- Bulk actions: Export all, Delete selected
- Quick stats: Total scans, Total vulnerabilities, Avg time to fix

---

### 2. **Upload Page** (`/dashboard/scans/upload`)

**Purpose**: Upload SBOM or SARIF files

**UI Design**:
```
┌─────────────────────────────────────────────────────────┐
│ Upload Scan                                             │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ╔═══════════════════════════════════════════════╗    │
│   ║                                                ║    │
│   ║     📄 Drag and drop your file here           ║    │
│   ║                                                ║    │
│   ║          or click to browse                    ║    │
│   ║                                                ║    │
│   ║  Supported formats:                            ║    │
│   ║  • CycloneDX 1.4, 1.5 (.json, .xml)          ║    │
│   ║  • SPDX 2.2, 2.3 (.json)                     ║    │
│   ║  • SARIF 2.1.0 (.json)                        ║    │
│   ║                                                ║    │
│   ╚═══════════════════════════════════════════════╝    │
│                                                          │
│   Scan Details (Optional):                              │
│   ┌──────────────────────────────────────────┐          │
│   │ Name:  [app-v1.2.3_____________________] │          │
│   │ Repo:  [github.com/acme/app____________] │          │
│   │ Branch:[main___________________________] │          │
│   │ Commit:[a3f9d2c________________________] │          │
│   └──────────────────────────────────────────┘          │
│                                                          │
│   Frameworks to Check:                                  │
│   ☑ FDA 524B (Medical Devices)                          │
│   ☑ EU Cyber Resilience Act                             │
│   ☐ IEC 62304 (Medical Software)                        │
│   ☑ NIST 800-53 (Federal Controls)                      │
│                                                          │
│                               [Cancel] [Upload & Analyze]│
└─────────────────────────────────────────────────────────┘
```

**Upload Options**:
1. **Drag-and-drop**: Drop file directly into upload zone
2. **File browser**: Click to select from filesystem
3. **Paste JSON**: Tab to paste raw JSON content
4. **GitHub Integration**: Fetch SBOM from GitHub repo (future)

**Validation**:
- File size limit: 50MB (configurable)
- Format validation: Parse JSON/XML before upload
- Schema validation: Check CycloneDX/SPDX/SARIF spec compliance
- Duplicate detection: Warn if identical SBOM uploaded recently

---

### 3. **Analysis Progress** (`/dashboard/scans/{id}/processing`)

**Purpose**: Show real-time enrichment progress

**UI (WebSocket updates)**:
```
┌─────────────────────────────────────────────────────────┐
│ Analyzing app-v1.2.3                                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ⏳ Enrichment in progress...                          │
│                                                          │
│   ████████████████░░░░░░░░░░ 67%                        │
│                                                          │
│   ✅ SBOM parsed (243 components found)                 │
│   ✅ CVE lookup complete (156 vulnerabilities)          │
│   ✅ EPSS scores fetched                                │
│   ✅ KEV status checked                                 │
│   ⏳ CWE mapping in progress...                         │
│   ⏳ ATT&CK technique analysis...                       │
│   ⏳ Compliance check (FDA 524B, CRA, NIST)...          │
│   ⏳ Generating recommendations...                      │
│                                                          │
│   Estimated time remaining: 8 seconds                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**WebSocket Events**:
- `parsing`: SBOM/SARIF file parsed
- `components_extracted`: Component count
- `vulnerabilities_found`: CVE count
- `enrichment_progress`: Percentage (0-100)
- `enrichment_complete`: Final results ready
- `error`: Processing failed with error message

---

### 4. **Analysis Results Dashboard** (`/dashboard/scans/{id}`)

**Purpose**: Comprehensive vulnerability analysis and compliance insights

**Layout (Multi-section dashboard)**:

#### **A. Executive Summary** (Top section)
```
┌─────────────────────────────────────────────────────────┐
│ app-v1.2.3 Analysis Results                             │
│ Scanned: 2 hours ago │ 243 components │ 156 vulnerabilities│
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Risk Score: 🔴 CRITICAL (8.7/10)                       │
│                                                          │
│  [🔴 42 Critical] [🟠 89 High] [🟡 21 Medium] [⚪ 4 Low]│
│                                                          │
│  ⚠️  Top Risks:                                         │
│  • 12 vulnerabilities in Known Exploited Vulnerabilities│
│  • 8 components with active exploits (EPSS > 0.5)       │
│  • 3 compliance violations (FDA 524B critical controls) │
│                                                          │
│  [📄 Export VEX] [📊 Download Report] [🔄 Re-scan]     │
└─────────────────────────────────────────────────────────┘
```

#### **B. Vulnerability Breakdown** (Charts)
```
┌──────────────────────────┬──────────────────────────────┐
│ Severity Distribution    │ Exploitability Heatmap       │
│                          │                              │
│     🔴 Critical: 42      │  High EPSS (>0.5): 8 CVEs    │
│     🟠 High:     89      │  Medium EPSS: 34 CVEs        │
│     🟡 Medium:   21      │  Low EPSS: 114 CVEs          │
│     ⚪ Low:       4      │  KEV (CISA): 12 CVEs ⚠️      │
│                          │                              │
│  [Pie chart visual]      │  [Bar chart visual]          │
└──────────────────────────┴──────────────────────────────┘
```

#### **C. Compliance Status** (Framework cards)
```
┌─────────────────────────────────────────────────────────┐
│ Regulatory Compliance                                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  FDA 524B (Medical Devices)              🔴 FAIL        │
│  ├─ 3 critical control violations                       │
│  ├─ V.C.1: Cybersecurity Testing (CVE-2023-12345)       │
│  ├─ V.A.1: SBOM required ✅                             │
│  └─ Remediation: Patch Log4j to 2.17.1+                 │
│                                                          │
│  EU Cyber Resilience Act                 🟡 PARTIAL     │
│  ├─ 1 critical, 5 medium violations                     │
│  ├─ Annex I §2.1: Vulnerability handling (delayed)      │
│  └─ Remediation: Update 8 high-severity CVEs            │
│                                                          │
│  NIST 800-53                             🟢 PASS        │
│  ├─ 0 critical violations                               │
│  └─ All controls satisfied                              │
└─────────────────────────────────────────────────────────┘
```

#### **D. Component Inventory** (Sortable table)
```
┌─────────────────────────────────────────────────────────┐
│ Components (243 total)                     [Export CSV] │
├─────────────────────────────────────────────────────────┤
│ Component      │ Version │ Vulns │ Max CVSS │ Risk     │
├─────────────────────────────────────────────────────────┤
│ log4j-core     │ 2.14.1  │ 🔴 12 │ 10.0 🔥  │ CRITICAL │
│ spring-core    │ 5.3.10  │ 🟠 3  │ 7.5      │ HIGH     │
│ jackson-databind│ 2.12.3 │ 🟠 2  │ 7.2      │ HIGH     │
│ gson           │ 2.8.9   │ 🟡 1  │ 5.3      │ MEDIUM   │
│ commons-io     │ 2.11.0  │ ⚪ 0  │ -        │ SAFE ✅  │
└─────────────────────────────────────────────────────────┘
│ 1-5 of 243     [<] [1] [2] [3] ... [49] [>]            │
└─────────────────────────────────────────────────────────┘
```

**Features**:
- Click component → Drill down to specific CVEs
- Sort by: Risk, Vulns, CVSS, Name
- Filter by: License, Ecosystem (npm, maven, pypi)

#### **E. Vulnerability Details** (Expandable table)
```
┌─────────────────────────────────────────────────────────┐
│ Vulnerabilities (156 total)               [Export JSON]│
├─────────────────────────────────────────────────────────┤
│ CVE ID        │ Component  │ CVSS │ EPSS  │ KEV │ Fix  │
├─────────────────────────────────────────────────────────┤
│ ▶ CVE-2021-   │ log4j-core │ 10.0 │ 0.97  │ ⚠️  │ 2.17 │
│   44228       │ 2.14.1     │ 🔥   │ 🔥    │     │ .1   │
│                                                          │
│ ▶ CVE-2023-   │ spring-    │ 9.8  │ 0.65  │     │ 5.3  │
│   20863       │ core 5.3.10│ 🔴   │ 🔴    │     │ .20  │
│                                                          │
│ ▼ CVE-2022-   │ jackson-   │ 7.5  │ 0.12  │     │ 2.13 │
│   42003       │ databind   │ 🟠   │ 🟡    │     │ .3   │
│   └─ CWE: CWE-502 (Deserialization)                    │
│   └─ ATT&CK: T1190 (Exploit Public-Facing Application) │
│   └─ NIST: SC-7 (Boundary Protection)                  │
│   └─ FDA: V.C.1 (Cybersecurity Testing) VIOLATED       │
│   └─ Description: Jackson Databind before 2.13.3       │
│      allows attackers to execute arbitrary code...      │
│   └─ [📄 View Full Details] [🔧 Remediation Plan]     │
└─────────────────────────────────────────────────────────┘
```

**Expandable Row Features**:
- Full CVE description
- Attack chain visualization (CVE → CWE → CAPEC → ATT&CK)
- Compliance impact (which frameworks violated)
- Remediation guidance (upgrade path, workarounds)
- External links (NVD, GHSA, vendor advisories)

#### **F. Remediation Recommendations** (Prioritized list)
```
┌─────────────────────────────────────────────────────────┐
│ Recommended Actions (Prioritized by Risk)               │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ 🔥 CRITICAL (Fix within 24 hours)                       │
│                                                          │
│ 1. Upgrade log4j-core: 2.14.1 → 2.17.1                  │
│    Fixes: 12 CVEs (10 CRITICAL, 2 HIGH)                 │
│    Impact: Removes RCE vulnerability (CVE-2021-44228)   │
│    Command: `npm install log4j-core@2.17.1`             │
│    [📋 Copy Command] [✅ Mark as Done]                  │
│                                                          │
│ 2. Upgrade spring-core: 5.3.10 → 5.3.20                 │
│    Fixes: 3 CVEs (3 HIGH)                               │
│    Impact: Patches Spring4Shell vulnerability           │
│    [📋 Copy Command] [✅ Mark as Done]                  │
│                                                          │
│ 🟠 HIGH (Fix within 7 days)                             │
│                                                          │
│ 3. Upgrade jackson-databind: 2.12.3 → 2.13.3            │
│    Fixes: 2 CVEs (2 HIGH)                               │
│    [📋 Copy Command]                                    │
│                                                          │
│ [Export Remediation Plan (Markdown)]                    │
└─────────────────────────────────────────────────────────┘
```

---

### 5. **VEX Export** (`/dashboard/scans/{id}/vex`)

**Purpose**: Generate and download VEX documents (CycloneDX format)

**UI**:
```
┌─────────────────────────────────────────────────────────┐
│ Generate VEX Document                                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ VEX (Vulnerability Exploitability eXchange) documents   │
│ provide machine-readable vulnerability status for your  │
│ software components.                                     │
│                                                          │
│ Configure VEX Options:                                  │
│                                                          │
│ Status Assignments:                                      │
│ ┌──────────────────────────────────────────┐            │
│ │ CVE-2021-44228: ⦿ Affected                            │
│ │                 ○ Not Affected                        │
│ │                 ○ Under Investigation                 │
│ │                                                        │
│ │ Justification: [Component removed in build ▾]         │
│ │ Response: [Will not fix - EOL product    ▾]          │
│ │ Detail: [_________________________________]            │
│ └──────────────────────────────────────────┘            │
│                                                          │
│ Format:                                                  │
│ ⦿ CycloneDX 1.5 (recommended)                           │
│ ○ CSAF 2.0                                              │
│                                                          │
│               [Cancel] [Generate & Download VEX]        │
└─────────────────────────────────────────────────────────┘
```

**VEX Statuses** (per CVE):
- **Affected**: Vulnerability present and exploitable
- **Not Affected**: Vulnerable code present but not reachable
- **Under Investigation**: Analysis in progress
- **Fixed**: Patched in this version

**Justifications** (if "Not Affected"):
- Component not present
- Vulnerable code not in execute path
- Inline mitigations already exist
- Vulnerable code not present

---

### 6. **Compliance Report Export** (`/dashboard/scans/{id}/report`)

**Purpose**: Generate PDF/Excel compliance reports for auditors

**Report Sections**:
1. **Executive Summary**: Risk score, top findings
2. **Vulnerability Inventory**: Full CVE list with CVSS, EPSS
3. **Compliance Matrix**: Framework-by-framework violations
4. **Remediation Plan**: Prioritized fix recommendations
5. **Component Bill of Materials**: Full SBOM with licenses
6. **Appendix**: Attack chain diagrams, external references

**Export Formats**:
- **PDF**: Formatted report with charts (for stakeholders)
- **Excel**: Detailed spreadsheet (for tracking remediation)
- **CSV**: Raw data (for import into other tools)
- **Markdown**: Plain text report (for GitHub/Jira)

---

## API Extensions (Backend)

### New Endpoints

#### 1. **WebSocket: Real-time Scan Progress**
```
WS /ws/scan/{session_id}
```

**Events Sent to Client**:
```json
{
  "event": "enrichment_progress",
  "data": {
    "percentage": 67,
    "stage": "cwe_mapping",
    "message": "Mapping CWE weaknesses...",
    "components_processed": 163,
    "components_total": 243
  }
}
```

**Connection Lifecycle**:
1. Client connects after file upload
2. Server sends progress events every 2 seconds
3. Final event: `enrichment_complete` with `session_id`
4. Client disconnects and navigates to results page

#### 2. **GET `/v1/scan/{session_id}/analysis`**

**Purpose**: Fetch structured data for dashboard visualization

**Response**:
```json
{
  "session_id": "scan_abc123",
  "summary": {
    "total_components": 243,
    "total_vulnerabilities": 156,
    "risk_score": 8.7,
    "risk_level": "CRITICAL",
    "by_severity": {
      "CRITICAL": 42,
      "HIGH": 89,
      "MEDIUM": 21,
      "LOW": 4
    }
  },
  "exploitability": {
    "kev_count": 12,
    "high_epss_count": 8,
    "active_exploits_count": 3
  },
  "compliance": [
    {
      "framework": "FDA_524B",
      "status": "FAIL",
      "violations": [
        {
          "requirement_id": "V.C.1",
          "title": "Cybersecurity Testing",
          "severity": "CRITICAL",
          "violated_by_cves": ["CVE-2021-44228", "CVE-2023-20863"]
        }
      ],
      "critical_count": 3,
      "high_count": 0,
      "medium_count": 0
    }
  ],
  "components": [
    {
      "name": "log4j-core",
      "version": "2.14.1",
      "purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
      "vulnerability_count": 12,
      "max_cvss": 10.0,
      "risk_level": "CRITICAL",
      "cves": ["CVE-2021-44228", "..."]
    }
  ],
  "vulnerabilities": [
    {
      "cve_id": "CVE-2021-44228",
      "component": "log4j-core@2.14.1",
      "cvss_score": 10.0,
      "epss_score": 0.974,
      "kev": true,
      "cwe_ids": ["CWE-502"],
      "attack_techniques": ["T1190"],
      "nist_controls": ["SC-7"],
      "fix_version": "2.17.1",
      "description": "Apache Log4j2 <=2.14.1 JNDI features..."
    }
  ],
  "recommendations": [
    {
      "priority": "CRITICAL",
      "action": "upgrade",
      "component": "log4j-core",
      "from_version": "2.14.1",
      "to_version": "2.17.1",
      "fixes_cves": ["CVE-2021-44228", "..."],
      "command": "npm install log4j-core@2.17.1"
    }
  ]
}
```

#### 3. **POST `/v1/scan/{session_id}/report`**

**Purpose**: Generate PDF/Excel compliance report

**Request**:
```json
{
  "format": "pdf",  // pdf, xlsx, csv, markdown
  "sections": ["summary", "vulnerabilities", "compliance", "remediation"],
  "frameworks": ["FDA_524B", "CRA", "NIST"],
  "include_charts": true
}
```

**Response**:
```json
{
  "report_url": "https://s3.amazonaws.com/.../report_abc123.pdf",
  "expires_at": "2026-03-17T10:00:00Z",
  "file_size_bytes": 2457600
}
```

---

## User Stories

### Story 1: First-Time Upload
**As a** security engineer
**I want to** upload my application's SBOM and see vulnerability analysis
**So that** I can understand my security posture

**Acceptance Criteria**:
1. Drag-and-drop CycloneDX JSON file
2. File validated (schema check) before upload
3. Real-time progress shown during enrichment
4. Results displayed within 30 seconds
5. Executive summary shows risk score and top findings

### Story 2: Compliance Audit Prep
**As a** quality manager at a medical device company
**I want to** generate a PDF compliance report for FDA auditors
**So that** I can demonstrate vulnerability management process

**Acceptance Criteria**:
1. Select FDA 524B framework filter
2. Generate PDF report with charts
3. Report includes: SBOM, vulnerabilities, compliance violations, remediation plan
4. Download link expires after 24 hours
5. Report watermarked with organization name and timestamp

### Story 3: Remediation Tracking
**As a** DevOps engineer
**I want to** track which vulnerabilities I've fixed
**So that** I can show progress over time

**Acceptance Criteria**:
1. Upload new SBOM after patching
2. Dashboard shows "Fixed" badge for resolved CVEs
3. Trend chart shows vulnerability count over time
4. Export remediation history as CSV

---

## Implementation Plan

### Phase 5D: SBOM/SARIF Upload UI (3-4 weeks)

**Week 1: File Upload**
- [ ] Upload page with drag-and-drop (react-dropzone)
- [ ] File validation (CycloneDX, SPDX, SARIF schemas)
- [ ] Integration with `/v1/scan/ingest` endpoint
- [ ] WebSocket connection for real-time progress
- [ ] Progress page with animated loading

**Week 2: Analysis Dashboard**
- [ ] Executive summary component (risk score, severity breakdown)
- [ ] Charts (Recharts): Pie chart (severity), Bar chart (exploitability)
- [ ] Compliance status cards (FDA, CRA, IEC, NIST)
- [ ] Component inventory table (TanStack Table)
- [ ] Vulnerability details table with expandable rows

**Week 3: Insights & Recommendations**
- [ ] Attack chain visualization (CVE → CWE → ATT&CK)
- [ ] Remediation recommendations (prioritized list)
- [ ] Fix command generator (copy-to-clipboard)
- [ ] Trend charts (vulnerability count over time)
- [ ] Component risk scores (CVSS + EPSS weighted)

**Week 4: Export & Reports**
- [ ] VEX generator UI (status assignments, justifications)
- [ ] PDF report generation (jsPDF)
- [ ] Excel export (xlsx library)
- [ ] CSV export (component inventory, vulnerability list)
- [ ] Markdown export (for GitHub issues)

---

## Technical Challenges

### Challenge 1: Large SBOM Files
**Problem**: SBOM with 10,000+ components takes 5+ minutes to enrich
**Solution**:
- Stream processing (enrich in batches of 100 components)
- WebSocket progress updates every 2 seconds
- Background job queue (Celery or Prefect)
- Cached results (don't re-enrich same components)

### Challenge 2: Real-time Updates
**Problem**: WebSocket connection drops during long enrichment
**Solution**:
- Server-Sent Events (SSE) as fallback
- Heartbeat ping every 30 seconds
- Reconnection logic with exponential backoff
- Progress saved to database (resume on reconnect)

### Challenge 3: Report Generation Performance
**Problem**: PDF generation blocks web server
**Solution**:
- Async report generation (background job)
- Return signed S3 URL instead of streaming file
- 24-hour expiration on S3 links
- Report caching (same scan → same report)

---

## UI/UX Design Principles

### Design System
- **Typography**: Inter font (clean, modern)
- **Colors**:
  - Critical: Red (#EF4444)
  - High: Orange (#F97316)
  - Medium: Yellow (#EAB308)
  - Low: Gray (#6B7280)
  - Safe: Green (#10B981)
- **Icons**: Heroicons (consistent icon family)
- **Spacing**: 4px grid system

### Accessibility
- WCAG 2.1 AA compliance
- Keyboard navigation (all tables, modals)
- Screen reader support (aria-labels)
- Color-blind friendly (patterns + colors)

### Responsive Design
- **Desktop**: Full dashboard (3-column layout)
- **Tablet**: 2-column layout (charts stack)
- **Mobile**: Single column (tables scroll horizontally)

---

## Success Metrics

### User Engagement
- **Upload rate**: 80%+ users upload SBOM within 7 days of signup
- **Re-upload frequency**: 2+ uploads per week (CI/CD integration)
- **Time on results page**: Avg 5+ minutes (engaged with insights)
- **Export rate**: 40%+ generate VEX or PDF report

### Performance
- **Upload to results**: 95th percentile < 45 seconds
- **Dashboard load time**: < 2 seconds (cached)
- **WebSocket stability**: 99%+ uptime during enrichment

### Business
- **Conversion**: 30%+ free users upgrade to paid (after seeing insights)
- **Support tickets**: < 2 per 100 uploads (self-explanatory UI)

---

## Open Questions

1. **Scan History Retention**: How long to keep uploaded SBOMs?
   - **Recommendation**: 90 days (Free), 1 year (Pro), Forever (Enterprise)

2. **Duplicate SBOM Detection**: Warn if identical SBOM uploaded?
   - **Recommendation**: Yes - show "No changes detected" with comparison

3. **Scheduled Scans**: Allow recurring SBOM uploads from GitHub?
   - **Recommendation**: Phase 6 (GitHub App integration)

4. **Multi-SBOM Comparison**: Compare two SBOMs side-by-side?
   - **Recommendation**: Phase 6 (Diff view for before/after patching)

5. **Collaboration**: Share scan results with team members?
   - **Recommendation**: Yes - per-scan permissions (Viewer, Editor, Owner)

---

## Next Steps

1. **Review & Approval**: Get stakeholder sign-off on UI design
2. **Create Figma Mockups**: High-fidelity designs for all pages
3. **API Specification**: Document `/v1/scan/{id}/analysis` response schema
4. **Spike: WebSocket vs SSE**: 2-day spike on real-time update architecture
5. **Kickoff Sprint**: Start Phase 5D (SBOM Upload UI)

---

## References

- **react-dropzone**: https://react-dropzone.js.org/
- **Recharts**: https://recharts.org/
- **TanStack Table**: https://tanstack.com/table/
- **jsPDF**: https://github.com/parallax/jsPDF
- **CycloneDX VEX**: https://cyclonedx.org/use-cases/#vex
- **SARIF Spec**: https://docs.oasis-open.org/sarif/sarif/v2.1.0/

---

**Document Version**: 1.0
**Last Updated**: 2026-03-16
**Status**: 📋 PLANNING (Integrated with Phase 5 Web UI)
