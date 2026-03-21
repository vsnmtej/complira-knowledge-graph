# Investigation Notes - Phase 5 Web UI

**Ticket**: phase-5-web-ui
**Investigation Date**: 2026-03-16
**Status**: Complete

---

## Executive Summary

Phase 5 aims to build a web-based user interface for Complira's cybersecurity compliance platform. Investigation reveals **substantial existing infrastructure** that can be leveraged, reducing implementation scope significantly. The backend already has:

- ✅ API key authentication framework (bcrypt hashing, header validation)
- ✅ Account management endpoints (`/v1/account/*`)
- ✅ Customer profile model with tier-based access
- ✅ Scan ingestion pipeline (`/v1/scan/ingest`)
- ✅ FastAPI application with CORS, error handling, versioned routing

**Key Finding**: We have ~40% of backend functionality already implemented. Frontend is greenfield (no existing UI). Primary work is:
1. Frontend Next.js application (new)
2. Authentication endpoints expansion (extend existing)
3. WebSocket real-time updates (new)
4. Dashboard UI components (new)

---

## Codebase Structure Analysis

### Backend Architecture (FastAPI)

**Location**: `src/api/`

**Structure**:
```
src/api/
├── main.py                    # App entry point, CORS, health check
├── core/
│   ├── config.py              # Environment configuration
│   ├── database.py            # ArangoDB connection management
│   ├── dependencies.py        # FastAPI dependency injection
│   ├── security.py            # API key authentication (✅ EXISTING)
│   └── cache.py               # Response caching
├── models/
│   ├── requests/              # Pydantic request models
│   │   ├── account.py         # CreateAPIKeyRequest (✅ EXISTING)
│   │   ├── scan.py            # SBOM/SARIF ingestion (✅ EXISTING)
│   │   └── vex.py             # VEX generation
│   └── responses/             # Pydantic response models
│       ├── account.py         # APIKeyResponse (✅ EXISTING)
│       ├── scan.py            # ScanResponse (✅ EXISTING)
│       └── enrichment.py      # EnrichmentResponse
├── services/
│   ├── enrichment.py          # Vulnerability enrichment service (✅ EXISTING)
│   ├── scan.py                # Scan processing service
│   └── vex.py                 # VEX document generation
├── repositories/
│   ├── enrichment.py          # Database queries for enrichment
│   ├── vulnerability.py       # CVE, CWE, ATT&CK queries
│   └── regulatory.py          # Compliance framework queries
└── v1/
    ├── router.py              # Main v1 router (✅ EXISTING)
    └── endpoints/
        ├── account.py         # /v1/account/* (✅ EXISTING - API keys only)
        ├── scan.py            # /v1/scan/ingest (✅ EXISTING)
        ├── enrichment.py      # /v1/enrich (✅ EXISTING)
        ├── vex.py             # /v1/vex (✅ EXISTING)
        └── reference.py       # /v1/reference (✅ EXISTING)
```

### Database Schema (ArangoDB)

**Reference Database** (`complira_reference`):
- ✅ `customer_profiles` - Multi-tenant customer records (✅ EXISTING)
- ✅ `vulnerabilities` - CVEs from NVD, OSV, GHSA
- ✅ `weaknesses` - CWE records
- ✅ `attack_techniques` - MITRE ATT&CK
- ✅ `controls` - NIST 800-53, OSCAL
- ✅ `regulatory_requirements` - FDA, CRA, IEC frameworks

**Customer-Specific Databases** (`complira_customer_{customer_id}`):
- ✅ `scans` - Uploaded SBOM/SARIF files (schema exists)
- ✅ `scan_results` - Enrichment results
- ⚠️ **MISSING**: `users` collection (for web UI login)
- ⚠️ **MISSING**: `api_tokens` collection (currently inline in customer_profiles)
- ⚠️ **MISSING**: `audit_log` collection

### Frontend - Greenfield

**Status**: No existing frontend code

**Evidence**:
- No `package.json` in root
- No `frontend/`, `web/`, `ui/`, `client/`, or `next/` directories
- No React, Next.js, or UI dependencies

**Implication**: Complete frontend stack needs to be created from scratch

---

## Existing Features Assessment

### ✅ EXISTING: API Key Authentication

**File**: `src/api/core/security.py`

**Functionality**:
- Bcrypt hashing for API keys (configurable rounds via `API_KEY_HASH_ROUNDS`)
- API key header extraction (`X-API-Key`)
- Customer identification via API key lookup
- FastAPI dependency for protected routes (`get_current_customer`)

**Code Snippet**:
```python
def hash_api_key(api_key: str) -> str:
    settings = get_cloud_settings()
    salt = bcrypt.gensalt(rounds=settings.API_KEY_HASH_ROUNDS)
    return bcrypt.hashpw(api_key.encode(), salt).decode()

def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    return bcrypt.checkpw(api_key.encode(), api_key_hash.encode())
```

**Gap Analysis**:
- ✅ Has: API key hashing, verification
- ❌ Missing: JWT session tokens for web UI
- ❌ Missing: Password hashing for user accounts
- ❌ Missing: Email verification workflow
- ❌ Missing: Refresh token rotation

**Action Required**: Extend `security.py` to support JWT-based session management for web UI

---

### ✅ EXISTING: Account Management Endpoints

**File**: `src/api/v1/endpoints/account.py`

**Existing Routes**:
- `POST /v1/account/api-keys` - Create API key
- `GET /v1/account/api-keys` - List API keys for customer
- `DELETE /v1/account/api-keys/{key_id}` - Revoke API key

**Features**:
- Secure random key generation (48 characters, alphanumeric)
- Key ID generation (`key_{hex(16)}`)
- Bcrypt hashing before storage

**Gap Analysis**:
- ✅ Has: API key CRUD operations
- ❌ Missing: User signup/login endpoints
- ❌ Missing: Organization creation
- ❌ Missing: User invitation workflow
- ❌ Missing: Usage analytics endpoints

**Action Required**: Add authentication routes (`/v1/auth/*`) and organization routes (`/v1/organizations/*`)

---

### ✅ EXISTING: Customer Profile Model

**File**: `src/complira_graph/models.py` (line 624-680)

**Schema**:
```python
class CustomerProfile(BaseDocument):
    _key: str                        # Customer ID
    name: str                        # Customer name
    email: str                       # Contact email
    api_key_hash: str                # Bcrypt hash of API key
    database_name: str               # Customer database name
    tier: str                        # free, professional, enterprise
    rate_limit: int                  # Requests per day
    created_at: datetime
    updated_at: datetime
```

**Gap Analysis for Phase 5**:
- ✅ Suitable for: Organization-level data
- ❌ Missing fields: `domain`, `industry`, `frameworks` (target compliance frameworks)
- ❌ Missing: Individual user accounts (admin vs member)
- ❌ Missing: Multiple API tokens per customer

**Action Required**:
1. Extend `CustomerProfile` model with missing fields OR
2. Create separate `Organization` and `User` models (cleaner separation)

**Recommendation**: Create new models (`Organization`, `User`, `APIToken`) to avoid breaking existing `CustomerProfile` usage

---

### ✅ EXISTING: Scan Ingestion Pipeline

**File**: `src/api/v1/endpoints/scan.py`

**Route**: `POST /v1/scan/ingest`

**Functionality**:
- Accepts CycloneDX, SPDX, SARIF files
- Parses SBOM/SARIF format
- Creates scan session
- Runs enrichment pipeline (CVE → CWE → ATT&CK → NIST → Regulatory)
- Stores results in customer database

**Performance** (from Phase 1 testing):
- Response time: ~13ms (p95)
- Throughput: 75 req/sec
- 200-component SBOM: ~2-5 seconds

**Gap Analysis**:
- ✅ Has: Full enrichment pipeline
- ❌ Missing: Real-time progress updates (blocking API call)
- ❌ Missing: WebSocket support for async updates
- ❌ Missing: Scan listing/deletion endpoints
- ❌ Missing: Dashboard data aggregation endpoint

**Action Required**:
1. Add WebSocket endpoint `/ws/scans/{session_id}` for real-time progress
2. Add `/v1/scans/{session_id}/analysis` for dashboard data
3. Add `/v1/scans` for listing scans
4. Add `DELETE /v1/scans/{session_id}` for deletion

---

## Technology Stack Validation

### Backend: FastAPI ✅ CONFIRMED

**Version**: Not specified in `requirements-api.txt` (needs verification)

**Dependencies** (from `requirements-api.txt`):
```
fastapi
uvicorn
pydantic
python-arango
bcrypt
structlog
python-multipart
```

**Assessment**: ✅ Mature, production-ready FastAPI setup

**Recommendations**:
- Add `python-jose` for JWT handling
- Add `passlib` for password hashing (email auth)
- Add `email-validator` for email validation
- Add `websockets` for real-time updates

---

### Frontend: Next.js 14 (Proposed)

**Status**: Not yet created

**Justification for Next.js**:
1. **Server-Side Rendering**: SEO-friendly (marketing pages)
2. **App Router**: Modern file-based routing
3. **API Routes**: BFF pattern for sensitive operations
4. **TypeScript**: Type safety across stack
5. **Vercel Deployment**: Simple hosting (or AWS Amplify)

**Alternative Considered**: Vite + React SPA
- ❌ Rejected: No SSR, worse SEO, more complex auth flow

**Action Required**: Initialize Next.js 14 project in `frontend/` directory

---

### UI Library: shadcn/ui (Proposed)

**Justification**:
1. **Accessibility**: Built on Radix UI primitives (WCAG 2.1 AA)
2. **Customizable**: Tailwind-based, full control over styling
3. **Composable**: Copy-paste components, no NPM bloat
4. **Modern**: Matches enterprise SaaS aesthetic
5. **Documentation**: Excellent component examples

**Components Needed** (35 components):
- `Button`, `Input`, `Label`, `Select`, `Checkbox`, `RadioGroup`
- `Dialog`, `Sheet`, `Popover`, `Dropdown`, `Tooltip`
- `Table`, `Card`, `Tabs`, `Accordion`, `Alert`
- `Badge`, `Progress`, `Skeleton`, `Toast`
- `Form` (react-hook-form integration)
- `Command` (search/filter)
- `Calendar`, `DatePicker`

**Action Required**: Install shadcn/ui CLI and add components as needed

---

### State Management: TanStack Query + Zustand (Proposed)

**Server State**: TanStack Query (React Query v5)
- ✅ Handles API calls, caching, invalidation
- ✅ Automatic retry, stale-while-revalidate
- ✅ Optimistic updates for mutations

**Client State**: Zustand
- ✅ Simple, minimal API
- ✅ No Redux boilerplate
- ✅ TypeScript-first

**Assessment**: ✅ Industry standard for modern React applications

---

### Authentication: NextAuth.js v5 (Proposed)

**Justification**:
1. **Session Management**: Automatic JWT handling
2. **OAuth Support**: GitHub, Google, Azure AD (Phase 6)
3. **CSRF Protection**: Built-in
4. **Edge Compatible**: Works with Next.js middleware

**Flow**:
```
User submits email/password → NextAuth validates against ArangoDB
→ Issues JWT (httpOnly cookie) → Client includes cookie in requests
→ Backend validates JWT → Identifies user/org → Routes to customer DB
```

**Alternative Considered**: Manual JWT implementation
- ❌ Rejected: Reinventing the wheel, more security surface area

**Action Required**: Install `next-auth@beta` (v5) and configure providers

---

### WebSocket: Native WebSocket API (Proposed)

**Justification**:
- ✅ Native browser support (no Socket.IO overhead)
- ✅ FastAPI has native WebSocket support (`@app.websocket`)
- ✅ Automatic reconnection easy to implement

**Flow**:
```
Frontend uploads SBOM → Backend creates scan session → Returns session_id
→ Frontend establishes WebSocket: ws://api/ws/scans/{session_id}
→ Backend sends progress events: {"percentage": 30, "stage": "cwe_mapping"}
→ Frontend updates progress bar in real-time
→ Completion event → Frontend fetches full results
```

**Fallback**: Server-Sent Events (SSE) if WebSocket blocked by proxy

**Action Required**: Implement WebSocket endpoint in FastAPI

---

## Integration Points

### 1. Enrichment Pipeline → Dashboard

**Current Flow**:
```
POST /v1/scan/ingest → Enrichment service → Returns enriched JSON
```

**Required Flow for Dashboard**:
```
POST /v1/scan/ingest → Create scan session → Start async enrichment
→ WebSocket sends progress events → Enrichment complete
→ GET /v1/scans/{session_id}/analysis → Returns dashboard data:
   - Executive summary (risk score, severity breakdown)
   - Vulnerability breakdown (by severity)
   - Compliance violations (by framework)
   - Component inventory
   - Remediation recommendations
```

**Gap**: Need to aggregate enrichment results into dashboard-friendly format

**Implementation**:
- Create `DashboardService` in `src/api/services/dashboard.py`
- Query scan results + enrichment edges
- Calculate risk scores (CVSS + EPSS + KEV weighted)
- Group by severity, framework
- Return structured JSON

---

### 2. Authentication → Customer Database Routing

**Current Flow**:
```
Request includes X-API-Key → Lookup customer_profiles → Get database_name
→ Connect to customer database → Execute query
```

**Required Flow for Web UI**:
```
User logs in → NextAuth issues JWT (contains user_id, org_id)
→ Frontend includes JWT in Authorization header
→ Backend validates JWT → Extracts org_id → Looks up database_name
→ Connects to customer database → Executes query
```

**Gap**: JWT validation logic needs to be added to `get_current_customer` dependency

**Implementation**:
- Extend `api/core/security.py` with `verify_jwt_token()` function
- Modify `get_current_customer()` to check both X-API-Key AND Authorization header
- Precedence: JWT over API key (web UI sessions)

---

### 3. Export Endpoints → PDF/Excel Generation

**Current State**:
- VEX endpoint exists (`POST /v1/vex/generate`) - returns CSAF JSON

**Required**:
- `/v1/scans/{session_id}/export/vex` → CSAF VEX document
- `/v1/scans/{session_id}/export/pdf` → PDF compliance report
- `/v1/scans/{session_id}/export/csv` → CSV vulnerability list

**Implementation**:
- **PDF**: Use ReportLab or WeasyPrint (Python) OR jsPDF (frontend)
  - Recommendation: Backend (Python) for server-side generation, no client dependencies
- **CSV**: Standard Python `csv` module
- **CSAF**: Existing VEX service can be reused

**Action Required**: Create `ExportService` in `src/api/services/export.py`

---

## Scope Triage

### Phase 5 MVP (In Scope)

**Module 1: Authentication (3 weeks)**
- User signup with email/password
- Email verification (SendGrid/SES)
- Login with JWT session
- Password reset via email
- Organization creation during signup

**Module 2: API Token Management (1 week)**
- Extend existing account endpoints for web UI
- Token listing with metadata (last used, request count)
- Token rotation (deprecate old, issue new)
- Usage analytics dashboard

**Module 3: SBOM Upload & Real-Time Processing (2 weeks)**
- File upload UI (react-dropzone)
- WebSocket integration for progress
- Async enrichment with progress events
- Error handling and retry logic

**Module 4: Analysis Dashboard (2 weeks)**
- Executive summary component
- Vulnerability breakdown charts (Recharts)
- Compliance violations table
- Component inventory with sorting/filtering (TanStack Table)
- Remediation recommendations

**Module 5: Export & Reporting (1 week)**
- VEX document generation
- PDF compliance report
- CSV export

**Module 6: Scans Management (1 week)**
- List all scans for organization
- Filter by date, severity, type
- Delete scans

**Total Estimated Effort**: 10 weeks (1 developer) or 6 weeks (2 developers)

---

### Deferred to Phase 6 (Out of Scope)

**Why Deferred**: High complexity, low MVP value

1. **SSO/SAML Integration**
   - Enterprise feature, requires complex SAML flow
   - NextAuth supports it, but needs extensive testing

2. **Multi-Factor Authentication (MFA)**
   - TOTP implementation (Google Authenticator)
   - SMS verification (Twilio integration)
   - Backup codes

3. **Advanced RBAC**
   - Custom roles beyond Admin/Member/Viewer
   - Permission matrix (read/write/delete per resource)

4. **Scheduled Scanning**
   - Cron-based SBOM re-scanning
   - Email notifications on new vulnerabilities

5. **CI/CD Integration**
   - GitHub Actions plugin
   - GitLab CI integration
   - Jenkins plugin

6. **Advanced Analytics**
   - Trend analysis (vulnerability count over time)
   - Benchmarking against industry peers
   - Risk scoring evolution

---

## Risk Assessment

### Risk 1: WebSocket Scalability at 1,000+ Concurrent Users

**Likelihood**: Medium
**Impact**: High (poor UX, timeout errors)

**Mitigation**:
- Use Redis pub/sub for WebSocket message distribution
- Horizontal scaling with sticky sessions (ALB)
- Fallback to Server-Sent Events (SSE) if WebSocket fails
- Implement connection pooling

**Validation**: Load test with 1,000 simulated WebSocket connections (k6 or Artillery)

---

### Risk 2: Large SBOM Files (> 1,000 Components) Cause Timeout

**Likelihood**: High (enterprise software often has 1,000+ dependencies)
**Impact**: High (enrichment fails, no results shown)

**Current Behavior**: `/v1/scan/ingest` is synchronous, may timeout at 30 seconds

**Mitigation**:
- Make enrichment fully asynchronous (Celery task queue)
- Email notification on completion (for very large SBOMs)
- Batch enrichment: Process 100 components at a time, emit progress
- Set realistic timeout: 5 minutes for 1,000 components

**Validation**: Test with 2,000-component SBOM (Kubernetes, Chromium-scale projects)

---

### Risk 3: CycloneDX/SPDX Schema Changes Break Parser

**Likelihood**: Medium (SPDX 3.0 released Q1 2024, CycloneDX 1.5 coming)
**Impact**: Medium (new uploads fail, user frustration)

**Mitigation**:
- Versioned parsers (`CycloneDXParser_v1_4`, `CycloneDXParser_v1_5`)
- Schema validation with clear error messages
- Fallback to generic parser if version unsupported
- Monitor SPDX/CycloneDX GitHub repos for spec updates

**Validation**: Maintain test fixtures for all supported versions

---

### Risk 4: JWT Token Leakage via XSS Attack

**Likelihood**: Low (if CSP headers configured correctly)
**Impact**: Critical (account takeover)

**Mitigation**:
- Store JWT in httpOnly cookies (not localStorage)
- Set strict CSP headers (`Content-Security-Policy`)
- Enable CSRF protection (NextAuth has this built-in)
- Short-lived access tokens (15 minutes), long-lived refresh tokens (7 days)
- Token rotation on every refresh

**Validation**: OWASP ZAP scan, manual XSS testing

---

### Risk 5: Database Schema Migration Breaks Existing API Clients

**Likelihood**: Low (careful migration planning)
**Impact**: High (production API downtime)

**Mitigation**:
- **DO NOT** modify existing `customer_profiles` collection
- Create NEW collections: `organizations`, `users`, `api_tokens`
- Dual-read: Check both `customer_profiles.api_key_hash` AND `api_tokens` collection
- Gradual migration: Write to both places, read from new schema
- Keep backward compatibility for 6 months

**Validation**: Integration tests against both old and new schemas

---

## Open Questions (Require User Input)

### Q1: SPDX 3.0 Support

**Context**: SPDX 3.0 released Q1 2024 with major schema changes

**Question**: Should Phase 5 support SPDX 3.0, or only SPDX 2.3?

**Options**:
1. **Phase 5**: SPDX 2.3 only (lower risk, faster delivery)
2. **Phase 5**: Both 2.3 and 3.0 (future-proof, +2 weeks effort)

**Recommendation**: SPDX 2.3 only for Phase 5, add 3.0 in Phase 6 once spec stabilizes

---

### Q2: API Token Expiry Policy

**Context**: Current `customer_profiles` model doesn't have token expiry

**Question**: Should API tokens expire, or allow indefinite validity?

**Options**:
1. **Indefinite**: Tokens valid until manually revoked
   - ✅ Simpler UX, no automated rotation needed
   - ❌ Security risk if token leaked
2. **90-day expiry**: Automatic expiry with email reminder at 80 days
   - ✅ Better security hygiene
   - ❌ More complex implementation, user friction

**Recommendation**: 90-day expiry with rotation reminders (industry standard)

---

### Q3: Scan Results Visibility

**Context**: Multi-user organizations

**Question**: Should scan results be shared across all organization users, or private to uploader?

**Options**:
1. **Shared**: All users see all scans (simpler model)
2. **Private**: Users only see their own scans (more complex RBAC)

**Recommendation**: Shared (Phase 5), add privacy controls in Phase 6

---

### Q4: SBOM File Retention

**Context**: Storage costs, compliance requirements

**Question**: How long should uploaded SBOM files be retained?

**Options**:
1. **30 days**: Aggressive cleanup (lower costs)
2. **90 days**: Moderate retention (balance cost + usability)
3. **Indefinite**: Never delete (highest cost, audit trail)

**Recommendation**: 90 days with option to archive (S3 Glacier) for compliance

---

### Q5: Email Notification Strategy

**Context**: Async scan completion

**Question**: Should users receive email notifications on scan completion, or WebSocket-only?

**Options**:
1. **WebSocket only**: Real-time browser notification (modern UX)
   - ❌ Fails if user closes browser
2. **Email + WebSocket**: Belt-and-suspenders approach
   - ✅ Guaranteed delivery
   - ❌ Email fatigue, more infrastructure (SendGrid cost)

**Recommendation**: Email notification for scans > 500 components (expected >30 sec completion)

---

## Technical Debt Assessment

### Existing Debt in Backend

1. **No API versioning in URLs**
   - Current: `/v1/scan/ingest` ✅ Good
   - Future: Maintain `/v1` as stable, add `/v2` for breaking changes

2. **API Key stored in `customer_profiles` (single token per customer)**
   - Problem: Can't revoke without breaking all API access
   - Solution: Migrate to `api_tokens` collection (many-to-one with customer)

3. **No rate limiting infrastructure**
   - Current: `rate_limit` field exists but not enforced
   - Solution: Add Redis-based rate limiter (FastAPI-limiter)

4. **No structured logging correlation IDs**
   - Problem: Hard to trace requests across services
   - Solution: Add `X-Request-ID` header, propagate through logs

5. **CORS allows all origins**
   - Current: `allow_origins=["*"]` (development mode)
   - Solution: Restrict to production domains in env config

**Impact on Phase 5**: Low (can work around), but should be addressed in Phase 6

---

## Recommendations

### Architecture Decisions

**Decision 1**: Create Separate Collections for Organizations, Users, API Tokens
- ✅ Cleaner separation of concerns
- ✅ Easier RBAC implementation
- ✅ Supports multi-user organizations
- ❌ Requires schema migration planning

**Recommendation**: ✅ **Proceed with new collections**

---

**Decision 2**: Use NextAuth.js v5 for Authentication
- ✅ Industry-proven solution
- ✅ Built-in CSRF, session management
- ✅ Extensible for OAuth (Phase 6)
- ❌ Adds dependency on Next.js

**Recommendation**: ✅ **Proceed with NextAuth.js v5**

---

**Decision 3**: WebSocket vs Server-Sent Events for Real-Time Updates
- WebSocket:
  - ✅ Bidirectional (can cancel scans)
  - ✅ Lower latency
  - ❌ More complex server infrastructure
- SSE:
  - ✅ Simpler (HTTP-based)
  - ✅ Auto-reconnect built-in
  - ❌ Unidirectional only

**Recommendation**: ✅ **WebSocket with SSE fallback**

---

**Decision 4**: Backend PDF Generation vs Frontend jsPDF
- Backend (Python):
  - ✅ More powerful (ReportLab)
  - ✅ No client-side dependencies
  - ✅ Consistent formatting
- Frontend (jsPDF):
  - ✅ Faster (no API call)
  - ❌ Limited styling
  - ❌ Large bundle size

**Recommendation**: ✅ **Backend PDF generation** (ReportLab)

---

### Implementation Priorities

**Priority 1** (Critical Path): Frontend Bootstrap
1. Initialize Next.js 14 project (`npx create-next-app@latest`)
2. Install shadcn/ui CLI
3. Set up TanStack Query + Zustand
4. Create basic layout (header, sidebar, main content)

**Priority 2** (Blocker for Testing): Authentication System
1. Extend backend with `/v1/auth/*` endpoints
2. Create `users` and `organizations` collections
3. Implement NextAuth.js configuration
4. Build login/signup UI

**Priority 3** (Core Feature): SBOM Upload + Real-Time Progress
1. Implement WebSocket endpoint in FastAPI
2. Make enrichment pipeline async
3. Build file upload UI
4. Integrate WebSocket on frontend

**Priority 4** (User Value): Analysis Dashboard
1. Create dashboard data aggregation service
2. Build dashboard UI components
3. Integrate with scan results API

**Priority 5** (Polish): Export & Reporting
1. Implement PDF/CSV export service
2. Build export UI buttons

---

## Next Steps (Stage 1 → Stage 2 Transition)

### Artifacts to Create:

1. **requirements.md** (Refined) ✅ DONE
   - User stories validated
   - Acceptance criteria refined with codebase insights

2. **proposed-design.md** (Stage 3)
   - Database schema migrations
   - API endpoint specifications
   - Frontend component tree
   - Authentication flow diagrams

3. **implementation-plan.md** (Stage 3)
   - Sprint breakdown (6 sprints × 2 weeks)
   - Task dependencies
   - Risk mitigation tasks

### Questions to Resolve Before Stage 3:

- Q1: SPDX 3.0 support? (Recommendation: No for Phase 5)
- Q2: API token expiry policy? (Recommendation: 90 days)
- Q3: Scan visibility? (Recommendation: Shared)
- Q4: SBOM retention? (Recommendation: 90 days)
- Q5: Email notifications? (Recommendation: For scans > 500 components)

**Status**: Investigation complete. Ready to refine requirements (Stage 2).

---

## References

- **Existing Codebase**: `src/api/*`, `src/complira_graph/*`
- **Phase 5 Planning Docs**: `docs/PHASE5_WEB_UI_PLAN.md`, `docs/PHASE5_SBOM_UPLOAD_UI.md`
- **Workflow State**: `tickets/in-progress/phase-5-web-ui/workflow-state.md`
- **Requirements**: `tickets/in-progress/phase-5-web-ui/requirements.md`
