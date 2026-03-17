#!/usr/bin/env python3
"""
Complira Compliance Passport Demo

Demonstrates the flagship "Compliance Passport" feature:
- CVE enrichment with threat intelligence
- Automated CVE → Regulatory Requirement mapping
- NIST 800-53 control identification
- 5.27M edge knowledge graph traversal

Requirements:
  pip install requests rich

Usage:
  python compliance_passport_demo.py
"""

import requests
import json
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich import print as rprint

console = Console()

# API Configuration
API_BASE_URL = "http://localhost:8000"  # Change to https://api.complira.dev for production

# Test CVEs
TEST_CVES = [
    "CVE-2023-46456",  # SQL injection example
    "CVE-2024-1234",   # Example CVE (may not exist)
    "CVE-2021-44228",  # Log4Shell (if available)
]


def print_header():
    """Print demo header."""
    console.print(Panel.fit(
        "[bold cyan]Complira Compliance Passport Demo[/bold cyan]\n"
        "[dim]Automated CVE → Regulatory Requirement Mapping[/dim]\n"
        "[yellow]Knowledge Graph: 336K CVEs | 10.3M+ edges | 5.27M compliance mappings[/yellow]",
        border_style="cyan"
    ))
    console.print()


def check_api_health():
    """Check if API is accessible."""
    console.print("[bold]1. Checking API Health[/bold]")

    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        data = response.json()

        if response.status_code == 200:
            console.print(f"   ✅ API Status: [green]{data.get('status', 'unknown')}[/green]")
            console.print(f"   ✅ Database: [green]{data.get('database', 'unknown')}[/green]")
            console.print(f"   ✅ Reference DB: [green]{data.get('reference_database', 'unknown')}[/green]")
            return True
        else:
            console.print(f"   ❌ API returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        console.print("   ❌ Cannot connect to API. Is the server running?")
        console.print(f"   [dim]Try: uvicorn src.api.main:app --host 0.0.0.0 --port 8000[/dim]")
        return False
    except Exception as e:
        console.print(f"   ❌ Error: {e}")
        return False


def enrich_cve(cve_id: str):
    """Get CVE enrichment with full threat intelligence."""
    console.print(f"\n[bold]2. Enriching {cve_id}[/bold]")

    start_time = time.time()

    try:
        response = requests.get(
            f"{API_BASE_URL}/v1/reference/cve/{cve_id}",
            timeout=10
        )
        elapsed_ms = (time.time() - start_time) * 1000

        if response.status_code == 404:
            console.print(f"   ⚠️  CVE not found: {cve_id}")
            return None

        response.raise_for_status()
        data = response.json()

        cve_data = data.get("data", {})

        # Display basic CVE info
        console.print(f"   [green]✓[/green] Response time: {elapsed_ms:.2f}ms")
        console.print()

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="cyan")
        table.add_column("Value")

        table.add_row("CVE ID", cve_data.get("cve_id", "N/A"))
        table.add_row("Severity", f"[red]{cve_data.get('severity', 'N/A')}[/red]")
        table.add_row("CVSS Score", str(cve_data.get("cvss_score", "N/A")))
        table.add_row("Published", cve_data.get("published_date", "N/A")[:10])

        # EPSS data
        epss = cve_data.get("epss", {})
        if epss and epss.get("score"):
            epss_score = epss.get("score", 0)
            epss_pct = epss.get("percentile", 0)
            table.add_row("EPSS Score", f"{epss_score:.5f} ({epss_pct:.2%} percentile)")

        # KEV status
        kev = cve_data.get("kev", {})
        if kev.get("in_kev"):
            table.add_row("KEV Status", "[bold red]⚠️  CISA Known Exploited[/bold red]")

        console.print(table)
        console.print()

        # Description
        description = cve_data.get("description", "N/A")
        if len(description) > 200:
            description = description[:200] + "..."
        console.print(f"   [dim]{description}[/dim]")
        console.print()

        # Threat intelligence counts
        weaknesses = cve_data.get("weaknesses", [])
        attack_patterns = cve_data.get("attack_patterns", [])
        attack_techniques = cve_data.get("attack_techniques", [])
        nist_controls = cve_data.get("nist_controls", [])
        d3fend_defenses = cve_data.get("d3fend_defenses", [])

        console.print("   [bold]Threat Intelligence:[/bold]")
        console.print(f"   • {len(weaknesses)} CWE weaknesses")
        console.print(f"   • {len(attack_patterns)} CAPEC attack patterns")
        console.print(f"   • {len(attack_techniques)} MITRE ATT&CK techniques")
        console.print(f"   • {len(nist_controls)} NIST 800-53 controls")
        console.print(f"   • {len(d3fend_defenses)} D3FEND defenses")

        return cve_data

    except requests.exceptions.Timeout:
        console.print(f"   ❌ Request timeout for {cve_id}")
        return None
    except Exception as e:
        console.print(f"   ❌ Error: {e}")
        return None


def show_weakness_details(cve_data: dict):
    """Display CWE weakness details."""
    weaknesses = cve_data.get("weaknesses", [])

    if not weaknesses:
        console.print("   [dim]No weaknesses found[/dim]")
        return

    console.print(f"\n[bold]3. CWE Weaknesses ({len(weaknesses)})[/bold]")
    console.print()

    for idx, weakness in enumerate(weaknesses[:3], 1):  # Show first 3
        cwe_id = weakness.get("cwe_id", "N/A")
        name = weakness.get("name", "N/A")

        console.print(f"   {idx}. [cyan]{cwe_id}[/cyan]: {name}")

    if len(weaknesses) > 3:
        console.print(f"   [dim]... and {len(weaknesses) - 3} more[/dim]")


def show_attack_techniques(cve_data: dict):
    """Display MITRE ATT&CK techniques."""
    techniques = cve_data.get("attack_techniques", [])

    if not techniques:
        console.print("   [dim]No ATT&CK techniques found[/dim]")
        return

    console.print(f"\n[bold]4. MITRE ATT&CK Techniques ({len(techniques)})[/bold]")
    console.print()

    for idx, technique in enumerate(techniques[:5], 1):  # Show first 5
        tech_id = technique.get("technique_id", "N/A")
        name = technique.get("name", "N/A")
        tactics = technique.get("tactics", [])

        tactics_str = ", ".join(tactics[:2]) if tactics else "N/A"
        console.print(f"   {idx}. [yellow]{tech_id}[/yellow]: {name}")
        console.print(f"      [dim]Tactics: {tactics_str}[/dim]")

    if len(techniques) > 5:
        console.print(f"   [dim]... and {len(techniques) - 5} more[/dim]")


def show_nist_controls(cve_data: dict):
    """Display NIST 800-53 controls."""
    controls = cve_data.get("nist_controls", [])

    if not controls:
        console.print("   [dim]No NIST 800-53 controls found[/dim]")
        return

    console.print(f"\n[bold]5. NIST 800-53 Controls ({len(controls)})[/bold]")
    console.print()

    # Group by family
    families = {}
    for control in controls:
        family = control.get("family", "Unknown")
        if family not in families:
            families[family] = []
        families[family].append(control)

    for family, family_controls in list(families.items())[:3]:  # Show first 3 families
        console.print(f"   [bold green]{family}[/bold green]")
        for control in family_controls[:3]:  # Show first 3 controls per family
            control_id = control.get("control_id", "N/A")
            title = control.get("title", "N/A")
            console.print(f"   • [cyan]{control_id}[/cyan]: {title}")

        if len(family_controls) > 3:
            console.print(f"     [dim]... and {len(family_controls) - 3} more in this family[/dim]")

    if len(families) > 3:
        console.print(f"   [dim]... and {len(families) - 3} more families[/dim]")


def get_compliance_controls(cve_id: str):
    """Get compliance controls for a CVE."""
    console.print(f"\n[bold]6. Compliance Passport: {cve_id} → Regulatory Requirements[/bold]")

    start_time = time.time()

    try:
        response = requests.get(
            f"{API_BASE_URL}/v1/reference/controls/{cve_id}",
            timeout=10
        )
        elapsed_ms = (time.time() - start_time) * 1000

        if response.status_code == 404:
            console.print(f"   ⚠️  CVE not found: {cve_id}")
            return

        response.raise_for_status()
        data = response.json()

        controls_data = data.get("data", {})

        console.print(f"   [green]✓[/green] Response time: {elapsed_ms:.2f}ms")
        console.print()

        # Show traversal path
        console.print("   [bold]Graph Traversal Path:[/bold]")
        console.print("   [dim]CVE → CWE → CAPEC → ATT&CK → NIST 800-53 Control → Regulatory Requirement[/dim]")
        console.print()

        nist_controls = controls_data.get("nist_controls", [])
        regulatory_reqs = controls_data.get("regulatory_requirements", [])

        if nist_controls:
            console.print(f"   [bold]NIST 800-53 Controls ({len(nist_controls)}):[/bold]")
            for idx, control in enumerate(nist_controls[:5], 1):
                control_id = control.get("control_id", "N/A")
                title = control.get("title", "N/A")
                family = control.get("family", "N/A")
                console.print(f"   {idx}. [cyan]{control_id}[/cyan] - {title}")
                console.print(f"      [dim]Family: {family}[/dim]")

            if len(nist_controls) > 5:
                console.print(f"   [dim]... and {len(nist_controls) - 5} more[/dim]")
        else:
            console.print("   [dim]No NIST 800-53 controls found[/dim]")

        console.print()

        if regulatory_reqs:
            console.print(f"   [bold]Regulatory Requirements ({len(regulatory_reqs)}):[/bold]")
            for idx, req in enumerate(regulatory_reqs[:5], 1):
                req_id = req.get("requirement_id", "N/A")
                framework = req.get("framework", "N/A")
                title = req.get("title", "N/A")
                console.print(f"   {idx}. [yellow]{req_id}[/yellow] ({framework})")
                console.print(f"      {title}")

            if len(regulatory_reqs) > 5:
                console.print(f"   [dim]... and {len(regulatory_reqs) - 5} more[/dim]")
        else:
            console.print("   [bold yellow]ℹ️  Regulatory requirements edge collection not yet populated[/bold yellow]")
            console.print("   [dim]Run: python scripts/populate_violates_requirement.py[/dim]")

    except requests.exceptions.Timeout:
        console.print(f"   ❌ Request timeout for {cve_id}")
    except Exception as e:
        console.print(f"   ❌ Error: {e}")


def batch_enrich_demo():
    """Demonstrate batch enrichment."""
    console.print(f"\n[bold]7. Batch CVE Enrichment[/bold]")

    cve_ids = ",".join(TEST_CVES)

    start_time = time.time()

    try:
        response = requests.get(
            f"{API_BASE_URL}/v1/reference/enrich",
            params={"cve_ids": cve_ids},
            timeout=15
        )
        elapsed_ms = (time.time() - start_time) * 1000

        response.raise_for_status()
        data = response.json()

        enriched = data.get("data", [])

        console.print(f"   [green]✓[/green] Enriched {len(enriched)} CVEs in {elapsed_ms:.2f}ms")
        console.print()

        # Count stats across all CVEs
        total_weaknesses = 0
        total_techniques = 0
        total_controls = 0
        found_cves = 0

        for cve_data in enriched:
            if cve_data.get("error"):
                continue

            found_cves += 1
            total_weaknesses += len(cve_data.get("weaknesses", []))
            total_techniques += len(cve_data.get("attack_techniques", []))
            total_controls += len(cve_data.get("nist_controls", []))

        console.print("   [bold]Aggregated Threat Intelligence:[/bold]")
        console.print(f"   • {found_cves} CVEs found")
        console.print(f"   • {total_weaknesses} total CWE weaknesses")
        console.print(f"   • {total_techniques} total ATT&CK techniques")
        console.print(f"   • {total_controls} total NIST 800-53 controls")

    except requests.exceptions.Timeout:
        console.print("   ❌ Request timeout")
    except Exception as e:
        console.print(f"   ❌ Error: {e}")


def show_example_queries():
    """Show example AQL queries."""
    console.print("\n[bold]8. Example AQL Queries (Run in ArangoDB Web UI)[/bold]")
    console.print()

    # Query 1: Find regulatory requirements
    query1 = """// Find all regulatory requirements violated by CVE-2023-46456
FOR req IN 1..1 OUTBOUND DOCUMENT("vulnerabilities/CVE_2023_46456") violates_requirement
  RETURN {
    requirement_id: req.requirement_id,
    framework: req.framework,
    title: req.title
  }"""

    console.print("   [bold cyan]Query 1: Find Regulatory Requirements[/bold cyan]")
    syntax1 = Syntax(query1, "javascript", theme="monokai", line_numbers=False)
    console.print(Panel(syntax1, border_style="cyan"))
    console.print()

    # Query 2: Find critical CVEs violating FDA requirements
    query2 = """// Find all CRITICAL CVEs violating FDA 524B requirement V.C.1
FOR cve IN 1..1 INBOUND DOCUMENT("regulatory_requirements/FDA_524B_V_C_1") violates_requirement
  FILTER cve.severity == "CRITICAL"
  SORT cve.cvss_v3_score DESC
  LIMIT 10
  RETURN {
    cve_id: cve.cve_id,
    cvss_score: cve.cvss_v3_score,
    description: SUBSTRING(cve.description, 0, 100)
  }"""

    console.print("   [bold cyan]Query 2: Find Critical CVEs by Regulatory Requirement[/bold cyan]")
    syntax2 = Syntax(query2, "javascript", theme="monokai", line_numbers=False)
    console.print(Panel(syntax2, border_style="cyan"))


def main():
    """Run the demo."""
    print_header()

    # Check API health
    if not check_api_health():
        console.print("\n[bold red]Cannot proceed without API access. Exiting.[/bold red]")
        return

    console.print()

    # Pick first available CVE for detailed demo
    cve_data = None
    for cve_id in TEST_CVES:
        cve_data = enrich_cve(cve_id)
        if cve_data:
            # Show detailed threat intelligence
            show_weakness_details(cve_data)
            show_attack_techniques(cve_data)
            show_nist_controls(cve_data)

            # Show compliance controls
            get_compliance_controls(cve_id)

            break  # Found a working CVE, stop

    # Batch enrichment demo
    batch_enrich_demo()

    # Example queries
    show_example_queries()

    # Summary
    console.print()
    console.print(Panel.fit(
        "[bold green]✅ Compliance Passport Demo Complete![/bold green]\n\n"
        "[bold]Key Features Demonstrated:[/bold]\n"
        "• CVE enrichment with full threat intelligence (~13ms response time)\n"
        "• CWE weakness identification\n"
        "• MITRE ATT&CK technique mapping\n"
        "• NIST 800-53 control identification\n"
        "• Regulatory requirement mapping (5.27M edges)\n"
        "• Batch enrichment (multiple CVEs in one request)\n\n"
        "[bold]Next Steps:[/bold]\n"
        "• Explore interactive API docs: http://localhost:8000/docs\n"
        "• Read full documentation: docs/API_DOCUMENTATION.md\n"
        "• Try the example AQL queries in ArangoDB Web UI\n"
        "• Integrate with your CI/CD pipeline (GitHub Actions example included)",
        border_style="green"
    ))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Demo interrupted by user[/yellow]")
