# Requirements Document

**Ticket**: phase-5-web-ui
**Status**: `Design-ready`
**Last Updated**: 2026-03-16
**Owner**: Engineering Team

---

## Document Status

- [x] Draft
- [x] Design-ready (current - refined based on codebase investigation)
- [ ] Refined

---

## Overview

Build a comprehensive web-based user interface for the Complira cybersecurity compliance platform that enables organizations to:
1. Self-service onboard and manage API tokens
2. Upload and analyze SBOM/SARIF files
3. View vulnerability analysis and compliance insights
4. Generate compliance reports and VEX documents

This is the "front door" for customers to interact with Complira, transforming it from an API-only service into a self-service platform.

---

## Business Context

### Problem Statement

Currently, Complira only exposes a FastAPI backend with no user interface. Organizations must:
- Contact sales to get API tokens (slow onboarding)
- Use curl/Postman to interact with APIs (high friction)
- Parse JSON responses manually (poor UX for compliance teams)
- Cannot visualize vulnerability chains or compliance violations

### Business Goals

1. **Reduce time-to-first-API-call**: From days to < 5 minutes (self-service signup)
2. **Enable non-technical users**: Compliance officers, product managers, auditors
3. **Increase conversion**: Free trial → paid conversion through better UX
4. **Reduce support burden**: Self-service token management and usage analytics

### Success Metrics

- Time-to-first-API-call < 5 minutes
- Token rotation compliance > 90%
- Self-service onboarding (zero support tickets)
- Upload-to-insights time < 30 seconds for typical SBOM (200 components)

---

## Scope

### In Scope

#### Module 1: Authentication & Organization Management
- User signup/login (email + password, OAuth optional for Phase 6)
- Email verification workflow
- Organization creation and settings
- User roles (Admin, Member, Viewer)
- Session management with JWT

#### Module 2: API Token Management
- Token creation with scoping (read-only, read-write)
- Token listing and metadata
- Token rotation and revocation
- Usage analytics per token
- Rate limit monitoring

#### Module 3: SBOM/SARIF Upload & Processing
- Drag-and-drop file upload (CycloneDX, SPDX, SARIF)
- Paste JSON directly option
- Real-time enrichment progress via WebSocket
- Scan session management
- File validation and error handling

#### Module 4: Analysis Dashboard
- Executive summary (risk score, severity breakdown)
- Vulnerability breakdown charts
- Compliance status by framework (FDA, CRA, IEC, NIST)
- Component inventory table
- Vulnerability detail expansion (CVE → CWE → ATT&CK chains)
- Remediation recommendations

#### Module 5: Export & Reporting
- VEX document generation (CSAF format)
- PDF compliance report
- Excel/CSV export for vulnerability data
- Share scan results via link

#### Module 6: Scans Dashboard
- List all uploaded scans for organization
- Filter by type, date, severity
- Search by scan name or component
- Delete scans

### Out of Scope (Future Phases)

- SSO/SAML integration → Phase 6
- Multi-factor authentication (MFA) → Phase 6
- Advanced RBAC (custom roles) → Phase 6
- Scheduled scanning → Phase 6
- CI/CD pipeline integration → Phase 6
- Advanced analytics (trends, benchmarking) → Phase 7
- White-label customization → Phase 7

---

## User Stories

### US-1: User Signup and Organization Creation
**As a** compliance officer at a medical device company
**I want to** sign up for Complira and create an organization account
**So that** I can start analyzing our SBOMs for FDA compliance

**Acceptance Criteria**:
- AC1.1: User can register with email and password
- AC1.2: Email verification link sent and validated
- AC1.3: User creates organization with name, domain, industry
- AC1.4: User selects target frameworks (FDA, CRA, IEC, NIST)
- AC1.5: Free tier auto-assigned with rate limits (100 req/day)

### US-2: API Token Generation
**As an** authenticated admin user
**I want to** create API tokens with specific scopes
**So that** I can integrate Complira with our CI/CD pipeline

**Acceptance Criteria**:
- AC2.1: Admin can create token with name and scope (read-only, read-write)
  - **Implementation Note**: Reuse existing `POST /v1/account/api-keys` endpoint
  - **Validation**: Token name unique within organization, 3-50 characters
- AC2.2: Token displayed once (cannot retrieve again)
  - **Implementation Note**: Return plaintext token in response, store bcrypt hash in DB
  - **UI**: Show copy-to-clipboard button, modal warning "Save this now, you won't see it again"
- AC2.3: Token metadata shows creation date, last used, request count
  - **Implementation Note**: Extend existing `APIKeyResponse` model with `last_used_at`, `request_count`
  - **Query**: Update `last_used_at` on every API call (async update to avoid latency)
- AC2.4: Admin can revoke token immediately
  - **Implementation Note**: Reuse existing `DELETE /v1/account/api-keys/{key_id}` endpoint
  - **Validation**: Only org admins can revoke (RBAC check)
- AC2.5: Admin can rotate token (generates new, marks old as deprecated)
  - **Implementation Note**: NEW endpoint `POST /v1/account/api-keys/{key_id}/rotate`
  - **Behavior**: Old token valid for 30 days (grace period), new token returned immediately
  - **Database**: Set `deprecated_at` timestamp on old token, create new token record

### US-3: SBOM Upload and Analysis
**As a** product manager
**I want to** upload a CycloneDX SBOM file
**So that** I can see which vulnerabilities affect our product

**Acceptance Criteria**:
- AC3.1: User can drag-and-drop SBOM file (JSON/XML, max 10MB)
  - **Frontend**: Use `react-dropzone` library
  - **Supported Formats**: CycloneDX 1.4/1.5 (JSON/XML), SPDX 2.3 (JSON), SARIF 2.1 (JSON)
  - **Validation**: Check `Content-Type`, file extension, magic bytes
  - **Error Handling**: Show user-friendly error if unsupported format
- AC3.2: File validated (schema, format) before upload
  - **Backend**: Reuse existing parsers in `src/api/parsers/{cyclonedx,sarif}.py`
  - **Validation**: JSON schema validation using `jsonschema` library
  - **Error Response**: Return 400 with specific error (e.g., "Missing required field 'components'")
- AC3.3: Real-time progress bar shows enrichment stages
  - **WebSocket Events**:
    - `{"event": "started", "data": {"session_id": "..."}}`
    - `{"event": "progress", "data": {"percentage": 30, "stage": "cwe_mapping", "message": "Mapping CWE weaknesses..."}}`
    - `{"event": "complete", "data": {"session_id": "..."}}`
    - `{"event": "error", "data": {"message": "..."}}`
  - **UI**: Animated progress bar with stage labels below
- AC3.4: Analysis completes in < 30 seconds for 200-component SBOM
  - **Performance Baseline**: Existing `/v1/scan/ingest` averages ~2-5 seconds (Phase 1 testing)
  - **Target**: Maintain < 30s even with async WebSocket overhead
  - **Validation**: Load test with 200-component SBOM (measure p95 latency)
- AC3.5: Dashboard displays results with severity breakdown
  - **Implementation**: Fetch `GET /v1/scans/{session_id}/analysis` on completion
  - **Data Format**: See FR-6 (Analysis Dashboard) for response schema

### US-4: Vulnerability Analysis Dashboard
**As a** security engineer
**I want to** view detailed vulnerability analysis for uploaded SBOM
**So that** I can prioritize remediation efforts

**Acceptance Criteria**:
- AC4.1: Executive summary shows risk score, total findings, framework violations
- AC4.2: Charts display severity distribution (Critical/High/Medium/Low)
- AC4.3: Component inventory table sortable by risk score
- AC4.4: Expanding CVE row shows CWE → ATT&CK → NIST chain
- AC4.5: Remediation recommendations prioritized by EPSS + KEV

### US-5: Compliance Report Export
**As a** compliance officer preparing for FDA audit
**I want to** generate a PDF report of our SBOM analysis
**So that** I can include it in our 524B submission

**Acceptance Criteria**:
- AC5.1: User can export VEX document (CSAF format)
- AC5.2: User can generate PDF report with compliance summary
- AC5.3: User can download CSV of all vulnerabilities
- AC5.4: Report includes Complira branding and timestamp
- AC5.5: Export completes in < 10 seconds

### US-6: Token Usage Analytics
**As an** admin monitoring API consumption
**I want to** view token usage over time
**So that** I can optimize rate limits and detect anomalies

**Acceptance Criteria**:
- AC6.1: Dashboard shows request count per token (7-day, 30-day)
- AC6.2: Chart displays daily usage trends
- AC6.3: Alert shown when approaching rate limit (80%)
- AC6.4: Error rate displayed (4xx, 5xx responses)
- AC6.5: Last used timestamp shown for each token

---

## Functional Requirements

### FR-1: Authentication System
- **FR-1.1**: Support email/password authentication with bcrypt hashing
- **FR-1.2**: JWT-based session management (15-min access token, 7-day refresh token)
- **FR-1.3**: Email verification required before accessing dashboard
- **FR-1.4**: Password reset via email link
- **FR-1.5**: Session revocation on password change

### FR-2: Organization Management
- **FR-2.1**: Organization has name, domain, industry, tier (free/pro/enterprise)
- **FR-2.2**: Organization can configure target frameworks
- **FR-2.3**: Organization settings include rate limits, data retention
- **FR-2.4**: Users belong to single organization
- **FR-2.5**: Admins can invite members via email

### FR-3: API Token Lifecycle
- **FR-3.1**: Tokens have name, scope, creation date, expiry (90 days)
  - **Schema**: `{_key, organization_id, created_by_user_id, name, token_hash, scope, created_at, expires_at, last_used_at, request_count, deprecated_at, revoked_at}`
  - **Default Expiry**: 90 days from creation (configurable per org tier)
- **FR-3.2**: Token hashed with bcrypt, raw value shown once
  - **Implementation**: Reuse existing `hash_api_key()` function in `src/api/core/security.py`
  - **Cost Factor**: 12 rounds (OWASP recommendation)
- **FR-3.3**: Token rotation creates new token, deprecates old (30-day grace)
  - **Flow**: `POST /v1/account/api-keys/{key_id}/rotate` → Generate new token → Set `deprecated_at` on old → Return new plaintext token
  - **Grace Period**: Old token valid for 30 days, then auto-revoked
- **FR-3.4**: Token revocation immediate (blacklist check on every request)
  - **Implementation**: Check `revoked_at IS NULL AND (deprecated_at IS NULL OR deprecated_at > NOW() - 30 days)` in `verify_api_key()`
  - **Performance**: Add index on `token_hash` for fast lookup
- **FR-3.5**: Tokens scoped to organization (cannot access other org data)
  - **Enforcement**: `get_current_customer()` dependency extracts `organization_id` from token, all queries filtered by org
  - **Validation**: Integration test attempts cross-org access, expects 403

### FR-4: File Upload Processing
- **FR-4.1**: Accept CycloneDX 1.4+, SPDX 2.3+, SARIF 2.1+ formats
- **FR-4.2**: Validate schema before processing (reject invalid files)
- **FR-4.3**: Create scan session with unique ID
- **FR-4.4**: Stream enrichment progress via WebSocket
- **FR-4.5**: Store raw file + processed results in database

### FR-5: Real-Time Enrichment
- **FR-5.1**: WebSocket connection established on upload
- **FR-5.2**: Progress events: parsing (10%), CVE mapping (30%), CWE mapping (50%), ATT&CK mapping (70%), regulatory mapping (90%), complete (100%)
- **FR-5.3**: Error events sent if enrichment fails
- **FR-5.4**: Connection auto-reconnects on disconnect
- **FR-5.5**: Fallback to polling if WebSocket unavailable

### FR-6: Analysis Dashboard
- **FR-6.1**: Calculate risk score (weighted by CVSS + EPSS + KEV)
- **FR-6.2**: Group vulnerabilities by severity
- **FR-6.3**: Identify framework violations (e.g., FDA requires SBOM patching in 30 days)
- **FR-6.4**: Display attack chains (CVE → CWE → ATT&CK → NIST)
- **FR-6.5**: Prioritize remediation by exploitability + impact

### FR-7: Export Formats
- **FR-7.1**: VEX document follows CSAF 2.0 schema
- **FR-7.2**: PDF report includes executive summary, vulnerability table, compliance status
- **FR-7.3**: CSV export has columns: CVE, Component, Severity, EPSS, KEV, Frameworks
- **FR-7.4**: Exports watermarked with organization name and timestamp
- **FR-7.5**: Export files named: `complira-{scan-name}-{date}.{ext}`

---

## Non-Functional Requirements

### NFR-1: Performance
- **NFR-1.1**: Dashboard loads in < 2 seconds (Time to Interactive)
  - **Measurement**: Lighthouse performance score > 90
  - **Optimization**: Code splitting, lazy load non-critical components
  - **Validation**: Test on throttled network (3G)
- **NFR-1.2**: File upload accepts 10MB files in < 5 seconds
  - **Target**: 10MB upload @ 16 Mbps (AWS ALB typical)
  - **Implementation**: Multipart upload with progress callback
  - **Validation**: Upload 10MB SBOM, measure time to 200 OK response
- **NFR-1.3**: Enrichment completes in < 30 seconds for 200-component SBOM
  - **Baseline**: Existing pipeline ~2-5 seconds (Phase 1)
  - **Buffer**: 6x headroom for WebSocket overhead
  - **Fallback**: If > 500 components, send email notification instead of blocking
- **NFR-1.4**: API response time < 500ms for p95
  - **Current**: ~13ms average (Phase 1 testing)
  - **Target**: Maintain < 500ms even with JWT validation overhead
  - **Monitoring**: CloudWatch metrics, alert if p95 > 500ms
- **NFR-1.5**: WebSocket latency < 100ms (message sent → client receives)
  - **Infrastructure**: AWS ALB supports WebSocket with sticky sessions
  - **Measurement**: Ping-pong test between client and server
  - **Validation**: Load test with 1,000 concurrent WebSocket connections

### NFR-2: Security
- **NFR-2.1**: All passwords hashed with bcrypt (cost 12)
- **NFR-2.2**: API tokens hashed, raw value never stored
- **NFR-2.3**: HTTPS required for all endpoints
- **NFR-2.4**: CSRF protection on state-changing requests
- **NFR-2.5**: Rate limiting per organization (100 req/day free, 10K pro)
- **NFR-2.6**: Input validation on all user inputs
- **NFR-2.7**: XSS protection via CSP headers

### NFR-3: Scalability
- **NFR-3.1**: Support 1,000 concurrent WebSocket connections
- **NFR-3.2**: Database handles 100K scans without degradation
- **NFR-3.3**: Horizontal scaling for API servers
- **NFR-3.4**: File storage uses S3 (not local filesystem)

### NFR-4: Reliability
- **NFR-4.1**: 99.9% uptime SLA
- **NFR-4.2**: Graceful degradation if enrichment service down
- **NFR-4.3**: Data backup daily with 30-day retention
- **NFR-4.4**: Transaction rollback on partial failures

### NFR-5: Usability
- **NFR-5.1**: Mobile-responsive design (works on tablets)
- **NFR-5.2**: WCAG 2.1 AA accessibility compliance
- **NFR-5.3**: Tooltips explain technical terms (EPSS, KEV, CWE)
- **NFR-5.4**: Error messages actionable (e.g., "Invalid CycloneDX schema: missing 'components' field")

### NFR-6: Observability
- **NFR-6.1**: Structured logging (JSON format)
- **NFR-6.2**: Metrics: request rate, error rate, latency percentiles
- **NFR-6.3**: Distributed tracing for enrichment pipeline
- **NFR-6.4**: Alerts: error rate > 5%, latency p95 > 2s

---

## Technical Architecture

### Frontend Stack
- **Framework**: Next.js 14 (App Router)
- **UI Library**: shadcn/ui (Radix UI + Tailwind CSS)
- **State**: TanStack Query (server state), Zustand (client state)
- **Auth**: NextAuth.js v5
- **Forms**: react-hook-form + zod validation
- **Charts**: Recharts
- **Tables**: TanStack Table
- **Upload**: react-dropzone
- **WebSocket**: native WebSocket API

### Backend Extensions (FastAPI)

**Phase 5A: Authentication & User Management**
- `POST /v1/auth/signup` - User signup (email + password)
- `POST /v1/auth/login` - User login (returns JWT)
- `POST /v1/auth/verify-email` - Email verification via token
- `POST /v1/auth/refresh` - Refresh JWT access token
- `POST /v1/auth/logout` - Invalidate session
- `POST /v1/auth/forgot-password` - Send password reset email
- `POST /v1/auth/reset-password` - Reset password via token

**Phase 5B: Organization Management**
- `POST /v1/organizations` - Create organization (during signup)
- `GET /v1/organizations/{org_id}` - Get organization details
- `PATCH /v1/organizations/{org_id}` - Update org settings
- `POST /v1/organizations/{org_id}/members` - Invite member
- `DELETE /v1/organizations/{org_id}/members/{user_id}` - Remove member
- `GET /v1/organizations/{org_id}/members` - List members

**Phase 5C: API Token Management** (extends existing `/v1/account/api-keys`)
- ✅ `POST /v1/account/api-keys` - Create token (EXISTING)
- ✅ `GET /v1/account/api-keys` - List tokens (EXISTING)
- ✅ `DELETE /v1/account/api-keys/{key_id}` - Revoke token (EXISTING)
- 🆕 `POST /v1/account/api-keys/{key_id}/rotate` - Rotate token
- 🆕 `GET /v1/account/api-keys/{key_id}/usage` - Get usage stats

**Phase 5D: Scan Management** (extends existing `/v1/scan/ingest`)
- ✅ `POST /v1/scan/ingest` - Upload SBOM/SARIF (EXISTING, make async)
- 🆕 `GET /v1/scans` - List all scans for organization
- 🆕 `GET /v1/scans/{session_id}` - Get scan details
- 🆕 `GET /v1/scans/{session_id}/analysis` - Get dashboard data
- 🆕 `DELETE /v1/scans/{session_id}` - Delete scan

**Phase 5E: Real-Time Updates**
- 🆕 `WS /ws/scans/{session_id}` - WebSocket for enrichment progress

**Phase 5F: Export**
- 🆕 `GET /v1/scans/{session_id}/export/vex` - CSAF VEX document
- 🆕 `GET /v1/scans/{session_id}/export/pdf` - PDF compliance report
- 🆕 `GET /v1/scans/{session_id}/export/csv` - CSV vulnerability list

**Legend**: ✅ Existing | 🆕 New | 🔄 Modified

### Database Schema (ArangoDB)

**Reference Database** (`complira_reference`):
- ✅ `customer_profiles` - KEEP UNCHANGED (backward compatibility)
- 🆕 `organizations` - New organization records
- 🆕 `users` - User accounts (email/password, JWT sessions)
- 🆕 `api_tokens` - API tokens (replaces inline `api_key_hash` in customer_profiles)
- 🆕 `audit_log` - User actions, login attempts, API calls

**Customer Databases** (`complira_customer_{org_id}`):
- ✅ `scans` - Uploaded SBOM/SARIF files (EXISTING schema)
- ✅ `scan_results` - Enrichment results (EXISTING)
- 🆕 `scan_metadata` - Dashboard aggregations (precomputed for performance)

**New Edge Collections** (reference database):
- 🆕 `user_belongs_to_org` (users → organizations)
- 🆕 `org_owns_token` (organizations → api_tokens)
- 🆕 `user_created_token` (users → api_tokens)
- 🆕 `org_uses_customer_db` (organizations → customer_profiles) - migration bridge

---

## Dependencies

### External Services
- **Email**: ✅ AWS SES (already configured for AWS deployment)
  - **Usage**: Email verification, password reset, scan completion notifications
  - **Rate Limit**: 1,000 emails/day (free tier)
- **Storage**: ✅ AWS S3 (already used for backups)
  - **Bucket**: `complira-sbom-uploads-prod`
  - **Retention**: 90 days active, then Glacier archive
- **Monitoring**: ✅ CloudWatch (already collecting API metrics)
  - **Custom Metrics**: WebSocket connection count, JWT validation latency

### Internal Dependencies (CRITICAL PATH)
- ✅ **Phase 1 Enrichment API**: Operational at `/v1/scan/ingest` (EXISTING)
- ✅ **ArangoDB Schema**: Reference database initialized (EXISTING)
- ✅ **Reference Data Seeded**: NVD, EPSS, KEV, CWE, CAPEC, ATT&CK, D3FEND (RUNNING ON AWS)
- ✅ **API Key Authentication**: Existing `src/api/core/security.py` (REUSABLE)
- ⚠️ **NEW**: JWT library (`python-jose`) - need to add to `requirements-api.txt`
- ⚠️ **NEW**: Password hashing (`passlib[bcrypt]`) - need to add to `requirements-api.txt`
- ⚠️ **NEW**: Email validator (`email-validator`) - need to add to `requirements-api.txt`
- ⚠️ **NEW**: PDF generation (`reportlab`) - need to add to `requirements-api.txt`

### Frontend Dependencies (NEW STACK)
- **Runtime**: Node.js 20 LTS
- **Framework**: Next.js 14.2+
- **UI Components**: shadcn/ui (35 components estimated)
- **State Management**: TanStack Query v5, Zustand
- **Authentication**: NextAuth.js v5
- **Forms**: react-hook-form + zod
- **Charts**: Recharts
- **Tables**: TanStack Table
- **File Upload**: react-dropzone
- **PDF Export**: jsPDF (fallback if backend fails)

---

## Risks and Mitigations

### Risk 1: WebSocket Scalability
**Impact**: High concurrent users may overwhelm WebSocket server
**Mitigation**: Use Redis pub/sub for WebSocket message distribution, horizontal scaling

### Risk 2: Large SBOM Files (> 1000 components)
**Impact**: Enrichment timeout, poor UX
**Mitigation**: Implement batch processing, async job queue (Celery), email notification on completion

### Risk 3: Schema Changes in SBOM Standards
**Impact**: Parser breaks on new CycloneDX/SPDX versions
**Mitigation**: Versioned parsers, schema validation with clear error messages

### Risk 4: Compliance Framework Updates
**Impact**: FDA/CRA requirements change, reports outdated
**Mitigation**: Versioned regulatory data, changelog for framework updates

---

## Open Questions → Resolved

### Q1: SPDX 3.0 Support
**Decision**: ❌ Not in Phase 5. Support SPDX 2.3 only.
**Rationale**: SPDX 3.0 spec still evolving (released Q1 2024). Defer to Phase 6 once ecosystem matures.
**Impact**: Minimal - SPDX 2.3 is industry standard. Add 3.0 when tooling supports it.

### Q2: API Token Expiry Policy
**Decision**: ✅ 90-day expiry with rotation reminders
**Rationale**: Industry best practice (GitHub, AWS). Better security hygiene.
**Implementation**: Email reminder at 80 days, auto-deprecate at 90 days, 30-day grace period.

### Q3: Scan Results Visibility
**Decision**: ✅ Shared across organization
**Rationale**: Simpler RBAC model for Phase 5. Most orgs want team collaboration.
**Future**: Add private scans in Phase 6 if requested.

### Q4: SBOM File Retention
**Decision**: ✅ 90-day active retention, S3 Glacier archive option
**Rationale**: Balance cost vs compliance needs. 90 days covers typical audit cycles.
**Implementation**: Cron job archives files to S3 Glacier after 90 days, retains metadata in DB.

### Q5: Email Notifications
**Decision**: ✅ Email for scans > 500 components (expected >30s completion)
**Rationale**: User may close browser for large scans. Small scans complete before user navigates away.
**Implementation**: Check component count on upload, conditionally send email on completion.

---

## Assumptions

1. ✅ Organizations willing to manually verify email (no SMS verification)
2. ✅ Target users comfortable with JSON file uploads (technical audience)
3. ✅ Browser support: Chrome/Firefox/Safari latest 2 versions (no IE11)
4. ✅ Initial launch: US-only (no GDPR compliance required in Phase 5)
5. ✅ Free tier limits prevent abuse (100 req/day sufficient for trials)
6. ✅ **NEW**: Existing `customer_profiles` model will NOT be modified (backward compatibility)
7. ✅ **NEW**: Frontend will be deployed separately from backend (separate domain/subdomain)
8. ✅ **NEW**: WebSocket connections limited to 1,000 concurrent (AWS ALB limit)

---

## Acceptance Criteria Summary

This feature is considered complete when:

1. ✅ User can sign up, verify email, and create organization (< 5 min)
2. ✅ User can generate API token and make first enrichment request
3. ✅ User can upload CycloneDX SBOM and see real-time progress
4. ✅ Analysis dashboard displays vulnerabilities, compliance violations, remediation plan
5. ✅ User can export VEX, PDF, and CSV reports
6. ✅ All functional requirements (FR-1 through FR-7) implemented
7. ✅ All non-functional requirements (NFR-1 through NFR-6) verified
8. ✅ Unit test coverage > 80%, E2E tests for all user stories
9. ✅ Documentation updated (API docs, user guide, deployment guide)
10. ✅ Security review passed (OWASP Top 10 mitigations verified)

---

## References

- **Phase 5 Web UI Plan**: `docs/PHASE5_WEB_UI_PLAN.md` (651 lines, detailed design)
- **Phase 5 SBOM Upload Plan**: `docs/PHASE5_SBOM_UPLOAD_UI.md` (639 lines, UI specs)
- **Phase 1 Enrichment API**: Existing `/v1/scan/ingest` endpoint
- **CycloneDX Spec**: https://cyclonedx.org/specification/overview/
- **SPDX Spec**: https://spdx.dev/specifications/
- **SARIF Spec**: https://sarifweb.azurewebsites.net/
- **CSAF VEX**: https://docs.oasis-open.org/csaf/csaf/v2.0/csaf-v2.0.html
