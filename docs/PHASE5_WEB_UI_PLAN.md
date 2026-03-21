# Phase 5: Web UI for API Token Management

**Date**: 2026-03-16
**Status**: 📋 PLANNING
**Priority**: HIGH (Required for SaaS launch)
**Dependencies**: Cloud SaaS Architecture (Phase 0)

---

## Executive Summary

Build a web-based admin portal for organizations to self-service manage API tokens, view usage analytics, and configure compliance frameworks. This is the "front door" for customers to onboard and integrate with the Complira API.

---

## Objectives

### Primary Goals
1. **Self-Service Onboarding**: Organizations can sign up and generate API tokens without sales intervention
2. **Token Management**: Create, rotate, revoke, and scope API tokens
3. **Usage Analytics**: View API usage, rate limits, and billing metrics
4. **Framework Configuration**: Select target compliance frameworks (FDA, CRA, IEC, NIST)

### Success Metrics
- Time-to-first-API-call < 5 minutes
- Token rotation compliance > 90%
- Self-service onboarding (no support tickets)

---

## Architecture

### Technology Stack

**Frontend**:
- **Framework**: Next.js 14 (App Router)
- **UI Components**: shadcn/ui (Radix UI + Tailwind CSS)
- **State Management**: TanStack Query (React Query)
- **Auth**: NextAuth.js v5 (Auth.js)
- **Styling**: Tailwind CSS
- **Charts**: Recharts or Tremor

**Backend API** (extends existing FastAPI):
- **Auth Endpoints**: `/v1/auth/*` (login, signup, verify)
- **Org Endpoints**: `/v1/organizations/*` (CRUD, members)
- **Token Endpoints**: `/v1/tokens/*` (CRUD, rotate, revoke)
- **Analytics Endpoints**: `/v1/analytics/*` (usage, billing)

**Database** (extends ArangoDB schema):
- New collections: `organizations`, `users`, `api_tokens`, `audit_log`

---

## Database Schema Extensions

### New Document Collections

#### 1. `organizations`
```json
{
  "_key": "org_abc123xyz",
  "name": "Acme Medical Devices Inc.",
  "domain": "acme-medical.com",
  "industry": "medical_devices",
  "tier": "professional",  // free, professional, enterprise
  "frameworks": ["FDA_524B", "IEC_62304"],
  "created_at": "2026-03-16T10:00:00Z",
  "billing_email": "billing@acme-medical.com",
  "settings": {
    "rate_limit_override": null,
    "data_retention_days": 90,
    "sso_enabled": false
  }
}
```

#### 2. `users`
```json
{
  "_key": "user_xyz789abc",
  "email": "john@acme-medical.com",
  "name": "John Smith",
  "role": "admin",  // admin, member, viewer
  "organization_id": "org_abc123xyz",
  "auth_provider": "email",  // email, google, github, azure_ad
  "auth_provider_id": "john@acme-medical.com",
  "password_hash": "$2b$12$...",  // bcrypt, only for email auth
  "email_verified": true,
  "created_at": "2026-03-16T10:00:00Z",
  "last_login": "2026-03-16T14:30:00Z",
  "mfa_enabled": false
}
```

#### 3. `api_tokens`
```json
{
  "_key": "token_def456ghi",
  "organization_id": "org_abc123xyz",
  "created_by_user_id": "user_xyz789abc",
  "name": "CI/CD Pipeline Token",
  "description": "GitHub Actions for main repo",
  "token_hash": "$2b$12$...",  // bcrypt hash of actual token
  "token_prefix": "complira_tk_abc123",  // shown in UI for identification
  "scopes": ["scan:write", "reference:read"],
  "rate_limit": 1000,  // requests per hour
  "created_at": "2026-03-16T10:00:00Z",
  "expires_at": "2027-03-16T10:00:00Z",  // 1 year
  "last_used": "2026-03-16T14:28:00Z",
  "revoked": false,
  "revoked_at": null,
  "revoked_by_user_id": null
}
```

#### 4. `audit_log`
```json
{
  "_key": "audit_jkl012mno",
  "organization_id": "org_abc123xyz",
  "user_id": "user_xyz789abc",
  "action": "token.created",
  "resource_type": "api_token",
  "resource_id": "token_def456ghi",
  "ip_address": "203.0.113.42",
  "user_agent": "Mozilla/5.0...",
  "timestamp": "2026-03-16T10:00:00Z",
  "metadata": {
    "token_name": "CI/CD Pipeline Token",
    "scopes": ["scan:write", "reference:read"]
  }
}
```

### New Edge Collections

1. **`user_belongs_to_org`**: users → organizations
2. **`token_belongs_to_org`**: api_tokens → organizations
3. **`token_created_by`**: api_tokens → users

---

## API Endpoints (New)

### Authentication (`/v1/auth`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/auth/signup` | Create organization + admin user |
| POST | `/v1/auth/login` | Email/password login → JWT |
| POST | `/v1/auth/logout` | Revoke JWT |
| POST | `/v1/auth/verify-email` | Verify email with token |
| POST | `/v1/auth/reset-password` | Send password reset email |
| POST | `/v1/auth/oauth/google` | OAuth2 login (Google) |
| POST | `/v1/auth/oauth/github` | OAuth2 login (GitHub) |
| GET | `/v1/auth/me` | Get current user info |

### Organizations (`/v1/organizations`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/organizations/{org_id}` | Get organization details |
| PATCH | `/v1/organizations/{org_id}` | Update settings |
| GET | `/v1/organizations/{org_id}/members` | List team members |
| POST | `/v1/organizations/{org_id}/members` | Invite team member |
| DELETE | `/v1/organizations/{org_id}/members/{user_id}` | Remove member |

### API Tokens (`/v1/tokens`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/tokens` | List all tokens for org |
| POST | `/v1/tokens` | Create new API token |
| GET | `/v1/tokens/{token_id}` | Get token details (no secret) |
| PATCH | `/v1/tokens/{token_id}` | Update token (name, scopes) |
| POST | `/v1/tokens/{token_id}/rotate` | Rotate token secret |
| POST | `/v1/tokens/{token_id}/revoke` | Revoke token |
| DELETE | `/v1/tokens/{token_id}` | Permanently delete token |

### Analytics (`/v1/analytics`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/analytics/usage` | API usage by endpoint/time |
| GET | `/v1/analytics/rate-limits` | Rate limit consumption |
| GET | `/v1/analytics/scans` | Scan statistics |
| GET | `/v1/analytics/findings` | Vulnerability findings trends |
| GET | `/v1/analytics/compliance` | Compliance coverage metrics |

---

## Web UI Pages

### 1. **Authentication Flow**

- `/signup` - Organization signup (name, domain, email, password)
- `/login` - Email/password or OAuth
- `/verify-email?token=xxx` - Email verification
- `/reset-password` - Password reset request
- `/reset-password/confirm?token=xxx` - New password form

### 2. **Dashboard** (`/dashboard`)

**Overview Page** (`/dashboard`):
- API usage chart (last 30 days)
- Active tokens count
- Recent scans
- Compliance score summary
- Rate limit gauge

### 3. **API Tokens** (`/dashboard/tokens`)

**Token List Page**:
```
┌─────────────────────────────────────────────────────────┐
│ API Tokens                                    [+ New]   │
├─────────────────────────────────────────────────────────┤
│ Name              │ Scopes       │ Last Used  │ Actions│
├─────────────────────────────────────────────────────────┤
│ CI/CD Pipeline    │ scan:write   │ 2 min ago  │ [•••]  │
│ complira_tk_abc123... │ ref:read     │            │        │
│                                                          │
│ Dev Environment   │ scan:write   │ 1 hour ago │ [•••]  │
│ complira_tk_xyz789... │ ref:read     │            │        │
│                                                          │
│ ⚠ Legacy Token    │ scan:write   │ 30 days ago│ [•••]  │
│ complira_tk_old123... │ ref:read     │ ROTATE!    │        │
└─────────────────────────────────────────────────────────┘
```

**Create Token Flow**:
1. Modal: "Create API Token"
2. Fields:
   - Name (required)
   - Description (optional)
   - Scopes (checkboxes):
     - `scan:write` - Ingest SBOM/SARIF scans
     - `scan:read` - Read scan results
     - `reference:read` - Query reference data (CVEs, NIST)
     - `vex:generate` - Generate VEX documents
   - Expiration (dropdown): 30 days, 90 days, 1 year, Never
3. Click "Generate Token"
4. Show token **once** with copy button:
   ```
   ⚠️ Important: Copy this token now. You won't see it again!

   complira_tk_abc123xyz789defghijklmnopqrstuvwxyz

   [Copy to Clipboard]
   ```

**Token Actions Menu** (•••):
- View Details
- Edit (name, scopes)
- Rotate Secret
- Revoke
- Delete

### 4. **Team Members** (`/dashboard/team`)

**Team List**:
```
┌─────────────────────────────────────────────────────────┐
│ Team Members                              [+ Invite]    │
├─────────────────────────────────────────────────────────┤
│ Name          │ Email              │ Role  │ Actions   │
├─────────────────────────────────────────────────────────┤
│ John Smith    │ john@acme.com      │ Admin │ [•••]     │
│ Jane Doe      │ jane@acme.com      │ Member│ [•••]     │
│ Bob Johnson   │ bob@acme.com       │ Viewer│ [•••]     │
└─────────────────────────────────────────────────────────┘
```

**Roles**:
- **Admin**: Full access (tokens, team, settings, billing)
- **Member**: Create tokens, view analytics, manage scans
- **Viewer**: Read-only access

### 5. **Settings** (`/dashboard/settings`)

**Tabs**:
- **Organization**: Name, domain, industry
- **Compliance Frameworks**: Select target frameworks (FDA, CRA, IEC, NIST)
- **Integrations**: GitHub, GitLab, Jira webhooks
- **Billing**: Subscription tier, usage, invoices
- **Security**: MFA, SSO, audit log
- **API**: Rate limits, data retention

### 6. **Analytics** (`/dashboard/analytics`)

**Charts**:
- API usage over time (line chart)
- Scans by repository (bar chart)
- Findings by severity (pie chart)
- Compliance coverage (radar chart)
- Rate limit usage (gauge)

---

## User Stories

### Story 1: Organization Signup
**As a** security engineer at a medical device company
**I want to** sign up for Complira and generate an API token
**So that** I can integrate vulnerability scanning into CI/CD

**Acceptance Criteria**:
1. Signup form validates email domain
2. Email verification sent within 1 minute
3. Upon verification, redirect to "Create First Token" flow
4. Token generated with default scopes: `scan:write`, `reference:read`
5. Quick start guide shown with example `curl` command

### Story 2: Token Rotation
**As a** security admin
**I want to** rotate API tokens without downtime
**So that** I can follow our 90-day key rotation policy

**Acceptance Criteria**:
1. "Rotate Token" generates new secret, keeps old valid for 24 hours
2. UI shows "Rotation pending - old token expires in 23h 45m"
3. After 24h, old token returns 401 with message "Token rotated - use new token"
4. Audit log records rotation event

### Story 3: Team Collaboration
**As a** team lead
**I want to** invite developers with viewer access
**So that** they can see scan results but not create/revoke tokens

**Acceptance Criteria**:
1. Invite email sent with magic link (no password required initially)
2. Viewer role can see dashboard, analytics, scan results
3. Viewer role cannot create/revoke tokens or invite members
4. Upgrade viewer to member requires admin approval

---

## Security Considerations

### Token Security
1. **Secrets Stored as Bcrypt Hashes**: Only hash stored in DB, never plaintext
2. **Token Prefix for UI**: Show `complira_tk_abc123...` in UI (last 6 chars hidden)
3. **Show Full Token Once**: After creation, full token shown once with warning
4. **Rotation Grace Period**: 24-hour overlap during rotation
5. **Automatic Expiration**: Tokens expire after configured period (default: 1 year)
6. **Revocation Immediate**: Revoked tokens rejected within 1 second (cache invalidation)

### Authentication
1. **JWT with Short TTL**: 15-minute access token, 7-day refresh token
2. **HTTP-Only Cookies**: Refresh token in HTTP-only cookie (XSS protection)
3. **CSRF Protection**: CSRF tokens for state-changing operations
4. **Rate Limiting**: 5 failed login attempts → 15-minute lockout
5. **MFA Optional**: TOTP-based 2FA (Google Authenticator)
6. **Password Requirements**: Min 12 chars, 1 uppercase, 1 number, 1 special

### Authorization
1. **RBAC**: Admin, Member, Viewer roles
2. **Scope-Based**: API tokens scoped to specific operations
3. **Organization Isolation**: Multi-tenant data isolation via `organization_id`
4. **Audit Logging**: All token operations logged with IP, user agent

---

## Implementation Plan

### Phase 5A: Backend API (2-3 weeks)

**Week 1: Auth & Organizations**
- [ ] Create new collections: `organizations`, `users`, `api_tokens`, `audit_log`
- [ ] Implement auth endpoints (signup, login, verify email)
- [ ] JWT middleware for protected routes
- [ ] Organization CRUD endpoints
- [ ] Unit tests (auth flows, token generation)

**Week 2: Token Management**
- [ ] Token CRUD endpoints (`/v1/tokens`)
- [ ] Token rotation logic (24-hour grace period)
- [ ] Token revocation (cache invalidation)
- [ ] Scope validation middleware
- [ ] Rate limiting per token

**Week 3: Analytics & Audit**
- [ ] Analytics endpoints (usage, rate limits)
- [ ] Audit log service (track all token operations)
- [ ] Team management endpoints
- [ ] Integration tests (E2E token lifecycle)

### Phase 5B: Web UI (3-4 weeks)

**Week 1: Setup & Auth UI**
- [ ] Next.js 14 project setup
- [ ] shadcn/ui components installation
- [ ] Signup/login pages
- [ ] Email verification flow
- [ ] OAuth integration (Google, GitHub)

**Week 2: Dashboard & Tokens**
- [ ] Dashboard layout (sidebar, header)
- [ ] API tokens list page
- [ ] Create token modal
- [ ] Token details page
- [ ] Rotate/revoke actions

**Week 3: Team & Settings**
- [ ] Team members page
- [ ] Invite flow
- [ ] Settings page (org, frameworks, security)
- [ ] MFA setup page

**Week 4: Analytics & Polish**
- [ ] Analytics dashboard (charts)
- [ ] Usage graphs (Recharts)
- [ ] Compliance coverage visualization
- [ ] Responsive design (mobile/tablet)
- [ ] Error handling (toast notifications)

### Phase 5C: Integration & Testing (1-2 weeks)

**Week 1: Testing**
- [ ] E2E tests (Playwright)
- [ ] API integration tests
- [ ] Security testing (OWASP Top 10)
- [ ] Load testing (token validation at scale)

**Week 2: Deployment**
- [ ] Deploy backend to AWS ECS (Fargate)
- [ ] Deploy frontend to Vercel/AWS Amplify
- [ ] Configure CDN (CloudFront)
- [ ] SSL/TLS certificates
- [ ] Monitoring (Sentry, Datadog)

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User's Browser                        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  Vercel/CloudFront    │
         │  (Next.js Frontend)   │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  AWS ALB (HTTPS)      │
         └───────────┬───────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│ ECS Fargate      │  │ ECS Fargate      │
│ FastAPI (API)    │  │ FastAPI (API)    │
└────────┬─────────┘  └─────────┬────────┘
         │                      │
         └──────────┬───────────┘
                    ▼
         ┌───────────────────────┐
         │  ArangoDB Cluster     │
         │  (Reference + Tenants)│
         └───────────────────────┘
```

---

## Cost Estimate

### Development (One-Time)
- Backend API: 2-3 weeks @ $200/hr = **$16,000 - $24,000**
- Web UI: 3-4 weeks @ $200/hr = **$24,000 - $32,000**
- Testing & Integration: 1-2 weeks @ $200/hr = **$8,000 - $16,000**
- **Total Development**: **$48,000 - $72,000**

### Infrastructure (Monthly)
- AWS ECS Fargate (2 tasks): **$70/month**
- AWS ALB: **$20/month**
- Vercel Pro (frontend): **$20/month**
- SendGrid (email): **$15/month**
- **Total Monthly**: **$125/month**

---

## Success Criteria

### Launch Readiness
- [ ] 100% test coverage for auth flows
- [ ] < 500ms page load time (dashboard)
- [ ] < 100ms API response time (token validation)
- [ ] Zero critical security vulnerabilities (OWASP)
- [ ] Mobile responsive (iOS, Android Chrome)
- [ ] Accessibility (WCAG 2.1 AA)

### Post-Launch Metrics (30 days)
- [ ] 90%+ email verification rate
- [ ] < 5 min time-to-first-API-call
- [ ] 80%+ weekly active users (returning)
- [ ] < 5 support tickets per 100 signups
- [ ] Zero token leaks (security incidents)

---

## Open Questions

1. **SSO Integration**: Should we support SAML/OIDC for enterprise customers? (Azure AD, Okta)
   - **Recommendation**: Phase 5D (Enterprise Features) - defer to Q2 2026

2. **Billing Integration**: Stripe for subscription management?
   - **Recommendation**: Yes - integrate Stripe Checkout for tiers (Free, Pro, Enterprise)

3. **Email Service**: SendGrid vs AWS SES?
   - **Recommendation**: SendGrid for transactional emails (better deliverability)

4. **Token Scopes**: Granular scopes (e.g., `scan:sarif:write`, `scan:cyclonedx:write`) or coarse-grained?
   - **Recommendation**: Start coarse-grained, add granularity in v2

5. **Audit Log Retention**: How long to keep audit logs?
   - **Recommendation**: 90 days (Free), 1 year (Pro), 7 years (Enterprise)

---

## Next Steps

1. **Review & Approval**: Get stakeholder sign-off on scope and timeline
2. **Spike: Auth Architecture**: 2-day spike on NextAuth.js vs Auth0 vs Clerk
3. **Design Mockups**: Create Figma designs for all pages
4. **Create Ticket**: Move to `tickets/in-progress/phase-5-web-ui/`
5. **Kickoff Sprint**: Start Phase 5A (Backend API)

---

## References

- **Next.js 14 Docs**: https://nextjs.org/docs
- **shadcn/ui**: https://ui.shadcn.com/
- **NextAuth.js v5**: https://authjs.dev/
- **Stripe Billing**: https://stripe.com/docs/billing
- **OWASP Token Management**: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html

---

**Document Version**: 1.0
**Last Updated**: 2026-03-16
**Status**: 📋 PLANNING (Awaiting approval)
