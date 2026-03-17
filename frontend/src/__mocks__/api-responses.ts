// Auto-generated API mocks for frontend testing
// Generated: 2026-03-17T07:30:59.659084

export const mockScanIngestResponse = {
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
};

export const mockScanSessionResponse = {
  "success": true,
  "data": {
    "session_id": "19051940",
    "tool_name": "syft",
    "tool_version": "v1.31.0",
    "scan_type": "sbom",
    "scan_timestamp": "2025-01-15T10:30:00Z",
    "status": "completed",
    "findings_count": 78,
    "components_count": 59,
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:32:15Z",
    "metadata": {
      "repository": "fda-cybersecurity-docs",
      "branch": "main",
      "bom_format": "CycloneDX",
      "spec_version": "1.6"
    },
    "project_id": null,
    "repository_id": null
  },
  "metadata": {
    "cache_hit": false,
    "execution_time_ms": 45.23
  }
};

export const mockScanFindingsResponse = {
  "success": true,
  "data": [
    {
      "finding_id": "19051941",
      "cve_id": "CVE-2024-27351",
      "severity": "CRITICAL",
      "description": "Django has a potential regular expression denial-of-service in django.utils.text.Truncator.words()",
      "location": "pkg:pypi/django@5.0",
      "tool_name": "grype",
      "created_at": "2025-01-15T10:31:00Z"
    },
    {
      "finding_id": "19051942",
      "cve_id": "CVE-2024-38875",
      "severity": "CRITICAL",
      "description": "Denial of service in Django MIME type parser",
      "location": "pkg:pypi/django@5.0",
      "tool_name": "grype",
      "created_at": "2025-01-15T10:31:00Z"
    },
    {
      "finding_id": "19051943",
      "cve_id": "GHSA-v8gr-m533-ghj9",
      "severity": "HIGH",
      "description": "Django vulnerable to SQL injection via QuerySet.values() on models with boolean field",
      "location": "pkg:pypi/django@5.0",
      "tool_name": "grype",
      "created_at": "2025-01-15T10:31:00Z"
    },
    {
      "finding_id": "19051944",
      "cve_id": "CVE-2024-45230",
      "severity": "HIGH",
      "description": "Django vulnerable to denial-of-service attack via certain inputs with a very large number of brackets",
      "location": "pkg:pypi/django@5.0",
      "tool_name": "grype",
      "created_at": "2025-01-15T10:31:00Z"
    },
    {
      "finding_id": "19051945",
      "cve_id": "CVE-2024-6345",
      "severity": "HIGH",
      "description": "pypa/setuptools vulnerable to Command Injection via package URL",
      "location": "pkg:pypi/setuptools@70.1.1",
      "tool_name": "grype",
      "created_at": "2025-01-15T10:31:00Z"
    },
    {
      "finding_id": "19051946",
      "cve_id": "CVE-2023-40577",
      "severity": "MEDIUM",
      "description": "Python bindings for XZ/LZMA backport are vulnerable to RCE",
      "location": "pkg:pypi/backports-lzma@0.0.14",
      "tool_name": "grype",
      "created_at": "2025-01-15T10:31:00Z"
    },
    {
      "finding_id": "19051947",
      "cve_id": "CVE-2024-11168",
      "severity": "MEDIUM",
      "description": "PyYAML unsafe deserialization of untrusted data",
      "location": "pkg:pypi/pyyaml@6.0.2",
      "tool_name": "grype",
      "created_at": "2025-01-15T10:31:00Z"
    },
    {
      "finding_id": "19051948",
      "cve_id": "CVE-2024-3651",
      "severity": "LOW",
      "description": "Idna package potential denial of service via resource consumption",
      "location": "pkg:pypi/idna@3.7",
      "tool_name": "grype",
      "created_at": "2025-01-15T10:31:00Z"
    }
  ],
  "metadata": {
    "cache_hit": false,
    "execution_time_ms": 12.34
  }
};

export const mockScansListResponse = {
  "success": true,
  "data": [
    {
      "session_id": "19051940",
      "tool_name": "syft",
      "tool_version": "v1.31.0",
      "scan_type": "sbom",
      "scan_timestamp": "2025-01-15T10:30:00Z",
      "status": "completed",
      "findings_count": 78,
      "components_count": 59,
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:32:15Z",
      "metadata": {
        "repository": "fda-cybersecurity-docs",
        "branch": "main"
      },
      "project_id": null,
      "repository_id": null
    },
    {
      "session_id": "19051939",
      "tool_name": "semgrep",
      "tool_version": "1.45.0",
      "scan_type": "sast",
      "scan_timestamp": "2025-01-14T15:20:00Z",
      "status": "completed",
      "findings_count": 12,
      "components_count": 0,
      "created_at": "2025-01-14T15:20:00Z",
      "updated_at": "2025-01-14T15:21:30Z",
      "metadata": {
        "repository": "fda-cybersecurity-docs",
        "branch": "main"
      },
      "project_id": null,
      "repository_id": null
    },
    {
      "session_id": "19051938",
      "tool_name": "trivy",
      "tool_version": "0.48.0",
      "scan_type": "container",
      "scan_timestamp": "2025-01-13T09:15:00Z",
      "status": "completed",
      "findings_count": 245,
      "components_count": 152,
      "created_at": "2025-01-13T09:15:00Z",
      "updated_at": "2025-01-13T09:18:45Z",
      "metadata": {
        "image": "python:3.11-slim",
        "digest": "sha256:abc123..."
      },
      "project_id": null,
      "repository_id": null
    }
  ],
  "metadata": {
    "cache_hit": false,
    "execution_time_ms": 23.45
  }
};

export const mockErrors = {
  "401_unauthorized": {
    "detail": "Invalid or missing API key"
  },
  "404_scan_not_found": {
    "detail": "Scan session not found: 19051940"
  },
  "400_validation_error": {
    "detail": "cve_id must start with one of ['CVE-', 'GHSA-', 'RUSTSEC-', 'PYSEC-', 'GO-', 'GHSL-'] if provided"
  },
  "500_internal_error": {
    "detail": "Internal server error during scan ingestion"
  }
};

// Export all mocks
const allMocks = {
  scanIngest: mockScanIngestResponse,
  scanSession: mockScanSessionResponse,
  scanFindings: mockScanFindingsResponse,
  scansList: mockScansListResponse,
  errors: mockErrors,
};
export default allMocks;
