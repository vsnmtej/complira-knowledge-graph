# Frontend API Mocks & Contract Testing

Guide for frontend developers on using API mocks for development and testing without running the backend.

## Overview

API mocks provide realistic response data that matches the production API contract. Use them for:
- **Local development** - Build UI without running backend server
- **Unit testing** - Test components in isolation
- **Integration testing** - Test API integration without real network calls
- **Contract testing** - Ensure frontend code handles API responses correctly

## Mock Data Location

```
tests/fixtures/api_responses/     # JSON fixtures (Python/backend tests)
frontend/src/__mocks__/            # TypeScript mocks (frontend usage)
```

## Available API Mocks

### 1. Scan Ingestion (`POST /v1/scan/ingest`)

**Mock file**: `frontend/src/__mocks__/api-responses.ts`

```typescript
import { mockScanIngestResponse } from './__mocks__/api-responses';

// Response structure:
{
  "success": true,
  "data": {
    "scan_session_id": "19051940",
    "findings_count": 78,
    "components_count": 59,
    "status": "completed"
  },
  "metadata": {
    "cache_hit": false,
    "execution_time_ms": 1234.56
  }
}
```

### 2. Scan Session Details (`GET /v1/scan/{session_id}`)

```typescript
import { mockScanSessionResponse } from './__mocks__/api-responses';

// Response includes:
// - session_id, tool_name, tool_version
// - scan_type, scan_timestamp, status
// - findings_count, components_count
// - created_at, updated_at, metadata
```

### 3. Scan Findings (`GET /v1/scan/{session_id}/findings`)

```typescript
import { mockScanFindingsResponse } from './__mocks__/api-responses';

// Returns array of findings:
// - finding_id, cve_id, severity
// - description, location, tool_name
// - created_at

// Includes diverse test data:
// - 2 CRITICAL vulnerabilities
// - 3 HIGH vulnerabilities
// - 2 MEDIUM vulnerabilities
// - 1 LOW vulnerability
// - Includes GHSA-* and CVE-* identifiers
```

### 4. Scans List (`GET /v1/scans`)

```typescript
import { mockScansListResponse } from './__mocks__/api-responses';

// Returns array of scan sessions
// - Multiple scan types: SBOM, SAST, container
// - Different tools: syft, semgrep, trivy
```

### 5. Error Responses

```typescript
import { mockErrors } from './__mocks__/api-responses';

// Available error scenarios:
// - 401_unauthorized: Missing/invalid API key
// - 404_scan_not_found: Scan doesn't exist
// - 400_validation_error: Invalid request data
// - 500_internal_error: Server error
```

## Usage Examples

### Example 1: Mocking API in Component Tests (React + Jest)

```typescript
// ScanList.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { mockScansListResponse } from './__mocks__/api-responses';
import ScanList from './ScanList';

// Mock fetch globally
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve(mockScansListResponse),
  })
) as jest.Mock;

test('displays list of scans', async () => {
  render(<ScanList />);

  await waitFor(() => {
    expect(screen.getByText('syft')).toBeInTheDocument();
    expect(screen.getByText('78 findings')).toBeInTheDocument();
  });
});
```

### Example 2: MSW (Mock Service Worker) for API Mocking

```typescript
// mocks/handlers.ts
import { rest } from 'msw';
import apiMocks from '../__mocks__/api-responses';

export const handlers = [
  rest.get('/v1/scans', (req, res, ctx) => {
    return res(ctx.status(200), ctx.json(apiMocks.scansList));
  }),

  rest.get('/v1/scan/:sessionId', (req, res, ctx) => {
    return res(ctx.status(200), ctx.json(apiMocks.scanSession));
  }),

  rest.get('/v1/scan/:sessionId/findings', (req, res, ctx) => {
    return res(ctx.status(200), ctx.json(apiMocks.scanFindings));
  }),

  rest.post('/v1/scan/ingest', (req, res, ctx) => {
    return res(ctx.status(200), ctx.json(apiMocks.scanIngest));
  }),
];
```

```typescript
// mocks/server.ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
```

```typescript
// setupTests.ts
import { server } from './mocks/server';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

### Example 3: Development with Mock API

```typescript
// hooks/useScanData.ts
import { useQuery } from '@tanstack/react-query';
import apiMocks from '../__mocks__/api-responses';

const USE_MOCK_API = process.env.REACT_APP_USE_MOCK_API === 'true';

export function useScanData(sessionId: string) {
  return useQuery({
    queryKey: ['scan', sessionId],
    queryFn: async () => {
      // Use mock data in development if backend isn't running
      if (USE_MOCK_API) {
        return new Promise((resolve) => {
          setTimeout(() => resolve(apiMocks.scanSession), 500);
        });
      }

      // Real API call
      const response = await fetch(`/v1/scan/${sessionId}`);
      return response.json();
    },
  });
}
```

### Example 4: Storybook Stories with Mock Data

```typescript
// ScanFindingCard.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { mockScanFindingsResponse } from '../__mocks__/api-responses';
import ScanFindingCard from './ScanFindingCard';

const meta: Meta<typeof ScanFindingCard> = {
  title: 'Components/ScanFindingCard',
  component: ScanFindingCard,
};

export default meta;
type Story = StoryObj<typeof ScanFindingCard>;

export const CriticalFinding: Story = {
  args: {
    finding: mockScanFindingsResponse.data[0], // CRITICAL severity
  },
};

export const HighFinding: Story = {
  args: {
    finding: mockScanFindingsResponse.data[2], // HIGH severity
  },
};

export const GHSAVulnerability: Story = {
  args: {
    finding: mockScanFindingsResponse.data.find(
      (f) => f.cve_id?.startsWith('GHSA-')
    ),
  },
};
```

## Updating Mock Data

When API responses change, regenerate mocks:

```bash
# From project root
python scripts/generate_api_mocks.py

# Or using make
make generate-mocks
```

This will:
1. Update `tests/fixtures/api_responses/*.json` (Python tests)
2. Update `frontend/src/__mocks__/api-responses.ts` (frontend tests)

## Contract Testing

Ensure frontend handles API responses correctly:

```bash
# Run contract tests (validates mocks match API schema)
pytest tests/contract/test_api_contract.py -v

# Run in CI/CD
make test-contract
```

Contract tests verify:
- ✅ Mock responses match Pydantic models
- ✅ All required fields present
- ✅ Field types correct
- ✅ Severity levels valid
- ✅ Vulnerability ID formats valid (CVE-*, GHSA-*)
- ✅ Metadata structure consistent

## TypeScript Types

Generate TypeScript types from API responses:

```bash
# Auto-generate types from OpenAPI schema
npm run generate-types

# Manual type definitions in:
frontend/src/types/api.ts
```

Example type definitions:

```typescript
export interface APIResponse<T> {
  success: boolean;
  data: T;
  metadata: {
    cache_hit: boolean;
    execution_time_ms: number;
  };
}

export interface ScanIngestResponse {
  scan_session_id: string;
  findings_count: number;
  components_count: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
}

export interface ScanFinding {
  finding_id: string;
  cve_id: string | null;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO' | 'UNKNOWN';
  description: string;
  location: string;
  tool_name: string;
  created_at: string;
}
```

## Environment Variables

```bash
# .env.local (frontend)
REACT_APP_USE_MOCK_API=true          # Use mocks instead of real API
REACT_APP_API_BASE_URL=http://localhost:8000/v1
```

## Best Practices

### 1. Keep Mocks Realistic
- Use real data from production-like scenarios
- Include edge cases (e.g., empty lists, null values)
- Match actual API response structure exactly

### 2. Sync with Backend Changes
- Regenerate mocks when API changes
- Run contract tests in CI/CD
- Version mock data with API versions

### 3. Test Error Scenarios
```typescript
// Test how UI handles errors
test('handles 404 error gracefully', async () => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: false,
      status: 404,
      json: () => Promise.resolve(mockErrors['404_scan_not_found']),
    })
  );

  render(<ScanDetails sessionId="nonexistent" />);

  await waitFor(() => {
    expect(screen.getByText(/not found/i)).toBeInTheDocument();
  });
});
```

### 4. Document Mock Scenarios
```typescript
/**
 * Mock scenarios available:
 * - mockScanIngestResponse: Successful SBOM upload (78 findings, 59 components)
 * - mockScanSessionResponse: Completed scan session
 * - mockScanFindingsResponse: Mixed severity findings (includes GHSA IDs)
 * - mockScansListResponse: Multiple scan types and tools
 * - mockErrors: Common error responses
 */
```

## CI/CD Integration

Contract tests run automatically on every push:

```yaml
# .github/workflows/test.yml
- name: Run contract tests
  run: pytest tests/contract/ -v

- name: Validate API mocks
  run: python scripts/generate_api_mocks.py --validate
```

## Troubleshooting

### Mock data doesn't match actual API
**Solution**: Regenerate mocks with latest API responses:
```bash
python scripts/generate_api_mocks.py
```

### TypeScript type errors with mock data
**Solution**: Ensure types match API response structure:
```typescript
// Update types in frontend/src/types/api.ts
```

### Frontend test failing with real API call
**Solution**: Verify MSW handlers are set up correctly:
```typescript
// Check setupTests.ts has server.listen()
```

## Resources

- [MSW Documentation](https://mswjs.io/)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
- [Storybook](https://storybook.js.org/)
- [Pydantic Models](../src/api/models/responses/)
