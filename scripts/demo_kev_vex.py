"""
Demo: KEV (Known Exploited Vulnerabilities) and VEX (Vulnerability Exploitability eXchange)

Shows:
1. KEV - CISA catalog of actively exploited vulnerabilities
2. VEX - CycloneDX standard for communicating exploitability status
"""

import json
import requests
from datetime import datetime

API_BASE = "http://localhost:8000/v1"


def demo_kev_data():
    """Show KEV data integration."""
    print("=" * 80)
    print("1. KEV (Known Exploited Vulnerabilities) - CISA Catalog")
    print("=" * 80)
    print("\nCISA KEV Catalog tracks vulnerabilities actively exploited in the wild.")
    print("Source: https://www.cisa.gov/known-exploited-vulnerabilities-catalog\n")

    # Test with a real KEV-listed CVE
    test_cves = ["CVE-2021-30952", "CVE-2023-43000", "CVE-2024-2508"]

    for cve_id in test_cves:
        print(f"\nChecking {cve_id}...")
        try:
            response = requests.get(f"{API_BASE}/reference/cve/{cve_id}", timeout=5)
            if response.status_code == 200:
                data = response.json()['data']

                kev_status = data.get('kev', {})
                print(f"  CVSS: {data.get('cvss_score', 'N/A')}")
                print(f"  KEV Listed: {kev_status.get('in_kev', False)}")

                if kev_status.get('in_kev'):
                    print(f"  ⚠️  ACTIVELY EXPLOITED IN THE WILD")
                    print(f"  Due Date: {kev_status.get('due_date', 'N/A')}")
                    print(f"  Ransomware: {kev_status.get('known_ransomware', False)}")

        except Exception as e:
            print(f"  Error: {e}")

    print("\n💡 KEV Integration Benefits:")
    print("   - Prioritize patching for actively exploited vulnerabilities")
    print("   - Federal agencies have 15-30 day remediation deadlines")
    print("   - Ransomware attribution helps risk assessment")


def generate_vex_document():
    """Generate a VEX document (CycloneDX format)."""
    print("\n" + "=" * 80)
    print("2. VEX (Vulnerability Exploitability eXchange)")
    print("=" * 80)
    print("\nVEX documents communicate vulnerability status in YOUR product.")
    print("Standards: CycloneDX BOM + VEX, CSAF VEX, OpenVEX\n")

    # Example: Laravel SBOM with VEX annotations
    vex_bom = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "component": {
                "type": "application",
                "name": "my-laravel-app",
                "version": "1.0.0"
            }
        },
        "components": [
            {
                "type": "library",
                "name": "laravel/framework",
                "version": "7.12.0",
                "purl": "pkg:composer/laravel/framework@7.12.0"
            }
        ],
        "vulnerabilities": [
            {
                "id": "CVE-2021-3129",
                "source": {
                    "name": "NVD",
                    "url": "https://nvd.nist.gov/vuln/detail/CVE-2021-3129"
                },
                "ratings": [
                    {
                        "source": {"name": "NVD"},
                        "score": 9.8,
                        "severity": "critical",
                        "method": "CVSSv3",
                        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
                    }
                ],
                "affects": [
                    {
                        "ref": "pkg:composer/laravel/framework@7.12.0"
                    }
                ],
                "analysis": {
                    "state": "not_affected",
                    "justification": "code_not_present",
                    "response": ["will_not_fix", "update"],
                    "detail": "Debug mode is disabled in production. The vulnerable code path is not reachable."
                }
            },
            {
                "id": "CVE-2024-2508",
                "source": {
                    "name": "NVD"
                },
                "ratings": [
                    {
                        "score": 5.3,
                        "severity": "medium"
                    }
                ],
                "affects": [
                    {
                        "ref": "pkg:composer/laravel/framework@7.12.0"
                    }
                ],
                "analysis": {
                    "state": "exploitable",
                    "justification": "requires_configuration",
                    "response": ["can_not_fix"],
                    "detail": "Application uses custom authentication middleware that validates permissions."
                }
            }
        ]
    }

    print("📄 Generated VEX Document (CycloneDX 1.5 format):")
    print(json.dumps(vex_bom, indent=2))

    return vex_bom


def vex_states_explained():
    """Explain VEX states."""
    print("\n" + "=" * 80)
    print("VEX Analysis States")
    print("=" * 80)

    states = {
        "exploitable": "Vulnerability is exploitable in this product",
        "in_triage": "Under investigation",
        "not_affected": "Product is not affected (code not present, configuration, etc.)",
        "resolved": "Vulnerability has been remediated",
        "false_positive": "Advisory is incorrect"
    }

    justifications = {
        "code_not_present": "Vulnerable code is not in this product",
        "code_not_reachable": "Code exists but cannot be executed",
        "requires_configuration": "Requires specific configuration",
        "requires_dependency": "Requires specific dependency",
        "requires_environment": "Requires specific environment",
        "protected_by_compiler": "Compiler protections prevent exploit",
        "protected_at_runtime": "Runtime protections prevent exploit",
        "protected_at_perimeter": "Network protections prevent exploit",
        "protected_by_mitigating_control": "Other controls prevent exploit"
    }

    print("\n🔍 VEX States:")
    for state, desc in states.items():
        print(f"   {state}: {desc}")

    print("\n🛡️  VEX Justifications:")
    for just, desc in justifications.items():
        print(f"   {just}: {desc}")


def integration_workflow():
    """Show how KEV + VEX work together."""
    print("\n" + "=" * 80)
    print("3. Integrated KEV + VEX Workflow")
    print("=" * 80)

    workflow = """
1️⃣  SBOM Ingestion
    ↓ Upload CycloneDX/SPDX SBOM

2️⃣  Vulnerability Discovery
    ↓ Query OSV, GitHub, VulnCheck APIs
    ↓ Match packages to CVEs

3️⃣  Knowledge Graph Enrichment (OUR API)
    ↓ CVE → CWE → CAPEC → ATT&CK → Controls
    ↓ Add EPSS scores (exploit probability)
    ↓ Check KEV catalog (actively exploited?)

4️⃣  Risk Prioritization
    ↓ KEV listed? → CRITICAL (patch within 15 days)
    ↓ High EPSS + High CVSS? → HIGH priority
    ↓ Low exploitability? → Medium/Low priority

5️⃣  VEX Publication (YOUR OUTPUT)
    ↓ Document exploitability status per CVE
    ↓ Justify why not affected / mitigated
    ↓ Share with customers/auditors

6️⃣  Compliance Mapping
    ↓ NIST 800-53 controls required
    ↓ FDA/CRA/IEC regulatory requirements
    ↓ Generate compliance evidence
"""

    print(workflow)

    print("\n💼 Business Value:")
    print("   - KEV: Know what to patch FIRST (federal requirement)")
    print("   - VEX: Document your security posture formally")
    print("   - API: Automate the entire enrichment pipeline")
    print("   - Compliance: Map to regulatory requirements automatically")


def main():
    """Run KEV + VEX demo."""
    print("\n🎯 KEV + VEX Integration Demo\n")

    # 1. Show KEV data
    demo_kev_data()

    # 2. Generate VEX document
    vex_doc = generate_vex_document()

    # 3. Explain VEX states
    vex_states_explained()

    # 4. Show integrated workflow
    integration_workflow()

    print("\n" + "=" * 80)
    print("✅ Demo Complete!")
    print("=" * 80)

    print("\n📚 Learn More:")
    print("   KEV: https://www.cisa.gov/known-exploited-vulnerabilities-catalog")
    print("   VEX: https://cyclonedx.org/capabilities/vex/")
    print("   CSAF VEX: https://docs.oasis-open.org/csaf/csaf/v2.0/csaf-v2.0.html")
    print("   OpenVEX: https://github.com/openvex/spec")

    print("\n🚀 Next Implementation Steps:")
    print("   1. Add VEX upload endpoint: POST /v1/scan/vex")
    print("   2. Store VEX analysis states in graph")
    print("   3. Generate VEX documents from scan results")
    print("   4. Add VEX to compliance report templates")


if __name__ == '__main__':
    main()
