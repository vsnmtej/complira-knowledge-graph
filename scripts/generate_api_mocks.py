#!/usr/bin/env python3
"""
Generate API mock responses for frontend testing.

Creates realistic mock data based on actual API response models.
Frontend can use these mocks for development and testing without a backend.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List


def generate_scan_ingest_response():
    """Generate mock response for POST /v1/scan/ingest"""
    return {
        "success": True,
        "data": {
            "scan_session_id": "19051940",
            "findings_count": 78,
            "components_count": 59,
            "status": "completed"
        },
        "metadata": {
            "cache_hit": False,
            "execution_time_ms": 1234.56
        }
    }


def generate_scan_session_response():
    """Generate mock response for GET /v1/scan/{session_id}"""
    return {
        "success": True,
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
            "project_id": None,
            "repository_id": None
        },
        "metadata": {
            "cache_hit": False,
            "execution_time_ms": 45.23
        }
    }


def generate_scan_findings_response():
    """Generate mock response for GET /v1/scan/{session_id}/findings"""
    findings = [
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
    ]

    return {
        "success": True,
        "data": findings,
        "metadata": {
            "cache_hit": False,
            "execution_time_ms": 12.34
        }
    }


def generate_scans_list_response():
    """Generate mock response for GET /v1/scans"""
    scans = [
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
            "project_id": None,
            "repository_id": None
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
            "project_id": None,
            "repository_id": None
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
            "project_id": None,
            "repository_id": None
        }
    ]

    return {
        "success": True,
        "data": scans,
        "metadata": {
            "cache_hit": False,
            "execution_time_ms": 23.45
        }
    }


def generate_error_responses():
    """Generate common error responses"""
    return {
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
    }


def main():
    """Generate all mock responses"""
    output_dir = Path("tests/fixtures/api_responses")
    output_dir.mkdir(parents=True, exist_ok=True)

    mocks = {
        "scan_ingest.json": generate_scan_ingest_response(),
        "scan_session.json": generate_scan_session_response(),
        "scan_findings.json": generate_scan_findings_response(),
        "scans_list.json": generate_scans_list_response(),
        "errors.json": generate_error_responses(),
    }

    for filename, data in mocks.items():
        filepath = output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ Generated {filepath}")

    # Also create TypeScript version for frontend
    frontend_mocks_dir = Path("frontend/src/__mocks__")
    frontend_mocks_dir.mkdir(parents=True, exist_ok=True)

    typescript_content = f"""// Auto-generated API mocks for frontend testing
// Generated: {datetime.now().isoformat()}

export const mockScanIngestResponse = {json.dumps(generate_scan_ingest_response(), indent=2)};

export const mockScanSessionResponse = {json.dumps(generate_scan_session_response(), indent=2)};

export const mockScanFindingsResponse = {json.dumps(generate_scan_findings_response(), indent=2)};

export const mockScansListResponse = {json.dumps(generate_scans_list_response(), indent=2)};

export const mockErrors = {json.dumps(generate_error_responses(), indent=2)};

// Export all mocks
export default {{
  scanIngest: mockScanIngestResponse,
  scanSession: mockScanSessionResponse,
  scanFindings: mockScanFindingsResponse,
  scansList: mockScansListResponse,
  errors: mockErrors,
}};
"""

    ts_file = frontend_mocks_dir / "api-responses.ts"
    with open(ts_file, 'w') as f:
        f.write(typescript_content)
    print(f"✅ Generated {ts_file}")

    print("\n✅ All API mocks generated successfully!")
    print(f"   Python fixtures: {output_dir}")
    print(f"   TypeScript mocks: {frontend_mocks_dir}")


if __name__ == "__main__":
    main()
