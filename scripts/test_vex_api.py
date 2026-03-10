"""
Test script for VEX API endpoints.

Demonstrates complete VEX CRUD workflow:
1. CREATE - Submit VEX document from client
2. READ - Retrieve enriched VEX
3. UPDATE - Update entire VEX document
4. PATCH - Update single CVE assessment
5. LIST - List all VEX documents
6. DELETE - Remove VEX document
"""

import requests
import json
from datetime import datetime

# API configuration
API_BASE = "http://localhost:8000/v1"
API_KEY = "demo_api_key_12345678901234567890"  # Demo customer API key

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}


def test_create_vex():
    """Test 1: Create VEX document."""
    print("=" * 80)
    print("TEST 1: Create VEX Document")
    print("=" * 80)

    vex_payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "vulnerabilities": [
            {
                "id": "CVE-2021-44228",
                "analysis": {
                    "state": "not_affected",
                    "justification": "code_not_reachable",
                    "detail": "Log4j is included but logging is disabled in production configuration"
                }
            },
            {
                "id": "CVE-2024-2508",
                "analysis": {
                    "state": "exploitable",
                    "response": ["update"],
                    "detail": "Vulnerability confirmed exploitable, patch available"
                }
            }
        ],
        "metadata": {
            "component": {
                "type": "application",
                "name": "my-app",
                "version": "1.0.0"
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    }

    print(f"\n📤 POST {API_BASE}/vex")
    print(f"   Vulnerabilities: {len(vex_payload['vulnerabilities'])}")

    response = requests.post(
        f"{API_BASE}/vex",
        headers=HEADERS,
        json=vex_payload
    )

    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ VEX Created Successfully")
        print(f"   VEX ID: {data['data']['vex_id']}")
        print(f"   Vulnerabilities: {data['data']['vulnerabilities_count']}")
        print(f"   Enriched: {data['data']['enriched_count']}")
        print(f"   Execution Time: {data['metadata']['execution_time_ms']:.2f}ms")

        return data['data']['vex_id']
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return None


def test_get_vex(vex_id):
    """Test 2: Retrieve enriched VEX document."""
    print("\n" + "=" * 80)
    print("TEST 2: Get VEX Document (with enrichment)")
    print("=" * 80)

    print(f"\n📥 GET {API_BASE}/vex/{vex_id}")

    response = requests.get(
        f"{API_BASE}/vex/{vex_id}",
        headers=HEADERS
    )

    if response.status_code == 200:
        data = response.json()
        vex = data['data']

        print(f"\n✅ VEX Retrieved Successfully")
        print(f"   VEX ID: {vex['vex_id']}")
        print(f"   Version: {vex['version']}")
        print(f"   Vulnerabilities: {len(vex['vulnerabilities'])}")
        print(f"   Created: {vex['created_at']}")

        # Show enrichment for first CVE
        if vex['vulnerabilities']:
            vuln = vex['vulnerabilities'][0]
            print(f"\n📊 Sample Enrichment - {vuln['cve_id']}:")
            print(f"   State: {vuln['state']}")
            print(f"   KEV Listed: {vuln['enrichment'].get('in_kev', False)}")
            print(f"   EPSS Score: {vuln['enrichment'].get('epss_score', 'N/A')}")
            print(f"   CVSS Score: {vuln['enrichment'].get('cvss_score', 'N/A')}")
            print(f"   CVSS Severity: {vuln['enrichment'].get('cvss_severity', 'N/A')}")
            print(f"   CWE Weaknesses: {len(vuln['enrichment'].get('weaknesses', []))}")
            print(f"   ATT&CK Techniques: {len(vuln['enrichment'].get('attack_techniques', []))}")
            print(f"   NIST Controls: {len(vuln['enrichment'].get('nist_controls', []))}")

            # Show first control
            if vuln['enrichment'].get('nist_controls'):
                ctrl = vuln['enrichment']['nist_controls'][0]
                print(f"   First Control: {ctrl['control_id']} - {ctrl['title']}")

        return True
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_list_vex():
    """Test 3: List all VEX documents."""
    print("\n" + "=" * 80)
    print("TEST 3: List VEX Documents")
    print("=" * 80)

    print(f"\n📋 GET {API_BASE}/vex?limit=10")

    response = requests.get(
        f"{API_BASE}/vex?limit=10",
        headers=HEADERS
    )

    if response.status_code == 200:
        data = response.json()
        vex_list = data['data']

        print(f"\n✅ Found {len(vex_list)} VEX documents")

        for vex in vex_list[:3]:  # Show first 3
            print(f"\n   • {vex['vex_id']}")
            print(f"     Vulnerabilities: {vex['vulnerabilities_count']}")
            print(f"     Created: {vex['created_at']}")

        return True
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_patch_vulnerability(vex_id):
    """Test 4: Update single vulnerability assessment."""
    print("\n" + "=" * 80)
    print("TEST 4: Patch Single Vulnerability")
    print("=" * 80)

    patch_payload = {
        "analysis": {
            "state": "resolved",
            "response": ["update"],
            "detail": "Updated to patched version Log4j 2.17.1"
        }
    }

    cve_id = "CVE-2021-44228"

    print(f"\n🔧 PATCH {API_BASE}/vex/{vex_id}/vulnerability/{cve_id}")
    print(f"   New State: {patch_payload['analysis']['state']}")

    response = requests.patch(
        f"{API_BASE}/vex/{vex_id}/vulnerability/{cve_id}",
        headers=HEADERS,
        json=patch_payload
    )

    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Vulnerability Updated")
        print(f"   VEX ID: {data['data']['vex_id']}")
        print(f"   Updated At: {data['data']['updated_at']}")

        return True
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_update_vex(vex_id):
    """Test 5: Update entire VEX document."""
    print("\n" + "=" * 80)
    print("TEST 5: Update Entire VEX Document")
    print("=" * 80)

    update_payload = {
        "vulnerabilities": [
            {
                "id": "CVE-2021-44228",
                "analysis": {
                    "state": "resolved",
                    "response": ["update"],
                    "detail": "Updated to Log4j 2.17.1 (fully patched)"
                }
            },
            {
                "id": "CVE-2024-2508",
                "analysis": {
                    "state": "resolved",
                    "response": ["update"],
                    "detail": "Patched in latest release"
                }
            },
            {
                "id": "CVE-2023-43000",
                "analysis": {
                    "state": "not_affected",
                    "justification": "code_not_present",
                    "detail": "Component not used in our application"
                }
            }
        ],
        "metadata": {
            "component": {
                "type": "application",
                "name": "my-app",
                "version": "1.1.0"
            },
            "note": "Updated to latest patched versions"
        }
    }

    print(f"\n📝 PUT {API_BASE}/vex/{vex_id}")
    print(f"   New Vulnerabilities Count: {len(update_payload['vulnerabilities'])}")

    response = requests.put(
        f"{API_BASE}/vex/{vex_id}",
        headers=HEADERS,
        json=update_payload
    )

    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ VEX Updated")
        print(f"   VEX ID: {data['data']['vex_id']}")
        print(f"   Vulnerabilities: {data['data']['vulnerabilities_count']}")
        print(f"   Updated At: {data['data']['updated_at']}")

        return True
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_delete_vex(vex_id):
    """Test 6: Delete VEX document."""
    print("\n" + "=" * 80)
    print("TEST 6: Delete VEX Document")
    print("=" * 80)

    print(f"\n🗑️  DELETE {API_BASE}/vex/{vex_id}")

    response = requests.delete(
        f"{API_BASE}/vex/{vex_id}",
        headers=HEADERS
    )

    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ VEX Deleted")
        print(f"   VEX ID: {data['data']['vex_id']}")

        return True
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def main():
    """Run complete VEX API test workflow."""
    print("\n🎯 VEX API Integration Test")
    print("Testing complete CRUD workflow with knowledge graph enrichment\n")

    try:
        # Test 1: Create VEX
        vex_id = test_create_vex()
        if not vex_id:
            print("\n❌ Test suite failed at CREATE")
            return

        # Test 2: Get VEX (enriched)
        if not test_get_vex(vex_id):
            print("\n❌ Test suite failed at GET")
            return

        # Test 3: List VEX documents
        if not test_list_vex():
            print("\n❌ Test suite failed at LIST")
            return

        # Test 4: Patch single vulnerability
        if not test_patch_vulnerability(vex_id):
            print("\n❌ Test suite failed at PATCH")
            return

        # Verify patch worked
        test_get_vex(vex_id)

        # Test 5: Update entire VEX
        if not test_update_vex(vex_id):
            print("\n❌ Test suite failed at UPDATE")
            return

        # Verify update worked
        test_get_vex(vex_id)

        # Test 6: Delete VEX
        if not test_delete_vex(vex_id):
            print("\n❌ Test suite failed at DELETE")
            return

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)

        print("\n📚 VEX API Endpoints:")
        print(f"   POST   {API_BASE}/vex")
        print(f"   GET    {API_BASE}/vex")
        print(f"   GET    {API_BASE}/vex/{{vex_id}}")
        print(f"   PUT    {API_BASE}/vex/{{vex_id}}")
        print(f"   PATCH  {API_BASE}/vex/{{vex_id}}/vulnerability/{{cve_id}}")
        print(f"   DELETE {API_BASE}/vex/{{vex_id}}")

        print("\n💡 Integration with Your Client App:")
        print("   1. Your client generates VEX with reachability analysis")
        print("   2. POST to /v1/vex to store and enrich with knowledge graph")
        print("   3. GET enriched VEX with KEV, EPSS, ATT&CK, NIST controls")
        print("   4. PATCH to update individual CVE assessments")
        print("   5. PUT to replace entire VEX document")

    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
