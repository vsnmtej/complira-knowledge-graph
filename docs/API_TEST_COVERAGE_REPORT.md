# API Test Coverage Report

**Generated**: 2026-03-17
**Total API Endpoints**: 52
**Endpoints with Comprehensive Tests**: 5 (9.6%)
**Endpoints Needing Tests**: 47 (90.4%)

---

## Summary

Currently, only the **scan ingestion endpoints** have comprehensive test coverage (unit + integration + contract + mocks). The remaining 47 endpoints across 11 endpoint files lack dedicated API tests.

### Coverage Legend
- ✅ **Full Coverage**: Unit + Integration + Contract + Mocks + Docs
- 🟡 **Partial Coverage**: Some tests exist but incomplete
- ❌ **No Coverage**: No dedicated API tests

---

## Endpoint Coverage by Module

### 1. Scan Endpoints (`scan.py`) - ✅ FULL COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/scan/ingest` | ✅ | Unit (11) + Integration (6) + Contract (8) + Mocks |
| GET | `/v1/scan/{session_id}` | ✅ | Integration + Contract + Mocks |
| GET | `/v1/scan/{session_id}/findings` | ✅ | Integration + Contract + Mocks |
| GET | `/v1/scans` | ✅ | Integration + Contract + Mocks |
| POST | `/v1/scan/{session_id}/vex` | 🟡 | Partial (model tests only) |
| POST | `/v1/scan/{session_id}/cpe-match` | ❌ | None |

**Test Files**:
- `tests/unit/test_cyclonedx_parser.py` (11 tests)
- `tests/integration/test_scan_ingestion_api.py` (6 tests)
- `tests/contract/test_api_contract.py` (8 tests)
- `tests/fixtures/api_responses/scan_*.json` (4 mock files)
- `frontend/src/__mocks__/api-responses.ts`

---

### 2. Auth Endpoints (`auth.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/auth/signup` | ❌ | None |
| POST | `/v1/auth/login` | ❌ | None |
| POST | `/v1/auth/verify-email` | ❌ | None |
| POST | `/v1/auth/forgot-password` | ❌ | None |
| POST | `/v1/auth/reset-password` | ❌ | None |
| POST | `/v1/auth/refresh` | ❌ | None |
| GET | `/v1/auth/me` | ❌ | None |

**Notes**:
- `tests/unit/test_phase1_authentication.py` exists but tests model/security functions, not API endpoints
- No integration tests for auth flow
- No mock responses for frontend

---

### 3. Token Management Endpoints (`tokens.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/tokens` | ❌ | None |
| GET | `/v1/tokens` | ❌ | None |
| GET | `/v1/tokens/{token_id}` | ❌ | None |
| PATCH | `/v1/tokens/{token_id}` | ❌ | None |
| POST | `/v1/tokens/{token_id}/rotate` | ❌ | None |
| POST | `/v1/tokens/{token_id}/revoke` | ❌ | None |
| DELETE | `/v1/tokens/{token_id}` | ❌ | None |

**Notes**: Critical endpoints for API key management - high priority for testing.

---

### 4. Repository Endpoints (`repositories.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/repositories` | ❌ | None |
| GET | `/v1/repositories` | ❌ | None |
| GET | `/v1/repositories/{repository_id}` | ❌ | None |
| PUT | `/v1/repositories/{repository_id}` | ❌ | None |
| DELETE | `/v1/repositories/{repository_id}` | ❌ | None |
| GET | `/v1/repositories/{repository_id}/summary` | ❌ | None |

**Notes**: Core functionality for linking GitHub/GitLab repos - high priority.

---

### 5. Project Endpoints (`projects.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/projects` | ❌ | None |
| GET | `/v1/projects` | ❌ | None |
| GET | `/v1/projects/{project_id}` | ❌ | None |
| PUT | `/v1/projects/{project_id}` | ❌ | None |
| DELETE | `/v1/projects/{project_id}` | ❌ | None |
| GET | `/v1/projects/{project_id}/summary` | ❌ | None |

---

### 6. VEX Endpoints (`vex.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/vex` | ❌ | None |
| GET | `/v1/vex` | ❌ | None |
| GET | `/v1/vex/{vex_id}` | ❌ | None |
| PUT | `/v1/vex/{vex_id}` | ❌ | None |
| PATCH | `/v1/vex/{vex_id}/vulnerability/{cve_id}` | ❌ | None |
| DELETE | `/v1/vex/{vex_id}` | ❌ | None |

**Notes**: VEX (Vulnerability Exploitability eXchange) - important for compliance workflows.

---

### 7. Account Endpoints (`account.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/account/api-keys` | ❌ | None |
| GET | `/v1/account/api-keys` | ❌ | None |
| DELETE | `/v1/account/api-keys/{key_id}` | ❌ | None |

---

### 8. Reference Data Endpoints (`reference.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| GET | `/v1/reference/cve/{cve_id}` | ❌ | None |
| GET | `/v1/reference/enrich` | ❌ | None |
| GET | `/v1/reference/cwe/{cwe_id}` | ❌ | None |
| GET | `/v1/reference/controls/{cve_id}` | ❌ | None |

**Notes**: Read-only endpoints - good candidates for simple contract tests.

---

### 9. Enrichment Endpoints (`enrichment.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/enrichment/enrich` | ❌ | None |
| GET | `/v1/enrichment/status` | ❌ | None |

---

### 10. CVE Enrichment Endpoint (`enrich.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| POST | `/v1/enrich/enrich` | ❌ | None |

**Notes**: Duplicate functionality with `enrichment.py` - needs consolidation.

---

### 11. Meta Endpoints (`meta.py`) - ❌ NO COVERAGE

| Method | Endpoint | Status | Tests |
|--------|----------|--------|-------|
| GET | `/v1/meta/coverage` | ❌ | None |
| GET | `/v1/meta/stats` | ❌ | None |

**Notes**: System health/stats endpoints - useful for monitoring.

---

## Test Infrastructure Status

### ✅ What We Have

1. **Test Framework**: pytest with fixtures, mocking, async support
2. **CI/CD Pipeline**: GitHub Actions with 5 jobs (`.github/workflows/test.yml`)
3. **Mock Generation**: `scripts/generate_api_mocks.py`
4. **Contract Testing**: `tests/contract/test_api_contract.py`
5. **Database Fixtures**: ArangoDB + Redis docker-compose setup
6. **Code Quality**: ruff (linter), mypy (type checker)
7. **Coverage Tracking**: pytest-cov with HTML/XML reports
8. **Makefile Commands**: 15+ quick test commands

### ❌ What We're Missing

1. **API endpoint integration tests** for 47 endpoints
2. **Mock responses** for frontend development (47 endpoints)
3. **Contract tests** validating response schemas (47 endpoints)
4. **Error scenario tests** (401, 403, 404, 422, 500)
5. **OpenAPI/Swagger spec** auto-generated from code
6. **End-to-end tests** (Playwright/Cypress)
7. **Load/performance tests** for API endpoints

---

## Priority Recommendations

### P0 - Critical (Authentication & Core Security)
**Why**: Security vulnerabilities, user can't access system
- [ ] Auth endpoints (7 endpoints) - signup, login, token refresh
- [ ] Token management endpoints (7 endpoints) - API key lifecycle
- [ ] Account endpoints (3 endpoints) - API key management

**Estimated effort**: 2-3 days

### P1 - High (Core User Features)
**Why**: Primary user workflows, high usage
- [ ] Repository endpoints (6 endpoints) - GitHub/GitLab integration
- [ ] Project endpoints (6 endpoints) - Project management
- [ ] VEX endpoints (6 endpoints) - Compliance workflows

**Estimated effort**: 3-4 days

### P2 - Medium (Reference Data)
**Why**: Read-only, less critical, but important for enrichment
- [ ] Reference endpoints (4 endpoints) - CVE/CWE/controls lookup
- [ ] Enrichment endpoints (3 endpoints) - CVE enrichment
- [ ] Scan VEX/CPE endpoints (2 endpoints) - Additional scan features

**Estimated effort**: 2 days

### P3 - Low (System Metadata)
**Why**: Informational only, low impact if broken
- [ ] Meta endpoints (2 endpoints) - Coverage/stats

**Estimated effort**: 0.5 day

---

## Recommended Test Structure

Based on successful scan ingestion tests, create similar structure for each endpoint module:

```
tests/
├── unit/
│   ├── test_auth_logic.py              # Business logic tests
│   ├── test_token_validation.py
│   └── test_repository_parsing.py
├── integration/
│   ├── test_auth_endpoints.py          # Full API integration tests
│   ├── test_token_endpoints.py
│   ├── test_repository_endpoints.py
│   └── test_project_endpoints.py
├── contract/
│   ├── test_auth_contract.py           # Schema validation
│   ├── test_token_contract.py
│   └── test_repository_contract.py
└── fixtures/
    └── api_responses/
        ├── auth_*.json                  # Mock responses
        ├── tokens_*.json
        └── repositories_*.json
```

---

## Next Steps

### Option A: Comprehensive Approach (Recommended)
1. **Create test templates** based on scan ingestion pattern
2. **Generate mock responses** for all 47 endpoints
3. **Write contract tests** to validate schemas
4. **Implement integration tests** following P0 → P1 → P2 → P3
5. **Update frontend mocks** as endpoints are tested
6. **Document coverage** in this report

### Option B: Incremental Approach
1. **Start with P0 (auth/tokens)** - critical for security
2. **Add contract tests** as endpoints are completed
3. **Generate mocks** progressively
4. **Expand to P1/P2** based on user feedback

### Option C: Frontend-First Approach
1. **Generate all mock responses** immediately
2. **Create TypeScript mocks** for frontend development
3. **Add contract tests** to prevent mock drift
4. **Backfill integration tests** as needed

---

## Automation Opportunities

### Auto-Generate Test Skeletons
Create script to auto-generate test files from endpoint definitions:

```bash
# Generate test skeletons for all endpoints
python scripts/generate_api_tests.py --all

# Generate for specific module
python scripts/generate_api_tests.py --module auth
```

### Auto-Generate Mocks from Pydantic Models
Extend `scripts/generate_api_mocks.py` to cover all endpoints:

```bash
# Generate mocks for all endpoints
python scripts/generate_api_mocks.py --all-endpoints

# Validate existing mocks
python scripts/generate_api_mocks.py --validate
```

### OpenAPI Spec Generation
Generate OpenAPI 3.0 spec from FastAPI:

```bash
# Export OpenAPI spec
python scripts/export_openapi_spec.py > docs/openapi.yaml

# Generate TypeScript types from OpenAPI
npm run generate-types
```

---

## Test Coverage Goals

| Metric | Current | Target (3 months) | Target (6 months) |
|--------|---------|-------------------|-------------------|
| Endpoint coverage | 9.6% (5/52) | 60% (31/52) | 100% (52/52) |
| Unit test coverage | 45% | 70% | 85% |
| Integration tests | 6 endpoints | 25 endpoints | 52 endpoints |
| Contract tests | 4 endpoints | 25 endpoints | 52 endpoints |
| Mock responses | 4 endpoints | 25 endpoints | 52 endpoints |

---

## Questions?

- **Backend testing**: See `tests/` directory + `Makefile`
- **Frontend mocks**: See `docs/FRONTEND_API_MOCKS.md`
- **CI/CD**: See `.github/workflows/test.yml`
- **Mock generation**: Run `python scripts/generate_api_mocks.py --help`
- **This report**: `docs/API_TEST_COVERAGE_REPORT.md`
