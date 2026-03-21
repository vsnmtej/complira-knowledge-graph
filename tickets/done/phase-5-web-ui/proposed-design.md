# Proposed Design Document - Phase 5 Web UI

## Design Version

- Current Version: `v1`

## Revision History

| Version | Trigger | Summary Of Changes | Related Review Round |
| --- | --- | --- | --- |
| v1 | 2026-03-16 | Initial design based on investigation and refined requirements | Stage 5 Review Round 1 |

## Artifact Basis

- Investigation Notes: `tickets/in-progress/phase-5-web-ui/investigation-notes.md`
- Requirements: `tickets/in-progress/phase-5-web-ui/requirements.md`
- Requirements Status: `Design-ready`

---

## Summary

Phase 5 adds a web-based user interface to Complira's cybersecurity compliance platform. The design extends the existing FastAPI backend with authentication, organization management, and real-time WebSocket support, while creating a greenfield Next.js 14 frontend with shadcn/ui components.

**Key Architectural Decisions**:
1. **Backward Compatibility**: Keep existing `customer_profiles` model unchanged, create parallel `organizations`/`users`/`api_tokens` collections
2. **Greenfield Frontend**: New Next.js 14 application with App Router, deployed separately from backend
3. **Dual Authentication**: Support both API keys (existing) and JWT sessions (new) for seamless migration
4. **WebSocket Real-Time**: FastAPI native WebSocket for enrichment progress (no Socket.IO overhead)
5. **Component-First UI**: shadcn/ui for accessibility, TanStack Query for server state, Zustand for client state

---

## Goals

### Primary Goals
1. **Self-Service Onboarding**: Time-to-first-API-call < 5 minutes (currently requires sales contact)
2. **Visual Analysis**: Non-technical users (compliance officers, auditors) can understand vulnerability data
3. **Real-Time Feedback**: Users see enrichment progress in real-time (vs blocking API call)
4. **Multi-User Collaboration**: Organizations can have multiple users with role-based access

### Non-Goals (Deferred to Phase 6)
- SSO/SAML integration
- Multi-factor authentication (MFA)
- Advanced RBAC (custom roles)
- CI/CD pipeline integration
- Scheduled scanning

---

## Legacy Removal Policy (Mandatory)

**Policy**: Maintain backward compatibility with existing API clients. NO removal of legacy code paths.

**Rationale**:
- Existing API clients (if any) must continue working with `X-API-Key` authentication
- `customer_profiles` collection must remain functional for migration period
- `/v1/account/api-keys` endpoints must support both old and new authentication methods

**Required Actions**:
- ✅ Keep `src/api/core/security.py::get_current_customer()` working with API keys
- ✅ Add JWT support as parallel authentication path (not replacement)
- ✅ Maintain `customer_profiles` collection indefinitely (or until explicit Phase 6 migration)

---

## Requirements And Use Cases

| Requirement ID | Description | Acceptance Criteria ID(s) | Use Case IDs |
| --- | --- | --- | --- |
| R-001 | User Authentication | AC1.1-AC1.5 | UC-001: Sign up, UC-002: Login |
| R-002 | API Token Management | AC2.1-AC2.5 | UC-003: Create token, UC-004: Rotate token |
| R-003 | SBOM Upload | AC3.1-AC3.5 | UC-005: Upload SBOM, UC-006: View analysis |
| R-004 | Vulnerability Dashboard | AC4.1-AC4.5 | UC-007: Analyze vulnerabilities |
| R-005 | Report Export | AC5.1-AC5.5 | UC-008: Generate PDF/VEX/CSV |
| R-006 | Token Usage Analytics | AC6.1-AC6.5 | UC-009: Monitor API usage |

---

## Codebase Understanding Snapshot (Pre-Design Mandatory)

### Entrypoints / Boundaries

| Area | Findings | Evidence | Open Unknowns |
| --- | --- | --- | --- |
| **API Entry** | FastAPI app with CORS, `/v1/*` versioned routes | `src/api/main.py:create_app()` | ✅ None |
| **Authentication** | API key auth via `X-API-Key` header, bcrypt hashing | `src/api/core/security.py:verify_api_key()` | ⚠️ JWT library choice (python-jose vs PyJWT) |
| **Database** | ArangoDB with multi-tenant isolation | `src/api/core/database.py:get_database()` | ✅ None |
| **Scan Pipeline** | Existing `/v1/scan/ingest`, ~2-5s for 200 components | `src/api/v1/endpoints/scan.py` | ⚠️ How to make async for WebSocket |

### Current Naming Conventions

| Area | Convention | Examples |
| --- | --- | --- |
| **Endpoints** | Snake case, REST verbs | `/v1/scan/ingest`, `/v1/account/api-keys` |
| **Pydantic Models** | PascalCase, suffixed with purpose | `CreateAPIKeyRequest`, `APIKeyResponse` |
| **Services** | PascalCase, suffixed `Service` | `EnrichmentService` |
| **Repositories** | PascalCase, suffixed `Repository` | `VulnerabilityRepository` |
| **Database Collections** | Snake case, plural | `customer_profiles`, `api_tokens` |

### Impacted Modules / Responsibilities

| Module | Current Responsibility | Phase 5 Changes |
| --- | --- | --- |
| `src/api/main.py` | App creation, CORS, health check | ✅ No changes |
| `src/api/core/security.py` | API key authentication | 🔄 Add JWT validation, dual auth support |
| `src/api/core/database.py` | DB connection management | 🔄 Add schema initialization for new collections |
| `src/api/v1/endpoints/account.py` | API key CRUD | 🔄 Extend with token rotation, usage stats |
| `src/api/v1/endpoints/scan.py` | SBOM ingestion | 🔄 Make async, add WebSocket support |
| `src/api/v1/router.py` | Route aggregation | 🔄 Add new routers for auth, orgs, scans list |

### Data / Persistence / External IO

| Concern | Current State | Phase 5 Changes |
| --- | --- | --- |
| **Reference DB** | `complira_reference` with vulnerability data | 🆕 Add `organizations`, `users`, `api_tokens`, `audit_log` collections |
| **Customer DBs** | `complira_customer_{id}` with scan data | 🆕 Add `scan_metadata` collection for dashboard precomputation |
| **File Storage** | Local filesystem (development) | 🔄 Migrate to AWS S3 (`complira-sbom-uploads-prod`) |
| **Email** | Not implemented | 🆕 AWS SES for verification, password reset, notifications |

---

## Current State (As-Is)

### Architecture Diagram (Current)

```
┌─────────────┐
│   Client    │ (curl, Postman, Python scripts)
└──────┬──────┘
       │ HTTP + X-API-Key header
       ▼
┌─────────────────────────────────────────────┐
│           FastAPI Backend                    │
│  ┌────────────────────────────────────────┐ │
│  │  /v1/scan/ingest (SBOM upload)         │ │
│  │  /v1/account/api-keys (token CRUD)     │ │
│  │  /v1/vex (VEX generation)              │ │
│  └────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────┐ │
│  │  API Key Auth (bcrypt)                 │ │
│  │  customer_profiles lookup              │ │
│  └────────────────────────────────────────┘ │
└──────────┬──────────────────────────────────┘
           │ AQL queries
           ▼
┌─────────────────────────────────────────────┐
│         ArangoDB                             │
│  ┌─────────────────┐  ┌──────────────────┐ │
│  │ complira_       │  │ complira_customer│ │
│  │ reference       │  │ _{org_id}        │ │
│  │                 │  │                  │ │
│  │ - vulnerabilities│  │ - scans         │ │
│  │ - weaknesses    │  │ - scan_results  │ │
│  │ - controls      │  │                  │ │
│  │ - customer_     │  │                  │ │
│  │   profiles      │  │                  │ │
│  └─────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────┘
```

### Current Authentication Flow

```
1. Client includes X-API-Key in header
2. FastAPI calls get_current_customer(api_key)
3. Query customer_profiles WHERE api_key_hash = bcrypt(api_key)
4. If found: return CustomerProfile, set customer DB context
5. If not found: raise 401 Unauthorized
```

### Current Scan Flow

```
1. POST /v1/scan/ingest with SBOM JSON
2. Parse SBOM (CycloneDX/SPDX/SARIF)
3. Extract components + vulnerabilities
4. Enrich: CVE → CWE → ATT&CK → NIST → Regulatory (BLOCKING)
5. Store results in customer DB
6. Return enriched JSON (2-5 seconds)
```

**Limitation**: Blocking API call, no progress updates, user must wait.

---

## Target State (To-Be)

### Architecture Diagram (Target)

```
┌──────────────────────────────────────────────────────────┐
│                 Web Browser (Frontend)                    │
│  ┌────────────────────────────────────────────────────┐  │
│  │     Next.js 14 App (https://app.complira.ai)       │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Pages: /login, /dashboard, /scans, /tokens │  │  │
│  │  │  Components: shadcn/ui (35 components)       │  │  │
│  │  │  State: TanStack Query + Zustand             │  │  │
│  │  │  Auth: NextAuth.js v5 (JWT sessions)         │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  └─────────┬──────────────────────────────┬────────────┘  │
└────────────┼──────────────────────────────┼───────────────┘
             │ HTTP + Authorization: Bearer │ WebSocket
             │ (JWT)                         │ ws://api/ws/scans/{id}
             ▼                               ▼
┌────────────────────────────────────────────────────────────┐
│             FastAPI Backend (api.complira.ai)               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  NEW: /v1/auth/* (signup, login, verify, refresh)   │   │
│  │  NEW: /v1/organizations/* (CRUD, members)           │   │
│  │  EXTENDED: /v1/account/api-keys/* (rotate, usage)   │   │
│  │  EXTENDED: /v1/scans (list, get, delete)            │   │
│  │  NEW: /v1/scans/{id}/analysis (dashboard data)      │   │
│  │  NEW: /v1/scans/{id}/export/{vex,pdf,csv}           │   │
│  │  NEW: WS /ws/scans/{id} (real-time progress)        │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Dual Auth: JWT (web) OR API Key (programmatic)     │   │
│  │  - JWT: NextAuth → verify token → extract user_id   │   │
│  │  - API Key: X-API-Key → bcrypt check → org_id       │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────┬──────────────────────────────────────────────────┘
           │ AQL queries
           ▼
┌────────────────────────────────────────────────────────────┐
│                    ArangoDB                                 │
│  ┌──────────────────────┐  ┌──────────────────────────┐   │
│  │ complira_reference   │  │ complira_customer_{id}   │   │
│  │                      │  │                          │   │
│  │ NEW:                 │  │ NEW:                     │   │
│  │ - organizations      │  │ - scan_metadata          │   │
│  │ - users              │  │   (dashboard cache)      │   │
│  │ - api_tokens         │  │                          │   │
│  │ - audit_log          │  │ EXISTING:                │   │
│  │                      │  │ - scans                  │   │
│  │ EXISTING (untouched):│  │ - scan_results           │   │
│  │ - customer_profiles  │  │                          │   │
│  │ - vulnerabilities    │  │                          │   │
│  │ - weaknesses         │  │                          │   │
│  └──────────────────────┘  └──────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

### Target Authentication Flow (Dual Mode)

**Mode 1: Web UI (JWT)**
```
1. User logs in at /login → POST /v1/auth/login
2. Backend verifies email + bcrypt(password) against users collection
3. Issue JWT access token (15 min) + refresh token (7 days)
4. NextAuth stores in httpOnly cookie
5. Subsequent requests: Authorization: Bearer {jwt}
6. Backend verifies JWT signature, extracts user_id
7. Lookup organization_id from user_belongs_to_org edge
8. Set customer DB context
```

**Mode 2: API Key (Backward Compatible)**
```
1. Client includes X-API-Key header
2. Backend checks api_tokens collection (bcrypt match)
3. Extract organization_id from token
4. Set customer DB context
(Fallback: Check legacy customer_profiles.api_key_hash for migration period)
```

### Target Scan Flow (Async + Real-Time)

```
1. POST /v1/scan/ingest with SBOM file
2. Validate format, create scan session → return session_id immediately
3. Client establishes WebSocket: ws://api/ws/scans/{session_id}
4. Backend starts async enrichment (Celery task or background thread)
5. Emit progress events via WebSocket:
   - {"event": "progress", "data": {"percentage": 10, "stage": "parsing"}}
   - {"event": "progress", "data": {"percentage": 30, "stage": "cwe_mapping"}}
   - {"event": "progress", "data": {"percentage": 70, "stage": "attack_mapping"}}
   - {"event": "complete", "data": {"session_id": "..."}}
6. On complete: client calls GET /v1/scans/{session_id}/analysis
7. Render dashboard with charts, tables, recommendations
```

---

## Architecture Direction Decision (Mandatory)

### Chosen Direction

**Hybrid Extension Pattern**: Add new features alongside existing code, maintain backward compatibility, use composition over modification.

### Rationale

| Dimension | Assessment |
| --- | --- |
| **Complexity** | 🟢 LOW - New code isolated in separate modules/files, minimal touch to existing code |
| **Testability** | 🟢 HIGH - New endpoints/services can be unit tested independently |
| **Operability** | 🟢 HIGH - Gradual rollout possible (backend first, then frontend), rollback safe |
| **Evolution Cost** | 🟡 MEDIUM - Dual auth adds some complexity, but enables smooth migration |

### Layering Fitness Assessment

**Current Layering**: ✅ **Coherent**
- Endpoints → Services → Repositories → Database (clean separation)
- Pydantic models for validation
- FastAPI dependency injection for database connections

**Post-Phase 5 Layering**: ✅ **Remains Coherent**
- Frontend (Next.js) → Backend API → Services → Repositories → Database
- New layer (Frontend) communicates only via REST/WebSocket APIs
- No direct database access from frontend

### Outcome

**Decision**: ✅ **Add** (new collections, new endpoints, new frontend application)

**Modifications**:
- 🔄 **Extend** `src/api/core/security.py` (add JWT alongside API keys)
- 🔄 **Extend** `/v1/scan/ingest` (add async mode with WebSocket)

**Removals**: ❌ None (maintain backward compatibility)

---

## Change Inventory (Delta)

| Change ID | Type | Current Path | Target Path | Rationale | Impacted Areas |
| --- | --- | --- | --- | --- | --- |
| **Backend Changes** |
| C-001 | Add | N/A | `src/api/v1/endpoints/auth.py` | User authentication endpoints | security.py |
| C-002 | Add | N/A | `src/api/v1/endpoints/organizations.py` | Org management endpoints | database.py |
| C-003 | Modify | `src/api/core/security.py` | (same) | Add JWT validation | All protected endpoints |
| C-004 | Modify | `src/api/v1/endpoints/account.py` | (same) | Add rotate, usage endpoints | api_tokens collection |
| C-005 | Add | N/A | `src/api/v1/endpoints/scans.py` | Scan listing, dashboard data | scan repo |
| C-006 | Add | N/A | `src/api/services/websocket.py` | WebSocket manager | scan.py |
| C-007 | Add | N/A | `src/api/services/dashboard.py` | Dashboard aggregation | repositories/* |
| C-008 | Add | N/A | `src/api/services/export.py` | PDF/CSV generation | External: reportlab |
| C-009 | Add | N/A | `src/api/models/auth.py` | Auth request/response models | N/A |
| C-010 | Add | N/A | `src/api/models/organization.py` | Org request/response models | N/A |
| **Database Changes** |
| C-011 | Add | N/A | `organizations` collection | Store organization metadata | N/A |
| C-012 | Add | N/A | `users` collection | Store user accounts | N/A |
| C-013 | Add | N/A | `api_tokens` collection | Store API tokens | security.py |
| C-014 | Add | N/A | `audit_log` collection | Store user actions | All endpoints |
| C-015 | Add | N/A | `user_belongs_to_org` edge | Link users to orgs | N/A |
| C-016 | Add | N/A | `org_owns_token` edge | Link tokens to orgs | N/A |
| **Frontend Changes** |
| C-017 | Add | N/A | `frontend/` (entire Next.js app) | Web UI | Backend API |
| C-018 | Add | N/A | `frontend/app/(auth)/login` | Login page | /v1/auth/login |
| C-019 | Add | N/A | `frontend/app/(auth)/signup` | Signup page | /v1/auth/signup |
| C-020 | Add | N/A | `frontend/app/(dashboard)/scans` | Scans list page | /v1/scans |
| C-021 | Add | N/A | `frontend/app/(dashboard)/tokens` | Tokens page | /v1/account/api-keys |
| C-022 | Add | N/A | `frontend/components/ui/*` | shadcn/ui components | N/A |
| C-023 | Add | N/A | `frontend/lib/api-client.ts` | API client (fetch wrapper) | Backend |
| C-024 | Add | N/A | `frontend/lib/websocket.ts` | WebSocket client | WS endpoint |
| **Infrastructure Changes** |
| C-025 | Add | N/A | `requirements-api.txt` additions | python-jose, passlib, email-validator, reportlab | Backend |
| C-026 | Add | N/A | `frontend/package.json` | Next.js, shadcn/ui, TanStack Query, etc. | Frontend |

**Total Changes**: 26 (8 backend files, 4 DB collections, 8 frontend directories, 6 dependency updates)

---

## Target Architecture Shape And Boundaries (Mandatory)

| Layer/Boundary | Purpose | Owns | Must Not Own | Notes |
| --- | --- | --- | --- | --- |
| **Frontend (Next.js)** | User interface, client state | UI components, routing, form validation, charts | Business logic, direct DB access | Deployed separately (Vercel/AWS Amplify) |
| **Backend API (FastAPI)** | Business logic, auth, data access | REST endpoints, WebSocket, JWT issuance, RBAC | UI rendering, frontend routing | Existing deployment (AWS ECS Fargate) |
| **Services Layer** | Reusable business logic | EnrichmentService, DashboardService, ExportService, WebSocketManager | HTTP concerns, database specifics | Testable without FastAPI |
| **Repositories Layer** | Data access abstraction | AQL queries, CRUD operations | Business logic, HTTP responses | Reusable across endpoints |
| **Database (ArangoDB)** | Persistence | Data storage, graph relationships, indexes | Application logic | Multi-tenant isolation enforced |

**Boundary Rules**:
- Frontend ↔ Backend: Only via HTTP REST or WebSocket (no direct DB access)
- Backend API ↔ Services: Dependency injection (FastAPI `Depends`)
- Services ↔ Repositories: Constructor injection
- Repositories ↔ Database: ArangoDB Python driver

---

## File And Module Breakdown

### Backend Files

| File/Module | Change | Layer | Responsibility | Public APIs | Dependencies |
| --- | --- | --- | --- | --- | --- |
| **src/api/v1/endpoints/auth.py** | Add | API | Auth endpoints | `/v1/auth/signup`, `/v1/auth/login`, `/v1/auth/verify-email`, `/v1/auth/refresh`, `/v1/auth/logout`, `/v1/auth/forgot-password`, `/v1/auth/reset-password` | security.py, database.py, models/auth.py |
| **src/api/v1/endpoints/organizations.py** | Add | API | Org management | `/v1/organizations`, `/v1/organizations/{id}`, `/v1/organizations/{id}/members` | security.py (auth), database.py |
| **src/api/v1/endpoints/scans.py** | Add | API | Scan listing & dashboard | `/v1/scans`, `/v1/scans/{id}`, `/v1/scans/{id}/analysis`, `/v1/scans/{id}/export/{format}` | services/dashboard.py, services/export.py |
| **src/api/core/security.py** | Modify | Core | Auth (dual mode) | `verify_jwt_token()`, `get_current_user()`, `get_current_customer()` (extended) | python-jose[cryptography], passlib |
| **src/api/services/websocket.py** | Add | Service | WebSocket manager | `WebSocketManager.connect()`, `.send_progress()`, `.disconnect()` | FastAPI WebSocket |
| **src/api/services/dashboard.py** | Add | Service | Dashboard aggregation | `DashboardService.get_analysis()` | repositories/enrichment.py, repositories/vulnerability.py |
| **src/api/services/export.py** | Add | Service | PDF/CSV/VEX export | `ExportService.generate_pdf()`, `.generate_csv()`, `.generate_vex()` | reportlab, csv, existing VEX service |
| **src/api/models/auth.py** | Add | Model | Auth request/response | `SignupRequest`, `LoginRequest`, `LoginResponse` (JWT tokens) | pydantic |
| **src/api/models/organization.py** | Add | Model | Org request/response | `CreateOrgRequest`, `OrgResponse`, `InviteMemberRequest` | pydantic |

### Frontend Files (Greenfield)

| File/Module | Layer | Responsibility | Key Exports | Dependencies |
| --- | --- | --- | --- | --- |
| **frontend/app/(auth)/login/page.tsx** | Page | Login UI | `default` (page component) | components/ui/form, lib/api-client |
| **frontend/app/(auth)/signup/page.tsx** | Page | Signup UI | `default` (page component) | components/ui/form, lib/api-client |
| **frontend/app/(dashboard)/layout.tsx** | Layout | Dashboard shell | Sidebar, header, protected route | next-auth, components/ui/* |
| **frontend/app/(dashboard)/scans/page.tsx** | Page | Scans list | `default` (page component) | components/scans-table, lib/api-client |
| **frontend/app/(dashboard)/scans/[id]/page.tsx** | Page | Scan analysis dashboard | `default` (dynamic route) | components/dashboard/*, lib/websocket |
| **frontend/app/(dashboard)/tokens/page.tsx** | Page | API tokens management | `default` (page component) | components/tokens-table, lib/api-client |
| **frontend/components/ui/button.tsx** | Component | shadcn/ui button | `Button` | @radix-ui/react-slot |
| **frontend/components/ui/form.tsx** | Component | shadcn/ui form | `Form`, `FormField`, `FormItem` | react-hook-form, zod |
| **frontend/components/dashboard/executive-summary.tsx** | Component | Dashboard summary card | `ExecutiveSummary` | components/ui/card, recharts |
| **frontend/components/dashboard/vulnerability-breakdown.tsx** | Component | Severity charts | `VulnerabilityBreakdown` | recharts |
| **frontend/lib/api-client.ts** | Utility | Fetch wrapper with auth | `apiClient.get/post/put/delete` | next-auth/react |
| **frontend/lib/websocket.ts** | Utility | WebSocket client | `useWebSocket()` hook | react, native WebSocket API |

---

## Layer-Appropriate Separation Of Concerns Check

✅ **Passed**

### Frontend Scope
- ✅ UI components own rendering logic only (no business logic)
- ✅ TanStack Query manages server state (caching, invalidation)
- ✅ Zustand manages client state (UI toggles, form drafts)
- ✅ Forms use react-hook-form + zod for validation (client-side only, server validates too)

### Backend API Scope
- ✅ Endpoints own HTTP concerns (request parsing, response formatting, status codes)
- ✅ Services own business logic (enrichment orchestration, dashboard aggregation)
- ✅ Repositories own data access (AQL queries, CRUD operations)
- ✅ Models own validation (Pydantic schemas)

### Integration Scope
- ✅ WebSocket manager owns connection lifecycle (connect, send, disconnect)
- ✅ Export service owns format generation (PDF layout, CSV structure)
- ✅ Email service owns delivery (AWS SES integration)

---

## Naming Decisions (Natural And Implementation-Friendly)

| Item Type | Current Name | Proposed Name | Reason |
| --- | --- | --- | --- |
| File | N/A | `auth.py` | Matches `/v1/auth/*` endpoint prefix |
| File | N/A | `organizations.py` | Matches `/v1/organizations/*` endpoint prefix |
| File | N/A | `scans.py` | Matches `/v1/scans/*` endpoint prefix (distinct from `/v1/scan/ingest`) |
| Collection | N/A | `organizations` | Standard plural noun, clear purpose |
| Collection | N/A | `users` | Standard plural noun, industry convention |
| Collection | N/A | `api_tokens` | Disambiguates from JWT tokens, plural noun |
| Edge | N/A | `user_belongs_to_org` | Verb phrase, reads naturally in AQL |
| Edge | N/A | `org_owns_token` | Verb phrase, ownership clear |
| Service | N/A | `DashboardService` | Suffix matches existing pattern (EnrichmentService) |
| Service | N/A | `WebSocketManager` | Manager suffix for connection pool |
| Function | N/A | `verify_jwt_token()` | Matches existing `verify_api_key()` pattern |
| Function | N/A | `get_current_user()` | Parallel to existing `get_current_customer()` |

---

## Naming Drift Check (Mandatory)

| Item | Current Responsibility | Name Still Match? | Corrective Action | Mapped Change ID |
| --- | --- | --- | --- | --- |
| `customer_profiles` | Customer metadata + API key | ❌ No - now "organization" concept | Keep for backward compat, introduce `organizations` | C-011 |
| `get_current_customer()` | Extract customer from API key | ⚠️ Partially - also JWT now | Extend to support dual auth (API key OR JWT) | C-003 |
| `/v1/account/api-keys` | Token CRUD | ✅ Yes - still manages API keys | N/A | N/A |
| `/v1/scan/ingest` | Upload SBOM | ⚠️ Partially - now async | Keep name, add async mode | C-006 |

---

## Existing-Structure Bias Check (Mandatory)

| Candidate Area | Current-File-Layout Bias Risk | Architecture-First Alternative | Decision | Why |
| --- | --- | --- | --- | --- |
| **Auth logic** | Add to `security.py` (existing) | Create separate `auth.py` endpoint + `AuthService` | ✅ Use alternative | `security.py` is for auth helpers, endpoint logic belongs in `endpoints/` |
| **WebSocket** | Add to `scan.py` endpoint | Create separate `websocket.py` service | ✅ Use alternative | WebSocket is infrastructure concern, reusable across endpoints |
| **Dashboard data** | Add to `scan.py` | Create `DashboardService` | ✅ Use alternative | Dashboard logic complex, deserves dedicated service |
| **Frontend structure** | Flat `/pages` (old Next.js) | Use App Router `/app/(dashboard)` | ✅ Use alternative | App Router is Next.js 14 standard, better DX |

---

**Status**: Design document in progress. Continuing with detailed schemas and API specifications...

*[Document continues in next section due to length]*

## Database Schema Specifications

### Collection: `organizations`

**Location**: `complira_reference` database
**Purpose**: Store organization metadata for multi-tenant access

```json
{
  "_key": "org_abc123xyz",           // Generated: org_{random_hex(12)}
  "name": "Acme Medical Devices Inc.",
  "slug": "acme-medical",             // URL-friendly, unique
  "domain": "acme-medical.com",       // Email domain for verification
  "industry": "medical_devices",      // Enum: medical_devices, automotive, iot, saas
  "tier": "professional",             // Enum: free, professional, enterprise
  "frameworks": [                     // Target compliance frameworks
    "FDA_524B",
    "IEC_62304"
  ],
  "settings": {
    "rate_limit_override": null,      // null = use tier default
    "data_retention_days": 90,
    "sso_enabled": false,
    "mfa_required": false
  },
  "billing_email": "billing@acme-medical.com",
  "created_at": "2026-03-16T10:00:00Z",
  "updated_at": "2026-03-16T10:00:00Z"
}
```

**Indexes**:
- `slug` (unique, hash index)
- `domain` (hash index for email verification)

---

### Collection: `users`

**Location**: `complira_reference` database
**Purpose**: User accounts with email/password authentication

```json
{
  "_key": "user_xyz789abc",          // Generated: user_{random_hex(12)}
  "email": "john@acme-medical.com",
  "email_verified": true,
  "email_verification_token": null,  // JWT token for verification
  "name": "John Smith",
  "role": "admin",                   // Enum: admin, member, viewer
  "password_hash": "$2b$12$...",     // bcrypt hash (cost 12)
  "password_reset_token": null,      // JWT token for password reset
  "password_reset_expires": null,
  "auth_provider": "email",          // Enum: email, google, github, azure_ad
  "auth_provider_id": "john@acme-medical.com",
  "mfa_enabled": false,
  "mfa_secret": null,                // TOTP secret (Phase 6)
  "last_login": "2026-03-16T14:30:00Z",
  "created_at": "2026-03-16T10:00:00Z",
  "updated_at": "2026-03-16T14:30:00Z"
}
```

**Indexes**:
- `email` (unique, hash index)
- `email_verification_token` (hash index, sparse - only set when pending)
- `password_reset_token` (hash index, sparse)

---

### Collection: `api_tokens`

**Location**: `complira_reference` database
**Purpose**: API tokens for programmatic access (replaces inline customer_profiles.api_key_hash)

```json
{
  "_key": "token_def456ghi",         // Generated: token_{random_hex(12)}
  "name": "CI/CD Pipeline Token",
  "token_hash": "$2b$12$...",        // bcrypt hash of raw token
  "token_prefix": "cpl_live_ab12",   // First 12 chars for display
  "scope": "read-write",             // Enum: read-only, read-write
  "organization_id": "org_abc123xyz",
  "created_by_user_id": "user_xyz789abc",
  "created_at": "2026-03-16T10:00:00Z",
  "expires_at": "2026-06-14T10:00:00Z",  // 90 days from creation
  "last_used_at": "2026-03-16T14:30:00Z",
  "request_count": 1247,
  "deprecated_at": null,             // Set when rotated (30-day grace)
  "revoked_at": null,                // Set when manually revoked
  "revoked_by_user_id": null
}
```

**Indexes**:
- `token_hash` (unique, hash index for fast auth lookup)
- `organization_id` (hash index for listing)
- `expires_at` (skiplist index for cleanup cron)

---

### Collection: `audit_log`

**Location**: `complira_reference` database
**Purpose**: Audit trail for security events and user actions

```json
{
  "_key": "audit_jkl890mno",         // Generated: audit_{random_hex(12)}
  "event_type": "user.login.success", // Enum: user.*, token.*, scan.*, org.*
  "actor_type": "user",              // Enum: user, api_token, system
  "actor_id": "user_xyz789abc",
  "organization_id": "org_abc123xyz",
  "ip_address": "203.0.113.42",
  "user_agent": "Mozilla/5.0...",
  "metadata": {                      // Event-specific data
    "login_method": "email_password",
    "mfa_used": false
  },
  "timestamp": "2026-03-16T14:30:00Z"
}
```

**Indexes**:
- `organization_id` + `timestamp` (compound index for org audit logs)
- `actor_id` + `timestamp` (compound index for user activity)
- `event_type` (hash index for filtering)

---

### Edge Collection: `user_belongs_to_org`

**Location**: `complira_reference` database
**Purpose**: Link users to organizations (many-to-one)

```json
{
  "_from": "users/user_xyz789abc",
  "_to": "organizations/org_abc123xyz",
  "joined_at": "2026-03-16T10:00:00Z",
  "invited_by_user_id": "user_abc123def"  // null if founder
}
```

---

### Edge Collection: `org_owns_token`

**Location**: `complira_reference` database
**Purpose**: Link API tokens to organizations (many-to-one)

```json
{
  "_from": "api_tokens/token_def456ghi",
  "_to": "organizations/org_abc123xyz",
  "created_at": "2026-03-16T10:00:00Z"
}
```

---

### Collection: `scan_metadata` (Customer Database)

**Location**: `complira_customer_{org_id}` databases
**Purpose**: Precomputed dashboard aggregations for performance

```json
{
  "_key": "scan_session_123",        // Matches scan session ID
  "scan_id": "scans/scan_session_123",
  "aggregations": {
    "total_components": 243,
    "total_vulnerabilities": 67,
    "severity_breakdown": {
      "critical": 3,
      "high": 12,
      "medium": 34,
      "low": 18
    },
    "exploitable_count": 8,          // Has EPSS > 0.5 OR KEV
    "compliance_violations": {
      "FDA_524B": 5,
      "IEC_62304": 2
    },
    "risk_score": 7.8,               // Weighted: CVSS + EPSS + KEV
    "top_cwes": [
      {"cwe_id": "CWE-79", "count": 12},
      {"cwe_id": "CWE-89", "count": 8}
    ],
    "top_attack_techniques": [
      {"technique_id": "T1190", "count": 15}
    ]
  },
  "computed_at": "2026-03-16T14:31:00Z",
  "ttl": 86400                       // Cache for 24 hours
}
```

---

## API Endpoint Specifications

### Authentication Endpoints

#### `POST /v1/auth/signup`

**Purpose**: User registration with email/password

**Request**:
```json
{
  "email": "john@acme-medical.com",
  "password": "SecureP@ssw0rd!",
  "name": "John Smith",
  "organization_name": "Acme Medical Devices Inc.",
  "industry": "medical_devices"
}
```

**Response** (201 Created):
```json
{
  "user_id": "user_xyz789abc",
  "organization_id": "org_abc123xyz",
  "email": "john@acme-medical.com",
  "email_verified": false,
  "message": "Verification email sent to john@acme-medical.com"
}
```

**Business Logic**:
1. Validate email format + password strength (min 8 chars, 1 uppercase, 1 number, 1 special)
2. Check email not already registered
3. Create `organizations` document with slug (e.g., "acme-medical-devices")
4. Create `users` document with bcrypt password hash
5. Create `user_belongs_to_org` edge
6. Generate email verification JWT (expires in 24 hours)
7. Send verification email via AWS SES
8. Return user_id + organization_id

---

#### `POST /v1/auth/login`

**Purpose**: User login with email/password

**Request**:
```json
{
  "email": "john@acme-medical.com",
  "password": "SecureP@ssw0rd!"
}
```

**Response** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 900,                 // 15 minutes
  "user": {
    "user_id": "user_xyz789abc",
    "email": "john@acme-medical.com",
    "name": "John Smith",
    "role": "admin",
    "organization": {
      "organization_id": "org_abc123xyz",
      "name": "Acme Medical Devices Inc.",
      "tier": "professional"
    }
  }
}
```

**Business Logic**:
1. Lookup user by email
2. Verify bcrypt password hash
3. Check email_verified = true (reject if false)
4. Lookup organization via `user_belongs_to_org` edge
5. Generate JWT access token (15 min expiry):
   ```json
   {
     "sub": "user_xyz789abc",
     "email": "john@acme-medical.com",
     "org_id": "org_abc123xyz",
     "role": "admin",
     "exp": 1710598800
   }
   ```
6. Generate JWT refresh token (7 days expiry)
7. Update `users.last_login`
8. Log `user.login.success` to audit_log
9. Return tokens + user metadata

---

#### `POST /v1/auth/verify-email`

**Purpose**: Verify user email via token from email link

**Request**:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Email verified successfully"
}
```

**Business Logic**:
1. Verify JWT signature + expiry
2. Extract user_id from token
3. Update `users.email_verified = true`
4. Clear `users.email_verification_token`
5. Log `user.email.verified` to audit_log

---

### Organization Endpoints

#### `GET /v1/organizations/{org_id}`

**Purpose**: Get organization details

**Auth**: JWT (admin/member/viewer)

**Response** (200 OK):
```json
{
  "organization_id": "org_abc123xyz",
  "name": "Acme Medical Devices Inc.",
  "slug": "acme-medical",
  "domain": "acme-medical.com",
  "industry": "medical_devices",
  "tier": "professional",
  "frameworks": ["FDA_524B", "IEC_62304"],
  "settings": {
    "rate_limit_override": null,
    "data_retention_days": 90,
    "sso_enabled": false
  },
  "created_at": "2026-03-16T10:00:00Z"
}
```

---

#### `GET /v1/organizations/{org_id}/members`

**Purpose**: List organization members

**Auth**: JWT (admin/member/viewer)

**Response** (200 OK):
```json
{
  "members": [
    {
      "user_id": "user_xyz789abc",
      "email": "john@acme-medical.com",
      "name": "John Smith",
      "role": "admin",
      "joined_at": "2026-03-16T10:00:00Z",
      "last_login": "2026-03-16T14:30:00Z"
    },
    {
      "user_id": "user_def456ghi",
      "email": "jane@acme-medical.com",
      "name": "Jane Doe",
      "role": "member",
      "joined_at": "2026-03-17T09:00:00Z",
      "last_login": "2026-03-17T11:00:00Z"
    }
  ],
  "total": 2
}
```

---

### Scan Endpoints

#### `GET /v1/scans`

**Purpose**: List all scans for organization

**Auth**: JWT or API Key

**Query Params**:
- `limit` (default: 50, max: 100)
- `offset` (default: 0)
- `sort` (default: "created_at", options: "created_at", "name", "risk_score")
- `order` (default: "desc", options: "asc", "desc")
- `filter_severity` (optional: "critical", "high", "medium", "low")

**Response** (200 OK):
```json
{
  "scans": [
    {
      "session_id": "scan_session_123",
      "name": "app-v1.2.3-cyclonedx.json",
      "format": "cyclonedx",          // cyclonedx, spdx, sarif
      "status": "completed",          // pending, processing, completed, failed
      "uploaded_by": "john@acme-medical.com",
      "created_at": "2026-03-16T14:30:00Z",
      "summary": {
        "total_components": 243,
        "total_vulnerabilities": 67,
        "severity_breakdown": {
          "critical": 3,
          "high": 12,
          "medium": 34,
          "low": 18
        },
        "risk_score": 7.8
      }
    }
  ],
  "total": 15,
  "limit": 50,
  "offset": 0
}
```

---

#### `GET /v1/scans/{session_id}/analysis`

**Purpose**: Get dashboard aggregation data for scan

**Auth**: JWT or API Key

**Response** (200 OK):
```json
{
  "session_id": "scan_session_123",
  "scan_name": "app-v1.2.3-cyclonedx.json",
  "executive_summary": {
    "risk_score": 7.8,              // 0-10 scale
    "total_components": 243,
    "total_vulnerabilities": 67,
    "exploitable_vulnerabilities": 8,
    "compliance_violations": 7,
    "remediation_priority": "high"
  },
  "severity_breakdown": {
    "critical": {
      "count": 3,
      "components": ["openssl@1.0.2", "lodash@4.17.15"],
      "top_cves": ["CVE-2024-1234", "CVE-2024-5678"]
    },
    "high": {"count": 12, "...": "..."},
    "medium": {"count": 34, "...": "..."},
    "low": {"count": 18, "...": "..."}
  },
  "compliance_status": {
    "FDA_524B": {
      "violations": 5,
      "requirements_affected": [
        {
          "requirement_id": "FDA_524B_R1",
          "title": "Cybersecurity Bill of Materials",
          "violation_reason": "3 critical vulnerabilities without patches within 30 days"
        }
      ]
    },
    "IEC_62304": {
      "violations": 2,
      "...": "..."
    }
  },
  "component_inventory": [
    {
      "component_id": "comp_123",
      "name": "openssl",
      "version": "1.0.2",
      "purl": "pkg:npm/openssl@1.0.2",
      "vulnerabilities": 2,
      "max_severity": "critical",
      "risk_score": 9.1,
      "cves": ["CVE-2024-1234", "CVE-2024-5678"]
    }
  ],
  "attack_chains": [
    {
      "cve_id": "CVE-2024-1234",
      "summary": "Remote Code Execution in OpenSSL",
      "cvss_score": 9.8,
      "epss_score": 0.78,
      "kev_status": true,
      "chain": {
        "cwe": ["CWE-119 (Buffer Overflow)"],
        "attack_techniques": ["T1190 (Exploit Public-Facing Application)"],
        "nist_controls": ["SI-2 (Flaw Remediation)", "RA-5 (Vulnerability Scanning)"]
      }
    }
  ],
  "remediation_recommendations": [
    {
      "priority": 1,
      "component": "openssl@1.0.2",
      "action": "Upgrade to openssl@3.0.0",
      "rationale": "Fixes CVE-2024-1234 (CVSS 9.8, EPSS 0.78, KEV)",
      "impact": "Resolves 2 critical vulnerabilities"
    }
  ]
}
```

---

### WebSocket Endpoint

#### `WS /ws/scans/{session_id}`

**Purpose**: Real-time enrichment progress updates

**Auth**: Query param `?token={jwt}` OR header `Sec-WebSocket-Protocol: Bearer, {jwt}`

**Events Sent (Server → Client)**:

```json
// Connection established
{"event": "connected", "data": {"session_id": "scan_session_123"}}

// Enrichment started
{"event": "started", "data": {"session_id": "scan_session_123", "total_components": 243}}

// Progress updates
{"event": "progress", "data": {
  "percentage": 10,
  "stage": "parsing",
  "message": "Parsing SBOM components...",
  "components_processed": 24,
  "components_total": 243
}}

{"event": "progress", "data": {
  "percentage": 30,
  "stage": "cve_mapping",
  "message": "Mapping CVE vulnerabilities...",
  "vulnerabilities_found": 67
}}

{"event": "progress", "data": {
  "percentage": 50,
  "stage": "cwe_mapping",
  "message": "Mapping CWE weaknesses..."
}}

{"event": "progress", "data": {
  "percentage": 70,
  "stage": "attack_mapping",
  "message": "Mapping MITRE ATT&CK techniques..."
}}

{"event": "progress", "data": {
  "percentage": 90,
  "stage": "regulatory_mapping",
  "message": "Analyzing compliance violations..."
}}

// Completion
{"event": "complete", "data": {
  "session_id": "scan_session_123",
  "duration_seconds": 23,
  "vulnerabilities_found": 67
}}

// Error (if enrichment fails)
{"event": "error", "data": {
  "message": "Enrichment pipeline failed: CVE lookup timeout",
  "code": "ENRICHMENT_TIMEOUT"
}}
```

**Events Received (Client → Server)**:

```json
// Ping (keepalive)
{"event": "ping"}

// Cancel enrichment
{"event": "cancel", "data": {"session_id": "scan_session_123"}}
```

---

## Design System Specifications

### Color Palette (Professional Cybersecurity Theme)

**Primary Colors**:
- `primary-900`: `#0A1F44` (Dark navy - headers, nav)
- `primary-700`: `#1E3A5F` (Navy - primary buttons)
- `primary-500`: `#2563EB` (Blue - links, accents)
- `primary-300`: `#60A5FA` (Light blue - hover states)
- `primary-50`: `#EFF6FF` (Very light blue - backgrounds)

**Semantic Colors**:
- `critical`: `#DC2626` (Red - critical vulnerabilities)
- `high`: `#EA580C` (Orange - high severity)
- `medium`: `#F59E0B` (Amber - medium severity)
- `low`: `#10B981` (Green - low severity)
- `success`: `#059669` (Green - success states)
- `warning`: `#D97706` (Amber - warnings)
- `info`: `#0891B2` (Cyan - info messages)

**Neutral Colors** (Tailwind default grays):
- `gray-900` to `gray-50` for text, borders, backgrounds

### Typography

**Font Stack**:
```css
--font-sans: 'Inter', ui-sans-serif, system-ui, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;
```

**Type Scale**:
- `text-xs`: 0.75rem (12px) - Labels, captions
- `text-sm`: 0.875rem (14px) - Body, table cells
- `text-base`: 1rem (16px) - Default body
- `text-lg`: 1.125rem (18px) - Subheadings
- `text-xl`: 1.25rem (20px) - Card titles
- `text-2xl`: 1.5rem (24px) - Page titles
- `text-3xl`: 1.875rem (30px) - Hero headings

---

## Frontend Component Hierarchy

### Layout Components

```
<RootLayout>
  ├── <NextAuthProvider>
  ├── <TanStackQueryProvider>
  └── <Toaster> (toast notifications)

<AuthLayout> (for /login, /signup)
  └── <Card> (centered auth form)

<DashboardLayout> (for authenticated pages)
  ├── <Sidebar>
  │   ├── Logo
  │   ├── Navigation Links
  │   └── User Menu
  ├── <Header>
  │   ├── Breadcrumbs
  │   └── User Avatar + Dropdown
  └── <MainContent>
      └── {children}
```

### Page Components

```
/app/(auth)/login/page.tsx
  └── <LoginForm>
      ├── <Input> (email)
      ├── <Input> (password, type="password")
      ├── <Button> (submit)
      └── <Link> (forgot password, signup)

/app/(dashboard)/scans/page.tsx
  ├── <PageHeader>
  │   ├── <h1> "Scans"
  │   └── <Button> "Upload SBOM"
  ├── <ScansTable>
  │   ├── TanStack Table instance
  │   ├── Columns: Name, Type, Date, Findings, Actions
  │   └── <Badge> (severity indicators)
  └── <Pagination>

/app/(dashboard)/scans/[id]/page.tsx
  ├── <ScanHeader>
  │   ├── Scan name
  │   ├── <Badge> (status)
  │   └── <DropdownMenu> (export options)
  ├── <ExecutiveSummary>
  │   ├── <Card> Risk Score (large number + gauge chart)
  │   ├── <Card> Total Vulnerabilities
  │   ├── <Card> Exploitable (EPSS/KEV)
  │   └── <Card> Compliance Violations
  ├── <VulnerabilityBreakdown>
  │   ├── <Card> Severity Pie Chart (Recharts)
  │   └── <Card> Top CVEs Bar Chart
  ├── <ComplianceStatus>
  │   └── <Accordion> (per framework)
  │       ├── FDA 524B violations (expandable)
  │       └── IEC 62304 violations
  ├── <ComponentInventory>
  │   └── <DataTable> (TanStack Table)
  │       ├── Sortable columns
  │       ├── Expandable rows (show CVEs)
  │       └── Risk score column
  └── <RemediationRecommendations>
      └── <Card> (prioritized list)
          ├── Priority badge
          ├── Component name
          ├── Action (upgrade/patch)
          └── Impact summary
```

---

## Integration Flows

### Flow 1: User Signup & Email Verification

```
[Browser] → POST /v1/auth/signup
          ← 201 Created {user_id, organization_id, message}
          
[Backend] → AWS SES: Send verification email
          
[User] Clicks email link with token
[Browser] → GET /v1/auth/verify-email?token={jwt}
          ← 200 OK {success: true}
          → Redirect to /login
```

### Flow 2: User Login & JWT Session

```
[Browser] → POST /v1/auth/login {email, password}
          ← 200 OK {access_token, refresh_token, user}
          
[NextAuth] Stores tokens in httpOnly cookies
          
[Browser] → GET /v1/scans
          (Authorization: Bearer {access_token})
          ← 200 OK {scans: [...]}
```

### Flow 3: SBOM Upload with Real-Time Progress

```
[Browser] → POST /v1/scan/ingest (multipart/form-data)
          ← 202 Accepted {session_id: "scan_session_123"}
          
[Browser] Establishes WebSocket:
          WS /ws/scans/scan_session_123?token={jwt}
          ← {"event": "connected"}
          ← {"event": "started", "data": {total_components: 243}}
          ← {"event": "progress", "data": {percentage: 10, stage: "parsing"}}
          ← {"event": "progress", "data": {percentage: 30, stage: "cve_mapping"}}
          ...
          ← {"event": "complete", "data": {session_id: "scan_session_123"}}
          
[Browser] → GET /v1/scans/scan_session_123/analysis
          ← 200 OK {executive_summary, severity_breakdown, ...}
          
[Browser] Renders dashboard with data
```

---

## Performance Optimization Strategy

### Backend Optimizations

1. **Precompute Dashboard Data**:
   - Create `scan_metadata` collection on enrichment complete
   - Store aggregations (severity counts, top CWEs, compliance violations)
   - TTL: 24 hours (refresh if stale)

2. **Database Indexes**:
   - `api_tokens.token_hash` (unique hash) - O(1) auth lookup
   - `users.email` (unique hash) - O(1) login lookup
   - `scans.organization_id + created_at` (compound skiplist) - fast scan listing

3. **WebSocket Connection Pooling**:
   - Use `WebSocketManager` singleton to track active connections
   - Limit 1,000 concurrent connections per server
   - Heartbeat every 30 seconds to detect dead connections

4. **Async Enrichment**:
   - Use FastAPI background tasks OR Celery for large SBOMs
   - Email notification for scans > 500 components (expected >30s)

### Frontend Optimizations

1. **Code Splitting**:
   - Next.js automatic code splitting per page
   - Lazy load dashboard charts: `const Chart = dynamic(() => import('recharts'))`

2. **Data Caching**:
   - TanStack Query caching (5-minute stale time)
   - Optimistic updates for mutations (instant UI feedback)

3. **Image Optimization**:
   - Next.js `<Image>` component for automatic optimization
   - WebP format with fallbacks

4. **Bundle Size**:
   - Target: < 200KB initial JS bundle
   - Use tree-shaking for shadcn/ui components (only import what's used)

---

## Security Implementation Details

### JWT Token Structure

**Access Token** (15-minute expiry):
```json
{
  "alg": "HS256",
  "typ": "JWT"
}
{
  "sub": "user_xyz789abc",           // User ID
  "email": "john@acme-medical.com",
  "org_id": "org_abc123xyz",
  "role": "admin",
  "iat": 1710597900,                 // Issued at
  "exp": 1710598800                  // Expires (15 min)
}
```

**Refresh Token** (7-day expiry):
```json
{
  "sub": "user_xyz789abc",
  "type": "refresh",
  "iat": 1710597900,
  "exp": 1711202700                  // 7 days
}
```

**JWT Secret**: Stored in environment variable `JWT_SECRET` (min 256-bit random string)

### Password Requirements

- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 number
- At least 1 special character (`!@#$%^&*()`)

**Regex**:
```python
r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
```

### CSRF Protection

- NextAuth.js automatically handles CSRF for state-changing requests
- Custom API calls use `X-CSRF-Token` header from NextAuth session

### Rate Limiting

**Implementation**: Redis-based sliding window
**Limits**:
- Free tier: 100 requests/day
- Professional: 10,000 requests/day
- Enterprise: Unlimited

**Response** (429 Too Many Requests):
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 3600,               // seconds
  "limit": 100,
  "remaining": 0,
  "reset_at": "2026-03-17T00:00:00Z"
}
```

---

**Status**: Proposed design v1 complete. Ready for Stage 4 (Runtime Modeling) and Stage 5 (Review Gate).

