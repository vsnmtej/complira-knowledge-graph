#!/usr/bin/env python3
"""
Test script for local API development.

Usage:
    python scripts/test_api_local.py [--base-url http://localhost:8000]

Tests:
- Health check
- Reference API endpoints (no auth)
- Scan ingestion API (requires API key)
"""

import sys
import argparse
import json
from typing import Optional
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def test_health(base_url: str) -> bool:
    """Test health check endpoint."""
    console.print("\n[bold blue]Testing Health Check[/bold blue]")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        response.raise_for_status()
        data = response.json()

        console.print(f"✅ Health check: [green]{data['status']}[/green]")
        console.print(f"   Version: {data['version']}")
        return True
    except Exception as e:
        console.print(f"❌ Health check failed: {e}")
        return False


def test_reference_cve(base_url: str, cve_id: str = "CVE-2024-21413") -> bool:
    """Test reference CVE endpoint."""
    console.print(f"\n[bold blue]Testing Reference API: CVE {cve_id}[/bold blue]")
    try:
        response = requests.get(
            f"{base_url}/v1/reference/cve/{cve_id}",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if not data.get('success'):
            console.print(f"❌ API returned success=false: {data.get('error')}")
            return False

        cve = data['data']

        # Display results
        table = Table(title=f"CVE Enrichment: {cve_id}")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("CVE ID", cve.get('cve_id', 'N/A'))
        table.add_row("CVSS Score", str(cve.get('cvss_score', 'N/A')))
        table.add_row("Severity", cve.get('severity', 'N/A'))
        table.add_row("EPSS Score", str(cve.get('epss', {}).get('score', 'N/A')))
        table.add_row("In KEV Catalog", "✅ Yes" if cve.get('kev', {}).get('in_kev') else "❌ No")
        table.add_row("Weaknesses (CWE)", str(len(cve.get('weaknesses', []))))
        table.add_row("ATT&CK Techniques", str(len(cve.get('attack_techniques', []))))
        table.add_row("NIST Controls", str(len(cve.get('nist_controls', []))))
        table.add_row("Regulatory Reqs", str(len(cve.get('regulatory_requirements', []))))
        table.add_row("D3FEND Defenses", str(len(cve.get('d3fend_defenses', []))))
        table.add_row("Threat Groups", str(len(cve.get('threat_groups', []))))
        table.add_row("Exploits", str(len(cve.get('exploits', []))))

        console.print(table)
        console.print("✅ Reference CVE API working correctly")
        return True

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            console.print(f"❌ CVE not found: {cve_id}")
            console.print("   This might mean your database is not seeded yet.")
            console.print("   Run: complira seed --skip-llm")
        else:
            console.print(f"❌ HTTP Error: {e}")
        return False
    except Exception as e:
        console.print(f"❌ Reference CVE test failed: {e}")
        return False


def test_reference_enrich(base_url: str) -> bool:
    """Test batch enrichment endpoint."""
    console.print("\n[bold blue]Testing Batch Enrichment[/bold blue]")
    cve_ids = "CVE-2024-21413,CVE-2023-44487"

    try:
        response = requests.get(
            f"{base_url}/v1/reference/enrich",
            params={"cve_ids": cve_ids},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if not data.get('success'):
            console.print(f"❌ API returned success=false: {data.get('error')}")
            return False

        results = data['data']
        console.print(f"✅ Enriched {len(results)} CVEs")

        for cve in results:
            if 'error' not in cve:
                console.print(f"   • {cve['cve_id']}: CVSS={cve.get('cvss_score', 'N/A')}, "
                            f"EPSS={cve.get('epss', {}).get('score', 'N/A')}")
            else:
                console.print(f"   • {cve['cve_id']}: {cve['error']}")

        return True

    except Exception as e:
        console.print(f"❌ Batch enrichment test failed: {e}")
        return False


def test_reference_cwe(base_url: str, cwe_id: str = "CWE-89") -> bool:
    """Test reference CWE endpoint."""
    console.print(f"\n[bold blue]Testing Reference API: CWE {cwe_id}[/bold blue]")
    try:
        response = requests.get(
            f"{base_url}/v1/reference/cwe/{cwe_id}",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if not data.get('success'):
            console.print(f"❌ API returned success=false: {data.get('error')}")
            return False

        cwe = data['data']
        console.print(f"✅ {cwe['cwe_id']}: {cwe['name']}")
        console.print(f"   Parents: {len(cwe.get('parents', []))}")
        console.print(f"   Children: {len(cwe.get('children', []))}")
        console.print(f"   Attack Patterns: {len(cwe.get('attack_patterns', []))}")
        return True

    except Exception as e:
        console.print(f"❌ Reference CWE test failed: {e}")
        return False


def test_scan_ingestion(base_url: str, api_key: Optional[str]) -> bool:
    """Test scan ingestion endpoint (requires API key)."""
    if not api_key:
        console.print("\n[bold yellow]Skipping Scan Ingestion Test[/bold yellow]")
        console.print("   Reason: No API key provided (use --api-key)")
        return True  # Not a failure, just skipped

    console.print("\n[bold blue]Testing Scan Ingestion API[/bold blue]")

    # Minimal SARIF payload
    sarif_payload = {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "TestScanner",
                    "version": "1.0.0"
                }
            },
            "results": []
        }]
    }

    try:
        response = requests.post(
            f"{base_url}/v1/scan/ingest",
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "format": "sarif",
                "scan_type": "sast",
                "payload": sarif_payload,
                "metadata": {
                    "repository": "test-repo",
                    "branch": "main"
                }
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if not data.get('success'):
            console.print(f"❌ Scan ingestion failed: {data.get('error')}")
            return False

        result = data['data']
        console.print(f"✅ Scan ingested successfully")
        console.print(f"   Session ID: {result['scan_session_id']}")
        console.print(f"   Findings: {result['findings_count']}")
        console.print(f"   Components: {result['components_count']}")
        return True

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            console.print("❌ Authentication failed: Invalid API key")
        else:
            console.print(f"❌ HTTP Error: {e}")
        return False
    except Exception as e:
        console.print(f"❌ Scan ingestion test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Complira API locally")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of API server (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--api-key",
        help="API key for testing authenticated endpoints (optional)"
    )
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]Complira API Local Test Suite[/bold cyan]\n"
        f"Testing: {args.base_url}",
        border_style="cyan"
    ))

    # Run tests
    results = {
        "Health Check": test_health(args.base_url),
        "Reference CVE API": test_reference_cve(args.base_url),
        "Batch Enrichment API": test_reference_enrich(args.base_url),
        "Reference CWE API": test_reference_cwe(args.base_url),
        "Scan Ingestion API": test_scan_ingestion(args.base_url, args.api_key),
    }

    # Summary
    console.print("\n" + "="*60)
    console.print("[bold]Test Summary[/bold]")
    console.print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "[green]✅ PASS[/green]" if result else "[red]❌ FAIL[/red]"
        console.print(f"{test_name:.<40} {status}")

    console.print("="*60)
    console.print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        console.print("[bold green]🎉 All tests passed![/bold green]")
        sys.exit(0)
    else:
        console.print("[bold red]❌ Some tests failed[/bold red]")
        console.print("\nTroubleshooting:")
        console.print("  1. Check if API server is running: http://localhost:8000/health")
        console.print("  2. Check if ArangoDB is running: docker compose ps arangodb")
        console.print("  3. Check if database is seeded: complira query 'RETURN LENGTH(vulnerabilities)'")
        console.print("  4. View logs: docker compose logs api")
        sys.exit(1)


if __name__ == "__main__":
    main()
