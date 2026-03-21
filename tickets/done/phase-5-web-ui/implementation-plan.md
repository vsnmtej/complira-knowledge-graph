# Implementation Plan - Phase 5 Web UI

**Ticket**: phase-5-web-ui
**Stage**: 6 (Implementation)
**Created**: 2026-03-16
**Strategy**: Phased incremental delivery with vertical slices

---

## Implementation Strategy

**Approach**: Build and test vertical slices end-to-end, rather than horizontal layers.

**Why Vertical Slices**:
- ✅ Each phase delivers working functionality (testable)
- ✅ Reduces integration risk (find issues early)
- ✅ Enables incremental deployment
- ✅ User can validate features as they're built

**Phase Ordering**: Authentication → Upload → Dashboard → Export

---

## Phase 1: Backend Authentication Foundation (Week 1)

**Goal**: Users can sign up, verify email, and log in with JWT sessions

### 1.1 Dependencies & Infrastructure (Day 1)

**Tasks**:
- [ ] Update `requirements-api.txt` with new dependencies:
  - `python-jose[cryptography]` (JWT handling)
  - `passlib[bcrypt]` (password hashing)
  - `email-validator` (email validation)
- [ ] Create database initialization script for new collections
- [ ] Test database connection and schema creation

**Deliverable**: Backend can create users/organizations collections

---

### 1.2 Authentication Models (Day 1)

**Files to Create**:
- `src/api/models/auth.py` - Request/response models

**Models**:
```python
class SignupRequest(BaseModel):
    email: EmailStr
    password: str  # Min 8 chars, validated by regex
    name: str
    organization_name: str
    industry: str  # Enum

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserProfile

class UserProfile(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    organization: OrganizationSummary
```

**Deliverable**: Pydantic models with validation

---

### 1.3 JWT Security Extensions (Day 2)

**Files to Modify**:
- `src/api/core/security.py` - Extend with JWT support

**New Functions**:
```python
def create_access_token(user_id: str, email: str, org_id: str, role: str) -> str
def create_refresh_token(user_id: str) -> str
def verify_jwt_token(token: str) -> dict
def hash_password(password: str) -> str
def verify_password(plain_password: str, hashed_password: str) -> bool
async def get_current_user(authorization: Optional[str] = Header(None)) -> User
async def get_current_customer(
    authorization: Optional[str] = Header(None),  # JWT
    x_api_key: Optional[str] = Header(None)       # API Key (backward compat)
) -> Customer
```

**Dual Auth Logic** (UC-002 from runtime):
```python
# Priority: JWT > API Key
if authorization and authorization.startswith("Bearer "):
    return await get_customer_from_jwt(authorization[7:])
elif x_api_key:
    return await get_customer_from_api_key(x_api_key)
else:
    raise HTTPException(401, "Missing authentication")
```

**Deliverable**: JWT issuance and verification working

---

### 1.4 User & Organization Repositories (Day 2)

**Files to Create**:
- `src/api/repositories/user_repository.py`
- `src/api/repositories/organization_repository.py`

**Key Functions**:
```python
# user_repository.py
async def create_user(email, password_hash, name, role) -> User
async def get_user_by_email(email) -> Optional[User]
async def get_user_by_id(user_id) -> Optional[User]
async def update_last_login(user_id) -> None
async def link_user_to_org(user_id, org_id) -> None
async def get_user_organization(user_id) -> Organization

# organization_repository.py
async def create_organization(name, slug, domain, industry, tier) -> Organization
async def get_organization_by_id(org_id) -> Optional[Organization]
async def generate_slug(name) -> str
```

**Deliverable**: Database CRUD operations for users/orgs

---

### 1.5 Authentication Endpoints (Day 3)

**Files to Create**:
- `src/api/v1/endpoints/auth.py`

**Endpoints**:
```python
POST /v1/auth/signup
POST /v1/auth/login
POST /v1/auth/verify-email
POST /v1/auth/refresh
POST /v1/auth/logout
POST /v1/auth/forgot-password
POST /v1/auth/reset-password
```

**Implementation Priority**:
1. Signup (UC-001) - 2 hours
2. Login (UC-002) - 1 hour
3. Verify email - 1 hour
4. Refresh token - 30 mins
5. Password reset - deferred to Phase 6 (not critical for MVP)

**Deliverable**: Working signup and login endpoints

---

### 1.6 Email Service (Day 3)

**Files to Create**:
- `src/api/services/email_service.py`

**Functions**:
```python
async def send_verification_email(email: str, token: str, name: str) -> None
async def send_password_reset_email(email: str, token: str, name: str) -> None
async def send_scan_complete_email(email: str, session_id: str, scan_name: str) -> None
```

**Email Templates** (HTML):
- `templates/email/verification.html`
- `templates/email/scan_complete.html`

**AWS SES Integration**:
```python
import boto3
ses_client = boto3.client('ses', region_name='us-east-1')
ses_client.send_email(...)
```

**Deliverable**: Email verification working end-to-end

---

### 1.7 Router Integration & Testing (Day 4)

**Files to Modify**:
- `src/api/v1/router.py` - Add auth router

**Testing**:
- [ ] Unit tests for JWT creation/verification
- [ ] Unit tests for password hashing
- [ ] Integration test: Signup → Verify → Login flow
- [ ] Test dual authentication (JWT + API key)

**Test Files**:
- `tests/unit/test_security.py`
- `tests/integration/test_auth_flow.py`

**Deliverable**: Authentication fully tested and working

---

## Phase 2: Frontend Authentication UI (Week 2, Days 1-3)

**Goal**: Users can sign up and log in via web UI

### 2.1 Frontend Bootstrap (Day 1)

**Tasks**:
- [ ] Initialize Next.js 14 project: `npx create-next-app@latest frontend`
- [ ] Configure App Router structure
- [ ] Install shadcn/ui: `npx shadcn-ui@latest init`
- [ ] Install dependencies: TanStack Query, Zustand, NextAuth.js v5
- [ ] Create folder structure:
  ```
  frontend/
  ├── app/
  │   ├── (auth)/
  │   │   ├── login/page.tsx
  │   │   └── signup/page.tsx
  │   ├── (dashboard)/
  │   │   ├── layout.tsx
  │   │   └── scans/page.tsx
  │   └── layout.tsx
  ├── components/
  │   └── ui/  (shadcn components)
  └── lib/
      ├── api-client.ts
      └── auth.ts
  ```

**Deliverable**: Empty Next.js app running at `localhost:3000`

---

### 2.2 shadcn/ui Component Setup (Day 1)

**Components to Install**:
```bash
npx shadcn-ui@latest add button
npx shadcn-ui@latest add input
npx shadcn-ui@latest add label
npx shadcn-ui@latest add card
npx shadcn-ui@latest add form
npx shadcn-ui@latest add toast
```

**Deliverable**: UI component library ready

---

### 2.3 API Client & NextAuth Configuration (Day 2)

**Files to Create**:
- `frontend/lib/api-client.ts` - Fetch wrapper with JWT
- `frontend/app/api/auth/[...nextauth]/route.ts` - NextAuth config

**API Client**:
```typescript
const apiClient = {
  async post(url: string, data: any) {
    const session = await getSession()
    const res = await fetch(`${API_URL}${url}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(session?.accessToken && {
          'Authorization': `Bearer ${session.accessToken}`
        })
      },
      body: JSON.stringify(data)
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  }
}
```

**NextAuth Config**:
```typescript
export const authOptions = {
  providers: [
    CredentialsProvider({
      async authorize(credentials) {
        const res = await fetch(`${API_URL}/v1/auth/login`, {
          method: 'POST',
          body: JSON.stringify(credentials)
        })
        if (res.ok) return await res.json()
        return null
      }
    })
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.accessToken = user.access_token
        token.refreshToken = user.refresh_token
      }
      return token
    }
  }
}
```

**Deliverable**: Frontend can call backend API with authentication

---

### 2.4 Signup & Login UI (Day 3)

**Files to Create**:
- `frontend/app/(auth)/signup/page.tsx`
- `frontend/app/(auth)/login/page.tsx`

**Signup Form** (react-hook-form + zod):
```typescript
const signupSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).regex(/[A-Z]/).regex(/[0-9]/).regex(/[!@#$%^&*]/),
  name: z.string().min(2),
  organization_name: z.string().min(2),
  industry: z.enum(['medical_devices', 'automotive', 'iot', 'saas'])
})

function SignupPage() {
  const form = useForm<SignupFormValues>({ resolver: zodResolver(signupSchema) })

  async function onSubmit(data: SignupFormValues) {
    const result = await apiClient.post('/v1/auth/signup', data)
    toast({ title: 'Verification email sent to ' + data.email })
    router.push('/login')
  }

  return <Form {...form}>...</Form>
}
```

**Deliverable**: Working signup and login UI

---

## Phase 3: SBOM Upload & Real-Time Progress (Week 2, Days 4-5 + Week 3, Day 1)

**Goal**: Users can upload SBOM files and see real-time enrichment progress

### 3.1 WebSocket Manager Service (Day 4)

**Files to Create**:
- `src/api/services/websocket_service.py`

**WebSocketManager Class**:
```python
class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        await self.send_message(session_id, {"event": "connected", "data": {"session_id": session_id}})

    async def send_progress(self, session_id: str, percentage: int, stage: str, message: str):
        await self.send_message(session_id, {
            "event": "progress",
            "data": {"percentage": percentage, "stage": stage, "message": message}
        })

    async def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
```

**Deliverable**: WebSocket connection management working

---

### 3.2 WebSocket Endpoint (Day 4)

**Files to Create**:
- `src/api/v1/endpoints/websocket.py`

**Endpoint**:
```python
@router.websocket("/ws/scans/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...)
):
    # Verify JWT
    payload = verify_jwt_token(token)
    user_id = payload["sub"]

    # Connect
    await websocket_manager.connect(session_id, websocket)

    # Keep connection alive
    try:
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong, cancel requests
    except WebSocketDisconnect:
        await websocket_manager.disconnect(session_id)
```

**Deliverable**: WebSocket endpoint functional

---

### 3.3 Async Enrichment Pipeline (Day 5)

**Files to Modify**:
- `src/api/v1/endpoints/scan.py` - Make async
- `src/api/services/enrichment.py` - Add progress callbacks

**Changes to /v1/scan/ingest**:
```python
@router.post("/v1/scan/ingest")
async def ingest_scan(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    # Validate file
    session_id = generate_session_id()

    # Upload to S3
    await upload_to_s3(file, session_id, current_user.org_id)

    # Create scan record
    await scan_repo.create_scan(session_id, file.filename, current_user.user_id)

    # Start async enrichment
    background_tasks.add_task(enrich_scan_with_progress, session_id, current_user.org_id)

    # Return immediately
    return {"session_id": session_id, "status": "processing"}
```

**Progress Integration**:
```python
async def enrich_scan_with_progress(session_id: str, org_id: str):
    await websocket_manager.send_progress(session_id, 10, "parsing", "Parsing SBOM...")
    components = await parse_sbom(file_content)

    await websocket_manager.send_progress(session_id, 30, "cve_mapping", "Mapping CVEs...")
    await map_cves(components)

    # ... (50%, 70%, 90%)

    await websocket_manager.send_message(session_id, {"event": "complete", "data": {"session_id": session_id}})
```

**Deliverable**: Async enrichment with WebSocket progress

---

### 3.4 Frontend Upload UI (Week 3, Day 1)

**Files to Create**:
- `frontend/app/(dashboard)/scans/upload/page.tsx`
- `frontend/lib/websocket.ts` - WebSocket hook

**Upload Component**:
```typescript
function UploadPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const { progress, connected } = useWebSocket(sessionId)

  async function handleUpload(file: File) {
    const formData = new FormData()
    formData.append('file', file)

    const result = await apiClient.post('/v1/scan/ingest', formData)
    setSessionId(result.session_id)
  }

  return (
    <>
      <FileUploadDropzone onUpload={handleUpload} />
      {sessionId && <ProgressBar value={progress} />}
    </>
  )
}
```

**Deliverable**: End-to-end SBOM upload with real-time progress

---

## Phase 4: Dashboard & Visualization (Week 3, Days 2-4)

### 4.1 Dashboard Aggregation Service (Day 2)

**Files to Create**:
- `src/api/services/dashboard_service.py`

**Functions**:
```python
async def get_scan_analysis(session_id: str, org_id: str) -> DashboardData:
    # Check cache
    metadata = await scan_repo.get_scan_metadata(session_id)
    if metadata and not is_expired(metadata):
        return metadata.aggregations

    # Recompute
    return await compute_aggregations(session_id)

async def compute_aggregations(session_id: str) -> dict:
    # Query scan_results, calculate:
    # - Risk score (CVSS + EPSS + KEV weighted)
    # - Severity breakdown
    # - Top CVEs, CWEs, ATT&CK techniques
    # - Compliance violations
    pass
```

**Deliverable**: Dashboard data API working

---

### 4.2 Scan Analysis Endpoint (Day 2)

**Files to Create**:
- `src/api/v1/endpoints/scans.py`

**Endpoints**:
```python
GET /v1/scans - List scans
GET /v1/scans/{session_id} - Get scan details
GET /v1/scans/{session_id}/analysis - Dashboard data
DELETE /v1/scans/{session_id} - Delete scan
```

**Deliverable**: Scan management API complete

---

### 4.3 Frontend Dashboard Components (Days 3-4)

**Files to Create**:
- `frontend/app/(dashboard)/scans/[id]/page.tsx`
- `frontend/components/dashboard/executive-summary.tsx`
- `frontend/components/dashboard/vulnerability-breakdown.tsx`
- `frontend/components/dashboard/component-inventory.tsx`

**Install Chart Library**:
```bash
npm install recharts
npm install @tanstack/react-table
```

**Deliverable**: Interactive dashboard UI

---

## Phase 5: Export & Polish (Week 4)

### 5.1 Export Service (Days 1-2)

**Files to Create**:
- `src/api/services/export_service.py`

**Dependencies**:
```
reportlab  # PDF generation
```

**Functions**:
```python
async def generate_pdf_report(session_id: str) -> bytes
async def generate_csv_export(session_id: str) -> str
async def generate_vex_document(session_id: str) -> dict  # Reuse existing VEX service
```

**Deliverable**: Export endpoints functional

---

### 5.2 Additional Features (Days 3-4)

**Tasks**:
- [ ] Organization management endpoints
- [ ] API token rotation endpoint
- [ ] User invitation (if in scope - clarify with user)
- [ ] Scan deletion
- [ ] Dashboard caching improvements

---

### 5.3 Testing & Bug Fixes (Day 5)

**Tasks**:
- [ ] End-to-end testing of all flows
- [ ] Performance testing (WebSocket load test)
- [ ] Security testing (OWASP ZAP scan)
- [ ] Bug fixes from testing

---

## Progress Tracking

### Completed Phases: 0/5
- [ ] Phase 1: Backend Authentication Foundation
- [ ] Phase 2: Frontend Authentication UI
- [ ] Phase 3: SBOM Upload & Real-Time Progress
- [ ] Phase 4: Dashboard & Visualization
- [ ] Phase 5: Export & Polish

### Current Sprint: Phase 1, Day 1
**Active Task**: Update backend dependencies

---

## Risk Mitigation

**Risk**: Large SBOM files cause timeout
**Mitigation**: Implemented in Phase 3 - email notification for >500 components

**Risk**: WebSocket scalability
**Mitigation**: Load testing in Phase 3, Redis pub/sub for horizontal scaling

**Risk**: Dashboard cache expiry performance
**Mitigation**: Async recomputation with stale data fallback

---

## Definition of Done (Stage 6 Exit Criteria)

- [ ] All 6 user stories (US-1 through US-6) implemented
- [ ] Unit test coverage > 80%
- [ ] Integration tests for critical flows (signup, upload, dashboard)
- [ ] API documentation updated (OpenAPI spec)
- [ ] No P0/P1 bugs outstanding
- [ ] Performance targets met (NFR-1.1 through NFR-1.5)
- [ ] Security review passed (OWASP Top 10 checklist)

---

## Next Steps

1. Start Phase 1, Task 1.1: Update backend dependencies
2. Test database connection
3. Create authentication models
4. Implement JWT security extensions

**Estimated Completion**: Week 4 (4 weeks total for all phases)
