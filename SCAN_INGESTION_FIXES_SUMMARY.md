# Scan Ingestion Fixes & Test Coverage Summary

## Overview

Fixed multiple issues in the scan ingestion pipeline and added comprehensive test coverage using real FDA SBOM data.

## Issues Fixed

### 1. GHSA Vulnerability Identifier Support
**Problem**: Model validation rejected GHSA (GitHub Security Advisories) identifiers, only accepting CVE-* format.

**Fix**: Updated `src/complira_graph/models/scan.py:198-217`
- Expanded `validate_cve_id()` to accept multiple formats: CVE-*, GHSA-*, RUSTSEC-*, PYSEC-*, GO-*, GHSL-*
- All identifiers are normalized to uppercase

**Impact**: Can now ingest SBOMs with GitHub Security Advisories (common in npm, PyPI packages)

### 2. Enriched Severity Format Parsing
**Problem**: Parser only extracted severity from `ratings[]` array (standard CycloneDX format), missing direct `severity` field used by many tools.

**Fix**: Updated `src/api/parsers/cyclonedx.py:111-120, 148-157`
- Check for direct `severity` field first (enriched format)
- Fall back to `ratings[0].severity` (standard format)
- Applied to both component-level and root-level vulnerabilities

**Impact**: Correctly parses severity from tools like Syft, Grype, Trivy that use enriched format

### 3. Pydantic Model → Dictionary Conversion
**Problem**: `_store_findings()` returned Pydantic `ScanFinding` models, but edge creation code expected dictionaries with `.get()` method.

**Error**: `AttributeError: 'ScanFinding' object has no attribute 'get'`

**Fix**: Updated `src/api/services/scan.py:245`
```python
findings_created.append(finding.model_dump(by_alias=True))
```

**Impact**: Edge creation (`finding → CVE`, `component → finding`) now works correctly

## Test Coverage Added

### Unit Tests
**File**: `tests/unit/test_cyclonedx_parser.py`

- ✅ GHSA identifier validation
- ✅ CVE identifier validation
- ✅ Enriched severity format (direct field)
- ✅ Standard severity format (ratings array)
- ✅ Root component extraction (`metadata.component`)
- ✅ Dependency component extraction (`components[]`)
- ✅ Old tool format (`tools: []`) and new format (`tools: {components: []}`)
- ✅ Severity mapping (critical → CRITICAL, high → HIGH, etc.)
- ✅ Component without PURL (fallback to name@version)
- ✅ Empty SBOMs
- ✅ Metadata extraction

### Integration Tests
**File**: `tests/integration/test_scan_ingestion_api.py`

- ✅ FDA SBOM ingestion with GHSA vulnerabilities
- ✅ Parser extracts GHSA vulnerabilities correctly
- ✅ Parser extracts enriched severity correctly
- ✅ Parser extracts root + dependency components
- ✅ Model validation accepts GHSA/CVE/RUSTSEC/PYSEC/GO identifiers
- ✅ Model→dict conversion preserves fields and supports .get()
- ⏸️  End-to-end API test (skipped by default, requires live server)

### Verification Script
**File**: `test_scan_fixes.py`

Standalone test script (no pytest dependency) that verifies:
1. GHSA validation (model level)
2. Enriched severity parsing (parser level)
3. Model to dict conversion (service level)
4. FDA SBOM parsing with real data

**Run with**: `.venv/bin/python test_scan_fixes.py`

## Test Fixtures

**Location**: `tests/fixtures/sboms/`

| File | Format | Source | Description |
|------|--------|--------|-------------|
| `fda_sbom.json` | CycloneDX 1.6 | FDA evidence | 59 components, 78 vulnerabilities (73 CVE + 5 GHSA) |
| `sarif_semgrep.json` | SARIF 2.1.0 | FDA evidence | Semgrep code scanning results |
| `spdx_example.json` | SPDX | FDA evidence | Example SPDX SBOM |

## Verification Results

```
✅ PASS: GHSA Validation
✅ PASS: Enriched Severity Parsing
✅ PASS: Model→Dict Conversion
✅ PASS: FDA SBOM Parsing

Total: 4/4 tests passed

FDA SBOM Parsing Results:
- Components: 59 (1 root + 58 dependencies)
- Findings: 78 vulnerabilities
- CVE vulnerabilities: 73
- GHSA vulnerabilities: 5
- Severity distribution:
  - CRITICAL: 9
  - HIGH: 39
  - MEDIUM: 26
  - LOW: 4
  - UNKNOWN: 0 ✓
```

## Files Modified

### Core Fixes
1. `src/complira_graph/models/scan.py` - GHSA validation
2. `src/api/parsers/cyclonedx.py` - Enriched severity parsing
3. `src/api/services/scan.py` - Model→dict conversion

### Tests Added
1. `tests/unit/test_cyclonedx_parser.py` - Parser unit tests
2. `tests/integration/test_scan_ingestion_api.py` - API integration tests
3. `test_scan_fixes.py` - Standalone verification script
4. `tests/fixtures/sboms/` - Real SBOM test data

## CI/CD Integration

### GitHub Actions Workflow
**File**: `.github/workflows/test.yml`

Comprehensive test pipeline runs on every push/PR to `main` or `develop`:

1. **Unit Tests Job**
   - Runs all tests in `tests/unit/`
   - Coverage reporting to Codecov
   - Fails fast on 5th failure

2. **Integration Tests Job**
   - Spins up ArangoDB + Redis services
   - Runs all tests in `tests/integration/`
   - Tests actual database operations

3. **Parser Tests Job**
   - Runs `test_scan_fixes.py` verification script
   - Tests CycloneDX parser with real FDA SBOM (59 components, 78 vulns)
   - Validates GHSA + CVE parsing

4. **Code Quality Job**
   - Runs `ruff` linter
   - Runs `mypy` type checker

5. **Test Summary Job**
   - Aggregates results from all jobs
   - Fails build if any job fails

### Makefile Commands

Quick test commands for local development:

```bash
make test              # Run unit tests
make test-unit         # Unit tests only
make test-integration  # Integration tests only (requires DB)
make test-parser       # Run parser verification script
make test-all          # Run everything
make test-cov          # Tests with coverage report (HTML output)
make test-scan         # Run scan ingestion tests specifically
make ci-test           # Simulate CI pipeline (fast)
make ci-full           # Simulate full CI pipeline

make lint              # Run ruff linter
make format            # Auto-format code
make typecheck         # Run mypy type checker
make quality           # Run all quality checks
```

### Local Development Workflow

1. **Install dependencies**:
   ```bash
   make install
   ```

2. **Run tests before commit**:
   ```bash
   make test-scan  # Test scan ingestion specifically
   # or
   make ci-test    # Run what CI will run
   ```

3. **Check code quality**:
   ```bash
   make quality
   ```

4. **View coverage**:
   ```bash
   make test-cov
   open htmlcov/index.html
   ```

## Next Steps

### For Users
1. ✅ Server auto-reloaded with fixes (if using `--reload` flag)
2. ✅ Ready to upload SBOMs with GHSA identifiers
3. ✅ Can use tools that output enriched severity format
4. ✅ CI/CD pipeline validates all changes

### For Developers
**Run tests locally:**
```bash
make test-scan                                    # Quick scan tests
pytest tests/unit/test_cyclonedx_parser.py -v    # Parser unit tests
pytest tests/integration/test_scan_ingestion_api.py -v  # API tests
python test_scan_fixes.py                        # Standalone verification
```

**Before pushing:**
```bash
make ci-test   # Run what CI will run
make quality   # Check code quality
```

### Recommended Future Work
- [ ] Add SARIF parser tests (similar structure to CycloneDX tests)
- [ ] Add SPDX parser support (fixtures already available)
- [ ] Add end-to-end API test with live database
- [ ] Add performance tests for large SBOMs (1000+ components)
- [ ] Add pre-commit hooks for automatic test execution
- [ ] Set up branch protection rules requiring CI to pass

## Related Documentation

- CycloneDX Specification: https://cyclonedx.org/docs/
- GHSA Format: https://github.com/advisories
- SARIF Specification: https://sarifweb.azurewebsites.net/
- SPDX Specification: https://spdx.github.io/spdx-spec/

## Commit Message

```
fix(scan): Add GHSA support, enriched severity parsing, model conversion

- Support GHSA/RUSTSEC/PYSEC/GO vulnerability identifiers
- Parse enriched severity format (direct field + ratings array fallback)
- Fix Pydantic model→dict conversion for edge creation
- Add comprehensive test coverage with real FDA SBOM data

Fixes:
- GHSA identifiers now accepted (previously rejected as invalid CVE)
- Enriched severity format parsed correctly (no more UNKNOWN severities)
- Edge creation works (finding→CVE, component→finding)

Tests:
- 11 unit tests for CycloneDX parser
- 6 integration tests for API contracts
- Standalone verification script
- Real SBOM fixtures from FDA cybersecurity docs (59 components, 78 vulns)

Verified with FDA SBOM: 73 CVE + 5 GHSA vulnerabilities, all severities parsed
```

## Breaking Changes

None - all changes are backward compatible. Existing CVE-only SBOMs continue to work.

## Performance Impact

None - additional validation checks are O(1) string prefix checks.
