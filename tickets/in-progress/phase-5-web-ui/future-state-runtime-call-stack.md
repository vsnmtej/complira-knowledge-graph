# Future-State Runtime Call Stacks (Debug-Trace Style)

Use this document as a future-state (`to-be`) execution model derived from the design basis.
Prefer exact `file:function` frames, explicit branching, and clear state/persistence boundaries.

## Conventions

- Frame format: `path/to/file.ts:functionName(args?)` or `path/to/file.py:functionName(args?)`
- Boundary tags:
  - `[ENTRY]` external entrypoint (API/HTTP/WebSocket)
  - `[ASYNC]` async boundary (`await`, background task, queue)
  - `[STATE]` in-memory mutation
  - `[IO]` file/network/database/cache IO
  - `[FALLBACK]` non-primary branch
  - `[ERROR]` error path
- Comments: use brief inline comments with `# ...`
- Do not include legacy/backward-compatibility branches

---

## Design Basis

- **Scope Classification**: `Large` (greenfield frontend + significant backend extensions)
- **Call Stack Version**: `v1`
- **Requirements**: `tickets/in-progress/phase-5-web-ui/requirements.md` (status: `Design-ready`)
- **Source Artifact**: `tickets/in-progress/phase-5-web-ui/proposed-design.md`
- **Source Design Version**: `v1`
- **Referenced Sections**: Database Schema Specifications, API Endpoint Specifications, Integration Flows

---

## Future-State Modeling Rule (Mandatory)

- Model target design behavior even when current code diverges.
- If migration from as-is to to-be requires transition logic, describe that logic in `Transition Notes`.
- Do not replace the to-be call stack with current flow.

---

## Use Case Index (Stable IDs)

| use_case_id | Source Type | Requirement ID(s) | Design-Risk Objective | Use Case Name | Coverage (Primary/Fallback/Error) |
| --- | --- | --- | --- | --- | --- |
| UC-001 | Requirement | R-001 (FR-1) | N/A | User Signup with Email Verification | Yes/Yes/Yes |
| UC-002 | Requirement | R-001 (FR-1) | N/A | User Login with JWT Session | Yes/Yes/Yes |
| UC-003 | Requirement | R-002 (FR-3) | N/A | API Token Generation | Yes/N/A/Yes |
| UC-004 | Requirement | R-003 (FR-4, FR-5) | N/A | SBOM Upload with Real-Time Progress | Yes/Yes/Yes |
| UC-005 | Requirement | R-004 (FR-6) | N/A | Dashboard Data Rendering | Yes/Yes/Yes |
| UC-006 | Design-Risk | R-003 (NFR-1.3) | Handle large SBOM files (>500 components) | Async Enrichment with Email Notification | Yes/N/A/Yes |

---

## Transition Notes

### Dual Authentication Migration

**Temporary Behavior**:
- `src/api/core/security.py:get_current_customer()` must support BOTH:
  1. NEW: JWT from `Authorization: Bearer {token}` header
  2. EXISTING: API Key from `X-API-Key` header

**Implementation**:
```python
async def get_current_customer(
    authorization: Optional[str] = Header(None),  # NEW: JWT
    x_api_key: Optional[str] = Header(None)       # EXISTING: API Key
) -> Customer:
    # Priority: JWT > API Key
    if authorization and authorization.startswith("Bearer "):
        # NEW PATH: Verify JWT, extract user_id, lookup org
        return await get_customer_from_jwt(authorization[7:])
    elif x_api_key:
        # EXISTING PATH: Verify API key, lookup customer_profiles
        return await get_customer_from_api_key(x_api_key)
    else:
        raise HTTPException(401, "Missing authentication")
```

**Retirement Plan**:
- Phase 6: Migrate existing API key users to new `api_tokens` collection
- After 6 months: Deprecate `customer_profiles.api_key_hash` field (keep collection for metadata)

---

## Use Case: UC-001 [User Signup with Email Verification]

### Goal

Allow new users to self-service register, creating both a user account and organization, then verify email before accessing the dashboard.

### Preconditions

- User has valid email address
- Email domain not already registered (optional check)
- Password meets complexity requirements

### Expected Outcome

- `users` document created with `email_verified=false`
- `organizations` document created
- `user_belongs_to_org` edge created
- Email sent with verification JWT
- HTTP 201 response returned with `user_id`, `organization_id`

---

### Primary Runtime Call Stack

```text
[ENTRY] Frontend: frontend/app/(auth)/signup/page.tsx:handleSubmit(form)
├── frontend/lib/api-client.ts:apiClient.post('/v1/auth/signup', payload)
│   └── [IO] HTTP POST /v1/auth/signup
│
[ENTRY] Backend: src/api/main.py:app (FastAPI app receives request)
├── src/api/v1/router.py:api_router (routes to /v1/auth/signup)
├── src/api/v1/endpoints/auth.py:signup(request: SignupRequest)
│   │
│   ├── src/api/models/auth.py:SignupRequest.validate(data)  # Pydantic validation
│   │   ├── validate email format (email-validator library)
│   │   └── validate password strength (regex check)
│   │
│   ├── src/api/core/database.py:get_database()  # Dependency injection
│   │   └── [IO] Connect to ArangoDB (reference database)
│   │
│   ├── src/api/repositories/user_repository.py:check_email_exists(email)
│   │   └── [IO] AQL: FOR u IN users FILTER u.email == @email RETURN u
│   │   └── [ERROR] if exists → raise HTTPException(400, "Email already registered")
│   │
│   ├── src/api/repositories/organization_repository.py:create_organization(data)
│   │   ├── generate_slug(organization_name)  # "Acme Inc" → "acme-inc"
│   │   ├── generate_org_id()  # "org_" + secrets.token_hex(12)
│   │   ├── [STATE] org_doc = {_key, name, slug, domain, tier="free", ...}
│   │   └── [IO] db["organizations"].insert(org_doc)
│   │
│   ├── src/api/repositories/user_repository.py:create_user(data, organization_id)
│   │   ├── hash_password(password)  # passlib bcrypt.hash(password, rounds=12)
│   │   ├── generate_user_id()  # "user_" + secrets.token_hex(12)
│   │   ├── [STATE] user_doc = {_key, email, password_hash, email_verified=false, ...}
│   │   └── [IO] db["users"].insert(user_doc)
│   │
│   ├── src/api/repositories/user_repository.py:link_user_to_org(user_id, org_id)
│   │   ├── [STATE] edge_doc = {_from: "users/{user_id}", _to: "organizations/{org_id}", ...}
│   │   └── [IO] db["user_belongs_to_org"].insert(edge_doc)
│   │
│   ├── src/api/core/security.py:generate_email_verification_token(user_id, email)
│   │   ├── [STATE] payload = {sub: user_id, email: email, exp: now + 24h}
│   │   └── jose.jwt.encode(payload, JWT_SECRET, algorithm="HS256")
│   │
│   ├── src/api/repositories/user_repository.py:store_verification_token(user_id, token)
│   │   └── [IO] db["users"].update(user_id, {email_verification_token: token})
│   │
│   ├── [ASYNC] src/api/services/email_service.py:send_verification_email(email, token)
│   │   ├── construct_verification_link(f"https://app.complira.ai/verify-email?token={token}")
│   │   ├── render_email_template("verification.html", {link, name})
│   │   └── [IO] AWS SES: boto3.client('ses').send_email(...)
│   │   └── [ERROR] if SES fails → log error, continue (user can resend)
│   │
│   ├── src/api/repositories/audit_repository.py:log_event(event)
│   │   ├── [STATE] audit_doc = {event_type: "user.signup", actor_id: user_id, ...}
│   │   └── [IO] db["audit_log"].insert(audit_doc)
│   │
│   └── src/api/models/auth.py:SignupResponse.construct(user_id, org_id, email)
│       └── [ENTRY] return HTTP 201 {user_id, organization_id, email, email_verified: false}
│
Frontend: frontend/app/(auth)/signup/page.tsx:onSuccess(response)
├── Show success message: "Verification email sent to {email}"
└── Redirect to /login after 3 seconds
```

---

### Branching / Fallback Paths

```text
[FALLBACK] If organization slug already exists (rare collision)
src/api/repositories/organization_repository.py:create_organization(data)
├── generate_slug(organization_name)  # "acme-inc"
├── [IO] check if slug exists: db["organizations"].find({slug: "acme-inc"})
├── if exists → append random suffix: "acme-inc-a4b2"
└── [IO] db["organizations"].insert(org_doc with updated slug)

[FALLBACK] If AWS SES is unavailable (email send fails)
src/api/services/email_service.py:send_verification_email(email, token)
├── [IO] boto3.client('ses').send_email(...) → raises ClientError
├── [ERROR] Log failure to CloudWatch
├── Store token in database (already done above)
└── Continue with signup (return 201), user can resend verification email via /v1/auth/resend-verification
```

---

### Error Paths

```text
[ERROR] Email already registered
src/api/repositories/user_repository.py:check_email_exists(email)
└── [IO] AQL query returns existing user
    └── src/api/v1/endpoints/auth.py:signup() raises HTTPException(400, "Email already registered")
        └── [ENTRY] return HTTP 400 {error: "Email already registered"}

[ERROR] Password too weak
src/api/models/auth.py:SignupRequest.validate(data)
└── password fails regex check (< 8 chars, no uppercase, etc.)
    └── raises ValidationError
        └── [ENTRY] return HTTP 422 {detail: [{msg: "Password must be at least 8 characters..."}]}

[ERROR] Database write failure (ArangoDB down)
src/api/repositories/organization_repository.py:create_organization(data)
└── [IO] db["organizations"].insert(org_doc) → raises ArangoServerError
    └── src/api/v1/endpoints/auth.py:signup() → FastAPI catches exception
        └── [ENTRY] return HTTP 500 {error: "Internal server error"} (logged to CloudWatch)
```

---

## Use Case: UC-002 [User Login with JWT Session]

### Goal

Authenticate user with email/password, issue JWT access + refresh tokens, return user metadata including organization.

### Preconditions

- User has completed signup
- Email has been verified (`email_verified=true`)
- Password is correct

### Expected Outcome

- JWT access token (15-min expiry) issued
- JWT refresh token (7-day expiry) issued
- `users.last_login` updated
- `audit_log` entry created
- HTTP 200 response with tokens + user metadata

---

### Primary Runtime Call Stack

```text
[ENTRY] Frontend: frontend/app/(auth)/login/page.tsx:handleSubmit(form)
├── frontend/lib/api-client.ts:apiClient.post('/v1/auth/login', {email, password})
│   └── [IO] HTTP POST /v1/auth/login
│
[ENTRY] Backend: src/api/v1/endpoints/auth.py:login(request: LoginRequest)
│   │
│   ├── src/api/models/auth.py:LoginRequest.validate(data)  # email + password
│   │
│   ├── src/api/repositories/user_repository.py:get_user_by_email(email)
│   │   └── [IO] AQL: FOR u IN users FILTER u.email == @email RETURN u
│   │   └── [ERROR] if not found → raise HTTPException(401, "Invalid credentials")
│   │
│   ├── src/api/core/security.py:verify_password(plain_password, password_hash)
│   │   └── passlib.bcrypt.verify(plain_password, password_hash)
│   │   └── [ERROR] if mismatch → raise HTTPException(401, "Invalid credentials")
│   │
│   ├── src/api/repositories/user_repository.py:check_email_verified(user)
│   │   └── [ERROR] if user.email_verified == false → raise HTTPException(403, "Email not verified")
│   │
│   ├── src/api/repositories/user_repository.py:get_user_organization(user_id)
│   │   └── [IO] AQL graph traversal:
│   │       FOR org IN OUTBOUND @user_id user_belongs_to_org RETURN org
│   │   └── [ERROR] if no org found → raise HTTPException(500, "User not linked to organization")
│   │
│   ├── src/api/core/security.py:create_access_token(user_id, email, org_id, role)
│   │   ├── [STATE] payload = {sub: user_id, email, org_id, role: "admin", exp: now + 15min}
│   │   └── jose.jwt.encode(payload, JWT_SECRET, algorithm="HS256")
│   │
│   ├── src/api/core/security.py:create_refresh_token(user_id)
│   │   ├── [STATE] payload = {sub: user_id, type: "refresh", exp: now + 7days}
│   │   └── jose.jwt.encode(payload, JWT_SECRET, algorithm="HS256")
│   │
│   ├── src/api/repositories/user_repository.py:update_last_login(user_id)
│   │   └── [IO] db["users"].update(user_id, {last_login: datetime.utcnow()})
│   │
│   ├── src/api/repositories/audit_repository.py:log_event(event)
│   │   ├── [STATE] audit_doc = {event_type: "user.login.success", actor_id: user_id, ip_address, ...}
│   │   └── [IO] db["audit_log"].insert(audit_doc)
│   │
│   └── src/api/models/auth.py:LoginResponse.construct(access_token, refresh_token, user, organization)
│       └── [ENTRY] return HTTP 200 {access_token, refresh_token, user: {...}, organization: {...}}
│
Frontend: NextAuth.js receives tokens
├── Store access_token + refresh_token in httpOnly cookies
├── Store user metadata in NextAuth session
└── Redirect to /dashboard
```

---

### Branching / Fallback Paths

```text
[FALLBACK] If refresh token expired (>7 days)
Frontend: frontend/lib/api-client.ts:apiClient.get('/v1/scans')
├── [IO] HTTP GET /v1/scans with Authorization: Bearer {expired_access_token}
├── Backend responds 401 {error: "Token expired"}
├── Frontend tries to refresh: POST /v1/auth/refresh {refresh_token}
├── Backend: src/api/v1/endpoints/auth.py:refresh_token(refresh_token)
│   ├── jose.jwt.decode(refresh_token) → raises JWTExpiredSignatureError
│   └── [ERROR] return HTTP 401 {error: "Refresh token expired, please log in again"}
└── Frontend: Redirect to /login, show message "Session expired"
```

---

### Error Paths

```text
[ERROR] User not found (typo in email)
src/api/repositories/user_repository.py:get_user_by_email(email)
└── [IO] AQL query returns empty result
    └── raise HTTPException(401, "Invalid credentials")  # Generic message for security
        └── [ENTRY] return HTTP 401 {error: "Invalid credentials"}

[ERROR] Password incorrect
src/api/core/security.py:verify_password(plain_password, password_hash)
└── passlib.bcrypt.verify() returns False
    └── raise HTTPException(401, "Invalid credentials")
        └── [ENTRY] return HTTP 401 {error: "Invalid credentials"}

[ERROR] Email not verified
src/api/repositories/user_repository.py:check_email_verified(user)
└── user.email_verified == false
    └── raise HTTPException(403, "Email not verified. Check your inbox for verification link.")
        └── [ENTRY] return HTTP 403 {error: "Email not verified...", resend_url: "/v1/auth/resend-verification"}
```

---

## Use Case: UC-003 [API Token Generation]

### Goal

Authenticated admin user creates an API token for programmatic access (CI/CD, scripts).

### Preconditions

- User is authenticated (valid JWT)
- User has `admin` role in organization
- Token name is unique within organization

### Expected Outcome

- `api_tokens` document created with bcrypt hash
- `org_owns_token` edge created
- Raw token (plaintext) returned ONCE in response
- `audit_log` entry created
- HTTP 201 response with token metadata + plaintext token

---

### Primary Runtime Call Stack

```text
[ENTRY] Frontend: frontend/app/(dashboard)/tokens/page.tsx:handleCreateToken(form)
├── frontend/lib/api-client.ts:apiClient.post('/v1/account/api-keys', {name, scope})
│   ├── Include Authorization: Bearer {jwt} header
│   └── [IO] HTTP POST /v1/account/api-keys
│
[ENTRY] Backend: src/api/v1/endpoints/account.py:create_api_key(request, current_user)
│   │
│   ├── src/api/core/security.py:get_current_user(jwt)  # Dependency
│   │   ├── jose.jwt.decode(jwt, JWT_SECRET)  # Verify signature + expiry
│   │   ├── [IO] db["users"].get(payload["sub"])
│   │   └── [ERROR] if JWT invalid → raise HTTPException(401, "Invalid token")
│   │
│   ├── src/api/core/security.py:require_role(current_user, "admin")
│   │   └── [ERROR] if current_user.role != "admin" → raise HTTPException(403, "Admin role required")
│   │
│   ├── src/api/repositories/token_repository.py:check_token_name_exists(org_id, name)
│   │   └── [IO] AQL: FOR t IN api_tokens FILTER t.organization_id == @org_id AND t.name == @name RETURN t
│   │   └── [ERROR] if exists → raise HTTPException(400, "Token name already exists")
│   │
│   ├── src/api/core/security.py:generate_api_token(length=48)
│   │   └── secrets.token_urlsafe(48)  # Generates random secure token
│   │   └── [STATE] raw_token = "cpl_live_ab12...xyz89" (48 chars)
│   │
│   ├── src/api/core/security.py:hash_api_key(raw_token)
│   │   └── bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt(rounds=12))
│   │   └── [STATE] token_hash = "$2b$12$..."
│   │
│   ├── src/api/repositories/token_repository.py:create_token(data)
│   │   ├── generate_token_id()  # "token_" + secrets.token_hex(12)
│   │   ├── [STATE] token_doc = {
│   │   │     _key: token_id,
│   │   │     name, token_hash, token_prefix: raw_token[:12],
│   │   │     scope, organization_id, created_by_user_id,
│   │   │     created_at, expires_at: created_at + 90 days,
│   │   │     last_used_at: null, request_count: 0
│   │   │   }
│   │   └── [IO] db["api_tokens"].insert(token_doc)
│   │
│   ├── src/api/repositories/token_repository.py:link_token_to_org(token_id, org_id)
│   │   ├── [STATE] edge_doc = {_from: "api_tokens/{token_id}", _to: "organizations/{org_id}"}
│   │   └── [IO] db["org_owns_token"].insert(edge_doc)
│   │
│   ├── src/api/repositories/audit_repository.py:log_event(event)
│   │   ├── [STATE] audit_doc = {event_type: "token.created", actor_id: user_id, metadata: {token_id, name}}
│   │   └── [IO] db["audit_log"].insert(audit_doc)
│   │
│   └── src/api/models/account.py:CreateAPIKeyResponse.construct(token_metadata, raw_token)
│       └── [ENTRY] return HTTP 201 {
│             token: raw_token,  # ONLY TIME plaintext is returned
│             token_id, name, scope, created_at, expires_at, token_prefix
│           }
│
Frontend: frontend/app/(dashboard)/tokens/page.tsx:onSuccess(response)
├── Show modal: "Save this token - you won't see it again!"
├── Display response.token in monospace font with copy button
└── After user clicks "Done", navigate back to tokens list (token hidden forever)
```

---

### Error Paths

```text
[ERROR] Token name already exists
src/api/repositories/token_repository.py:check_token_name_exists(org_id, name)
└── [IO] AQL query returns existing token with same name
    └── raise HTTPException(400, "Token name 'CI/CD Pipeline' already exists")
        └── [ENTRY] return HTTP 400 {error: "Token name already exists"}

[ERROR] User is not admin
src/api/core/security.py:require_role(current_user, "admin")
└── current_user.role == "member" (not admin)
    └── raise HTTPException(403, "Admin role required to create API tokens")
        └── [ENTRY] return HTTP 403 {error: "Admin role required..."}
```

---

## Use Case: UC-004 [SBOM Upload with Real-Time Progress]

### Goal

User uploads SBOM file (CycloneDX/SPDX), enrichment pipeline runs asynchronously, WebSocket sends real-time progress updates, dashboard displays results.

### Preconditions

- User is authenticated
- SBOM file is valid (parseable JSON/XML)
- File size < 10MB

### Expected Outcome

- File uploaded to S3
- `scans` document created
- Enrichment pipeline runs in background
- WebSocket sends progress events (10%, 30%, 50%, 70%, 90%, 100%)
- `scan_metadata` precomputed aggregations created
- HTTP 202 response with `session_id`

---

### Primary Runtime Call Stack

```text
[ENTRY] Frontend: frontend/app/(dashboard)/scans/upload/page.tsx:handleUpload(file)
├── frontend/lib/api-client.ts:apiClient.post('/v1/scan/ingest', formData)
│   ├── Include Authorization: Bearer {jwt} header
│   ├── multipart/form-data with file + metadata
│   └── [IO] HTTP POST /v1/scan/ingest
│
[ENTRY] Backend: src/api/v1/endpoints/scan.py:ingest_scan(file: UploadFile, current_user)
│   │
│   ├── src/api/core/security.py:get_current_user(jwt)  # Auth dependency
│   │
│   ├── src/api/services/scan_service.py:validate_file(file)
│   │   ├── Check file size < 10MB
│   │   ├── Check Content-Type (application/json or application/xml)
│   │   └── [ERROR] if invalid → raise HTTPException(400, "Invalid file format")
│   │
│   ├── src/api/services/scan_service.py:generate_session_id()
│   │   └── [STATE] session_id = "scan_session_" + secrets.token_hex(16)
│   │
│   ├── [ASYNC] src/api/services/scan_service.py:upload_to_s3(file, session_id)
│   │   ├── boto3.client('s3').upload_fileobj(file, bucket="complira-sbom-uploads-prod", key=f"{org_id}/{session_id}.json")
│   │   └── [IO] S3 upload completes
│   │   └── [ERROR] if S3 fails → raise HTTPException(500, "File upload failed")
│   │
│   ├── src/api/repositories/scan_repository.py:create_scan_record(session_id, metadata)
│   │   ├── [STATE] scan_doc = {
│   │   │     _key: session_id,
│   │   │     name: file.filename,
│   │   │     format: detect_format(file),  # cyclonedx, spdx, sarif
│   │   │     status: "processing",
│   │   │     s3_path: f"s3://{bucket}/{org_id}/{session_id}.json",
│   │   │     uploaded_by: current_user.user_id,
│   │   │     created_at: datetime.utcnow()
│   │   │   }
│   │   └── [IO] db_customer["scans"].insert(scan_doc)  # Customer-specific DB
│   │
│   ├── [ASYNC] FastAPI BackgroundTasks.add_task(enrich_scan, session_id, org_id, file_content)
│   │   # Enrichment runs in background thread (see UC-004-ASYNC below)
│   │
│   └── src/api/models/scan.py:ScanIngestResponse.construct(session_id, status)
│       └── [ENTRY] return HTTP 202 {session_id, status: "processing", message: "Enrichment started"}
│
Frontend: frontend/app/(dashboard)/scans/upload/page.tsx:onSuccess(response)
├── Store session_id in state
├── Establish WebSocket connection: useWebSocket(`/ws/scans/${session_id}`)
└── Render progress bar component (initially 0%)
```

---

### [UC-004-ASYNC] Background Enrichment Pipeline (Parallel to WebSocket)

```text
[ASYNC] src/api/services/enrichment_service.py:enrich_scan(session_id, org_id, file_content)
│
├── src/api/services/websocket_service.py:get_connection(session_id)
│   └── [STATE] Retrieve WebSocket connection from WebSocketManager (if connected)
│
├── src/api/services/websocket_service.py:send_progress(session_id, {event: "started", total_components: 243})
│   └── [IO] WebSocket.send_json({event: "started", data: {...}})
│
├── [10%] src/api/parsers/cyclonedx.py:parse_sbom(file_content)
│   ├── Detect format (CycloneDX vs SPDX vs SARIF)
│   ├── Parse JSON schema, extract components + vulnerabilities
│   └── [STATE] components = [{name, version, purl, cves}, ...]
│   └── src/api/services/websocket_service.py:send_progress(session_id, {percentage: 10, stage: "parsing"})
│
├── [30%] src/api/services/enrichment_service.py:map_cves(components)
│   ├── FOR EACH component.cves:
│   │   └── [IO] db_reference["vulnerabilities"].find({vulnerability_id: cve_id})
│   └── [STATE] Enrich components with CVSS scores, published dates
│   └── src/api/services/websocket_service.py:send_progress(session_id, {percentage: 30, stage: "cve_mapping", vulnerabilities_found: 67})
│
├── [50%] src/api/services/enrichment_service.py:map_cwes(vulnerabilities)
│   ├── FOR EACH vulnerability:
│   │   └── [IO] Graph traversal: FOR cwe IN OUTBOUND vulnerability cve_has_cwe RETURN cwe
│   └── [STATE] Attach CWE data to each vulnerability
│   └── src/api/services/websocket_service.py:send_progress(session_id, {percentage: 50, stage: "cwe_mapping"})
│
├── [70%] src/api/services/enrichment_service.py:map_attack_techniques(cwes)
│   ├── FOR EACH cwe:
│   │   └── [IO] Graph traversal: FOR tech IN OUTBOUND cwe cwe_exploited_by_technique RETURN tech
│   └── [STATE] Attach ATT&CK techniques
│   └── src/api/services/websocket_service.py:send_progress(session_id, {percentage: 70, stage: "attack_mapping"})
│
├── [90%] src/api/services/enrichment_service.py:map_regulatory_violations(techniques, org_frameworks)
│   ├── org_frameworks = ["FDA_524B", "IEC_62304"]  # From organization settings
│   ├── FOR EACH technique:
│   │   └── [IO] Graph traversal: FOR req IN OUTBOUND technique technique_violates_requirement RETURN req
│   ├── [STATE] Aggregate violations per framework
│   └── src/api/services/websocket_service.py:send_progress(session_id, {percentage: 90, stage: "regulatory_mapping"})
│
├── [95%] src/api/services/dashboard_service.py:precompute_aggregations(session_id, enriched_data)
│   ├── Calculate risk_score = weighted_avg(CVSS, EPSS, KEV)
│   ├── Count severity_breakdown = {critical: 3, high: 12, medium: 34, low: 18}
│   ├── Identify top_cwes, top_attack_techniques
│   ├── [STATE] scan_metadata_doc = {session_id, aggregations: {...}, computed_at, ttl: 86400}
│   └── [IO] db_customer["scan_metadata"].insert(scan_metadata_doc)
│
├── [100%] src/api/repositories/scan_repository.py:update_scan_status(session_id, "completed")
│   └── [IO] db_customer["scans"].update(session_id, {status: "completed"})
│
├── src/api/services/websocket_service.py:send_progress(session_id, {
│   │   event: "complete",
│   │   data: {session_id, duration_seconds: 23, vulnerabilities_found: 67}
│   │ })
│   └── [IO] WebSocket.send_json({event: "complete", ...})
│
└── src/api/services/websocket_service.py:close_connection(session_id)
    └── [IO] WebSocket.close()
```

---

### WebSocket Connection Flow (Parallel to Enrichment)

```text
[ENTRY] Frontend: frontend/lib/websocket.ts:useWebSocket(`/ws/scans/${session_id}`)
├── const ws = new WebSocket(`wss://api.complira.ai/ws/scans/${session_id}?token=${jwt}`)
└── [IO] WebSocket connection established
│
[ENTRY] Backend: src/api/v1/endpoints/websocket.py:websocket_endpoint(websocket, session_id, token)
│   │
│   ├── src/api/core/security.py:verify_jwt_token(token)  # Auth from query param
│   │   └── [ERROR] if invalid → ws.close(code=1008, reason="Unauthorized")
│   │
│   ├── src/api/services/websocket_service.py:WebSocketManager.connect(session_id, websocket)
│   │   ├── [STATE] active_connections[session_id] = websocket
│   │   └── Send initial message: {event: "connected", data: {session_id}}
│   │
│   └── WHILE connection open:
│       ├── Receive messages from client (optional ping/pong)
│       ├── Send progress messages from enrichment pipeline (see UC-004-ASYNC above)
│       └── [ERROR] if client disconnects → WebSocketManager.disconnect(session_id)
│
Frontend: frontend/app/(dashboard)/scans/upload/page.tsx:WebSocket.onmessage(event)
├── Parse JSON: data = JSON.parse(event.data)
├── SWITCH data.event:
│   ├── CASE "connected": setConnected(true)
│   ├── CASE "started": setTotalComponents(data.total_components)
│   ├── CASE "progress": updateProgressBar(data.percentage, data.stage)
│   ├── CASE "complete":
│   │   ├── setProgress(100)
│   │   ├── Fetch dashboard data: apiClient.get(`/v1/scans/${session_id}/analysis`)
│   │   └── Redirect to /scans/${session_id} (dashboard page)
│   └── CASE "error": showErrorMessage(data.message)
└── WebSocket.close()
```

---

### Branching / Fallback Paths

```text
[FALLBACK] If WebSocket connection fails (firewall, proxy blocks WS)
Frontend: frontend/lib/websocket.ts:useWebSocket()
├── Try WebSocket connection → fails after 5 seconds
├── [FALLBACK] Switch to polling mode:
│   └── setInterval(() => {
│         apiClient.get(`/v1/scans/${session_id}`)  # Poll scan status every 2 seconds
│         if (scan.status === "completed") {
│           fetch analysis data, redirect to dashboard
│         }
│       }, 2000)
└── Show warning: "Real-time updates unavailable, polling instead"

[FALLBACK] If SBOM file is very large (>500 components)
src/api/services/enrichment_service.py:enrich_scan(session_id, org_id, file_content)
├── component_count = len(components)
├── if component_count > 500:
│   ├── Log: "Large SBOM detected ({component_count} components), sending email notification"
│   ├── [ASYNC] src/api/services/email_service.py:send_scan_complete_email(user_email, session_id)
│   │   └── [IO] AWS SES: "Your SBOM analysis is complete. View results: https://app.complira.ai/scans/{session_id}"
│   └── Continue enrichment (user may close browser)
└── else: No email (enrichment completes in <30s, user stays on page)
```

---

### Error Paths

```text
[ERROR] Invalid SBOM format (malformed JSON)
src/api/parsers/cyclonedx.py:parse_sbom(file_content)
└── json.loads(file_content) → raises JSONDecodeError
    ├── src/api/services/websocket_service.py:send_error(session_id, {message: "Invalid JSON format", code: "PARSE_ERROR"})
    ├── src/api/repositories/scan_repository.py:update_scan_status(session_id, "failed")
    └── Frontend shows error: "Upload failed: Invalid JSON format"

[ERROR] CVE lookup timeout (NVD API slow)
src/api/services/enrichment_service.py:map_cves(components)
└── [IO] db_reference["vulnerabilities"].find(...) → timeout after 30 seconds
    ├── [ERROR] Log timeout to CloudWatch
    ├── Continue with partial data (mark missing CVEs as "unknown")
    └── src/api/services/websocket_service.py:send_warning(session_id, {message: "Some CVE data unavailable"})

[ERROR] S3 upload fails
src/api/services/scan_service.py:upload_to_s3(file, session_id)
└── boto3.client('s3').upload_fileobj(...) → raises ClientError
    └── raise HTTPException(500, "File upload failed. Please try again.")
        └── [ENTRY] return HTTP 500 {error: "File upload failed"}
```

---

## Use Case: UC-005 [Dashboard Data Rendering]

### Goal

User navigates to scan analysis dashboard, fetches precomputed aggregations, renders interactive charts and tables.

### Preconditions

- Scan has completed enrichment (`status="completed"`)
- `scan_metadata` aggregations have been precomputed
- User is authenticated

### Expected Outcome

- Dashboard data fetched from `/v1/scans/{session_id}/analysis`
- Executive summary rendered (risk score, vulnerability counts)
- Charts rendered (severity breakdown, top CVEs)
- Component inventory table rendered
- Remediation recommendations displayed
- HTTP 200 response with dashboard JSON

---

### Primary Runtime Call Stack

```text
[ENTRY] Frontend: frontend/app/(dashboard)/scans/[id]/page.tsx:useEffect()
├── const {data, isLoading} = useQuery(['scan-analysis', session_id], () =>
│     frontend/lib/api-client.ts:apiClient.get(`/v1/scans/${session_id}/analysis`)
│   )
├── [IO] HTTP GET /v1/scans/{session_id}/analysis
│
[ENTRY] Backend: src/api/v1/endpoints/scans.py:get_scan_analysis(session_id, current_user)
│   │
│   ├── src/api/core/security.py:get_current_user(jwt)  # Auth
│   │
│   ├── src/api/repositories/scan_repository.py:get_scan(session_id, org_id)
│   │   ├── [IO] db_customer["scans"].get(session_id)
│   │   └── [ERROR] if not found → raise HTTPException(404, "Scan not found")
│   │   └── [ERROR] if scan.organization_id != current_user.org_id → raise HTTPException(403, "Forbidden")
│   │
│   ├── src/api/repositories/scan_repository.py:check_scan_status(scan)
│   │   └── [ERROR] if scan.status != "completed" → raise HTTPException(400, "Scan still processing")
│   │
│   ├── src/api/repositories/scan_repository.py:get_scan_metadata(session_id)
│   │   ├── [IO] db_customer["scan_metadata"].get(session_id)
│   │   ├── if found AND not expired (ttl < 24h):
│   │   │   └── [STATE] Return cached aggregations
│   │   └── [FALLBACK] if missing or expired:
│   │       └── src/api/services/dashboard_service.py:recompute_aggregations(session_id)
│   │           └── (Same computation as UC-004-ASYNC 95% step)
│   │
│   ├── src/api/services/dashboard_service.py:format_dashboard_response(scan, metadata, org_frameworks)
│   │   ├── Construct executive_summary {risk_score, total_vulnerabilities, exploitable_count, ...}
│   │   ├── Construct severity_breakdown {critical: {count, components, top_cves}, ...}
│   │   ├── Construct compliance_status {FDA_524B: {violations, requirements_affected}, ...}
│   │   ├── [IO] db_customer["scan_results"].find({scan_id: session_id}) → Get component inventory
│   │   ├── [IO] db_reference graph traversal → Get attack chains (CVE → CWE → ATT&CK → NIST)
│   │   └── Construct remediation_recommendations (sorted by priority: KEV > EPSS > CVSS)
│   │
│   └── src/api/models/scan.py:ScanAnalysisResponse.construct(dashboard_data)
│       └── [ENTRY] return HTTP 200 {
│             session_id, scan_name,
│             executive_summary, severity_breakdown, compliance_status,
│             component_inventory, attack_chains, remediation_recommendations
│           }
│
Frontend: frontend/app/(dashboard)/scans/[id]/page.tsx:render(data)
├── <ExecutiveSummary data={data.executive_summary} />
│   ├── Render risk score (7.8/10) with gauge chart (Recharts)
│   ├── Render total vulnerabilities (67) with trend icon
│   └── Render compliance violations (7) with warning badge
│
├── <VulnerabilityBreakdown data={data.severity_breakdown} />
│   ├── Render pie chart (Recharts): Critical 4%, High 18%, Medium 51%, Low 27%
│   └── Render bar chart: Top 5 CVEs by CVSS score
│
├── <ComplianceStatus data={data.compliance_status} />
│   └── <Accordion> (expandable per framework)
│       ├── FDA 524B: 5 violations (expand to show specific requirements)
│       └── IEC 62304: 2 violations
│
├── <ComponentInventory data={data.component_inventory} />
│   └── <DataTable> (TanStack Table)
│       ├── Columns: Component, Version, Vulnerabilities, Max Severity, Risk Score
│       ├── Sortable by risk score (descending by default)
│       ├── Expandable rows → Show CVEs for each component
│       └── Search filter by component name
│
└── <RemediationRecommendations data={data.remediation_recommendations} />
    └── FOR EACH recommendation (sorted by priority):
        ├── <Card>
        │   ├── Priority badge (1, 2, 3, ...)
        │   ├── Component name (openssl@1.0.2)
        │   ├── Action (Upgrade to openssl@3.0.0)
        │   └── Impact (Resolves 2 critical vulnerabilities, CVSS 9.8, KEV)
        └── </Card>
```

---

### Branching / Fallback Paths

```text
[FALLBACK] If scan_metadata cache is expired (>24 hours old)
src/api/repositories/scan_repository.py:get_scan_metadata(session_id)
├── [IO] db_customer["scan_metadata"].get(session_id) → Returns doc with old timestamp
├── Check: datetime.utcnow() - metadata.computed_at > 24 hours
├── if expired:
│   ├── Log: "Cache expired for scan {session_id}, recomputing"
│   ├── src/api/services/dashboard_service.py:recompute_aggregations(session_id)
│   │   ├── Query scan_results, run aggregations (same as enrichment 95% step)
│   │   └── [IO] db_customer["scan_metadata"].update(session_id, {aggregations, computed_at: now})
│   └── Return refreshed metadata
└── else: Return cached metadata (fast path)

[FALLBACK] If user requests CSV export instead of dashboard view
Frontend: frontend/app/(dashboard)/scans/[id]/page.tsx:handleExport('csv')
├── apiClient.get(`/v1/scans/${session_id}/export/csv`)
├── Backend: src/api/v1/endpoints/scans.py:export_scan_csv(session_id)
│   ├── Fetch component_inventory from scan_results
│   ├── Generate CSV: "Component,Version,CVE,Severity,CVSS,EPSS,KEV\n..."
│   └── [ENTRY] return HTTP 200 (Content-Type: text/csv, Content-Disposition: attachment)
└── Frontend: Browser downloads file "complira-scan_session_123-2026-03-16.csv"
```

---

### Error Paths

```text
[ERROR] Scan not found
src/api/repositories/scan_repository.py:get_scan(session_id, org_id)
└── [IO] db_customer["scans"].get(session_id) → Returns None
    └── raise HTTPException(404, "Scan not found")
        └── [ENTRY] return HTTP 404 {error: "Scan not found"}
        └── Frontend: Show error page "Scan not found. It may have been deleted."

[ERROR] Scan still processing (user navigates too early)
src/api/repositories/scan_repository.py:check_scan_status(scan)
└── scan.status == "processing" (enrichment not complete)
    └── raise HTTPException(400, "Scan still processing. Please wait.")
        └── [ENTRY] return HTTP 400 {error: "Scan still processing", eta_seconds: 15}
        └── Frontend: Show loading spinner + message "Analysis in progress... (ETA: 15 seconds)"

[ERROR] User tries to access another organization's scan
src/api/repositories/scan_repository.py:get_scan(session_id, org_id)
└── scan.organization_id != current_user.org_id
    └── raise HTTPException(403, "You do not have access to this scan")
        └── [ENTRY] return HTTP 403 {error: "Forbidden"}
        └── Frontend: Show error "Access denied"
```

---

## Use Case: UC-006 [Async Enrichment with Email Notification] (Design-Risk)

### Goal

Handle large SBOM files (>500 components) that take >30 seconds to enrich. Send email notification when complete instead of requiring user to wait.

### Preconditions

- SBOM has >500 components
- User email is verified
- Enrichment takes >30 seconds

### Expected Outcome

- User receives email notification when enrichment completes
- Email contains link to dashboard
- User can close browser during enrichment (no WebSocket required)

---

### Primary Runtime Call Stack

```text
[ENTRY] src/api/services/enrichment_service.py:enrich_scan(session_id, org_id, file_content)
├── component_count = len(components)  # 743 components
├── if component_count > 500:
│   ├── Log: "Large SBOM ({component_count} components) - will send email notification"
│   ├── user = get_user_by_id(current_user.user_id)
│   │   └── [IO] db["users"].get(user_id)
│   │
│   ├── Continue enrichment (same as UC-004-ASYNC pipeline)
│   │   └── ... (10%, 30%, 50%, 70%, 90%, 100%)
│   │
│   ├── [100%] After enrichment completes:
│   │   └── [ASYNC] src/api/services/email_service.py:send_scan_complete_email(user.email, session_id, scan_name)
│   │       ├── construct_scan_link(f"https://app.complira.ai/scans/{session_id}")
│   │       ├── render_email_template("scan_complete.html", {
│   │       │     name: user.name,
│   │       │     scan_name: scan.name,
│   │       │     vulnerabilities_found: 127,
│   │       │     critical_count: 8,
│   │       │     link: scan_link
│   │       │   })
│   │       └── [IO] AWS SES: boto3.client('ses').send_email(
│   │             Source="no-reply@complira.ai",
│   │             Destination={'ToAddresses': [user.email]},
│   │             Message={'Subject': "SBOM Analysis Complete - 127 vulnerabilities found", 'Body': html}
│   │           )
│   │
│   └── Log audit event: "scan.completed_with_notification"
│
└── else:  # <500 components, no email
    └── (Standard flow from UC-004, user stays on page with WebSocket)
```

---

**Status**: Runtime modeling complete for all critical use cases (UC-001 through UC-006). Ready for Stage 5 Review Gate.
