"""
Complira Knowledge Graph CLI.

Command-line interface for managing the cybersecurity knowledge graph.

Commands:
- seed: Populate knowledge graph with all data sources
- incremental: Run incremental updates for specific agents
- ingest: Run individual data ingestion agents
- blast-radius: Analyze regulatory impact of a CVE
- generate-vex: Generate VEX document for an SBOM
- compliance: Analyze compliance status and violations
- violations: List compliance violations
- requirement: Analyze individual requirements
- query: Execute AQL query against the graph
- status: Check system health and statistics
- report: Generate prioritized vulnerability patching reports
- analyze: Analyze CISA-enriched vulnerability data
- init: Initialize database schema
- schedule: Manage Prefect schedules
"""

import sys
import json
from typing import Optional, List
from pathlib import Path
from datetime import datetime

import click
import structlog
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from .db import get_db, init_schema, health_check
from .config import get_settings
from .orchestrator import (
    execute_seed_dag,
    execute_incremental_update,
    deploy_schedules,
    show_schedules,
)

logger = structlog.get_logger()
console = Console()


# ========== CLI Group ==========

@click.group()
@click.version_option(version='1.0.0', prog_name='complira')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose: bool):
    """
    Complira Knowledge Graph - Cybersecurity Compliance Engine.

    Unified knowledge graph for vulnerabilities, threats, compliance, and components.
    """
    if verbose:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        )


# ========== Seed Commands ==========

@cli.command()
@click.option('--skip-llm', is_flag=True, help='Skip LLM enrichment agents')
@click.option('--max-concurrent', default=4, help='Max concurrent agents (default: 4)')
def seed(skip_llm: bool, max_concurrent: int):
    """
    Populate knowledge graph with all data sources.

    Executes all data ingestion and enrichment agents in dependency order.
    Uses Prefect for orchestration and parallel execution.

    Examples:
        complira seed
        complira seed --skip-llm
        complira seed --max-concurrent 8
    """
    console.print("\n[bold cyan]Complira Knowledge Graph - Seed Workflow[/bold cyan]\n")

    # Display configuration
    settings = get_settings()
    console.print(f"Database: {settings.ARANGO_URL}")
    console.print(f"Skip LLM: {skip_llm}")
    console.print(f"Max Concurrent: {max_concurrent}\n")

    # Confirm execution
    if not click.confirm("Start seed workflow?", default=True):
        console.print("[yellow]Aborted[/yellow]")
        return

    console.print()

    # Execute workflow
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Executing seed workflow...", total=None)

            result = execute_seed_dag(
                skip_llm=skip_llm,
                max_concurrent=max_concurrent,
            )

            progress.update(task, completed=True)

        # Display results
        console.print("\n[bold green]✓ Seed Workflow Completed[/bold green]\n")

        stats_table = Table(show_header=False, box=None)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", style="white")

        stats_table.add_row("Total Execution Time", f"{result['total_execution_time_seconds']:.2f} seconds")
        stats_table.add_row("Agents Executed", str(result['total_agents_executed']))
        stats_table.add_row("Successful", f"[green]{result['successful_agents']}[/green]")
        stats_table.add_row("Failed", f"[red]{result['failed_agents']}[/red]")
        stats_table.add_row("Records Created", f"{result['total_records_created']:,}")
        stats_table.add_row("Records Updated", f"{result['total_records_updated']:,}")

        console.print(stats_table)
        console.print()

        # Display failures if any
        if result['failed_agents'] > 0:
            console.print("[bold red]Failed Agents:[/bold red]")
            for agent_result in result['agent_results']:
                if agent_result.get('status') == 'failed':
                    console.print(f"  • {agent_result.get('agent', 'Unknown')}")
            console.print()

    except Exception as e:
        console.print(f"\n[bold red]✗ Seed workflow failed: {e}[/bold red]\n")
        logger.error("Seed workflow failed", error=str(e))
        sys.exit(1)


@cli.command()
@click.argument('agents', nargs=-1)
def incremental(agents: List[str]):
    """
    Run incremental update for specific agents.

    If no agents specified, runs default high-frequency agents:
    NVDAgent, KEVAgent, EPSSAgent, GHSAAgent

    Examples:
        complira incremental
        complira incremental NVDAgent KEVAgent
        complira incremental EPSSAgent GHSAAgent OSVAgent
    """
    console.print("\n[bold cyan]Incremental Update[/bold cyan]\n")

    agent_list = list(agents) if agents else None

    if agent_list:
        console.print(f"Agents: {', '.join(agent_list)}\n")
    else:
        console.print("Agents: NVDAgent, KEVAgent, EPSSAgent, GHSAAgent (default)\n")

    try:
        result = execute_incremental_update(agents=agent_list)

        console.print(f"\n[bold green]✓ Incremental update completed[/bold green]\n")
        console.print(f"Agents executed: {result['agents_executed']}")
        console.print(f"Successful: [green]{result['successful']}[/green]")
        console.print(f"Failed: [red]{result['failed']}[/red]\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Incremental update failed: {e}[/bold red]\n")
        sys.exit(1)


# ========== Ingest Commands ==========

@cli.group()
def ingest():
    """
    Run individual data ingestion agents.

    Ingest data from specific regulatory frameworks or vulnerability sources.

    Examples:
        complira ingest nist-ssdf
        complira ingest cra
        complira ingest fda-524b
        complira ingest iec-62304
        complira ingest yaml-framework DORA
    """
    pass


@ingest.command('nist-ssdf')
def ingest_nist_ssdf():
    """Ingest NIST SSDF (Secure Software Development Framework)."""
    console.print("\n[bold cyan]NIST SSDF Ingestion[/bold cyan]\n")

    try:
        from complira_graph.agents.nist_ssdf import NISTSSDFAgent

        db = get_db()
        agent = NISTSSDFAgent(db)

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task("Fetching NIST SSDF data...", total=None)
            result = agent.run()
            progress.update(task, completed=True)

        # Display results
        if result.get('status') == 'success':
            console.print(f"\n[green]✓ NIST SSDF ingestion completed[/green]")
            console.print(f"Execution time: {result.get('execution_time_seconds', 0):.2f}s")

            # Display collection breakdown
            if 'collections' in result:
                console.print("\nCollection Statistics:")
                for coll_name, stats in result['collections'].items():
                    console.print(f"  {coll_name}:")
                    console.print(f"    Created: {stats.get('created', 0)}")
                    console.print(f"    Updated: {stats.get('updated', 0)}")
            else:
                console.print(f"Documents created: {result.get('created', 0)}")
                console.print(f"Documents updated: {result.get('updated', 0)}")
            console.print()
        else:
            console.print(f"\n[red]✗ NIST SSDF ingestion failed: {result.get('error', 'Unknown error')}[/red]\n")
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[red]✗ Error: {e}[/red]\n")
        logger.error("NIST SSDF ingestion failed", error=str(e))
        sys.exit(1)


@ingest.command('cra')
def ingest_cra():
    """Ingest EU Cyber Resilience Act (CRA) requirements."""
    console.print("\n[bold cyan]CRA Ingestion[/bold cyan]\n")

    try:
        from complira_graph.agents.cra import CRAAgent

        db = get_db()
        agent = CRAAgent(db)

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task("Fetching CRA requirements...", total=None)
            result = agent.run()
            progress.update(task, completed=True)

        # Display results
        if result.get('status') == 'success':
            console.print(f"\n[green]✓ CRA ingestion completed[/green]")
            console.print(f"Execution time: {result.get('execution_time_seconds', 0):.2f}s")

            # Display collection breakdown
            if 'collections' in result:
                console.print("\nCollection Statistics:")
                for coll_name, stats in result['collections'].items():
                    console.print(f"  {coll_name}:")
                    console.print(f"    Created: {stats.get('created', 0)}")
                    console.print(f"    Updated: {stats.get('updated', 0)}")
            else:
                console.print(f"Documents created: {result.get('created', 0)}")
                console.print(f"Documents updated: {result.get('updated', 0)}")
            console.print()
        else:
            console.print(f"\n[red]✗ CRA ingestion failed: {result.get('error', 'Unknown error')}[/red]\n")
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[red]✗ Error: {e}[/red]\n")
        logger.error("CRA ingestion failed", error=str(e))
        sys.exit(1)


@ingest.command('fda-524b')
def ingest_fda_524b():
    """Ingest FDA Section 524B cybersecurity requirements."""
    console.print("\n[bold cyan]FDA Section 524B Ingestion[/bold cyan]\n")

    try:
        from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent

        db = get_db()
        agent = YAMLRegulatoryAgent(db, framework_key="FDA_524B")

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task("Fetching FDA 524B requirements...", total=None)
            result = agent.run()
            progress.update(task, completed=True)

        # Display results
        if result.get('status') == 'success':
            console.print(f"\n[green]✓ FDA Section 524B ingestion completed[/green]")
            console.print(f"Execution time: {result.get('execution_time_seconds', 0):.2f}s")

            # Display collection breakdown
            if 'collections' in result:
                console.print("\nCollection Statistics:")
                for coll_name, stats in result['collections'].items():
                    console.print(f"  {coll_name}:")
                    console.print(f"    Created: {stats.get('created', 0)}")
                    console.print(f"    Updated: {stats.get('updated', 0)}")
            else:
                console.print(f"Documents created: {result.get('created', 0)}")
                console.print(f"Documents updated: {result.get('updated', 0)}")
            console.print()
        else:
            console.print(f"\n[red]✗ FDA 524B ingestion failed: {result.get('error', 'Unknown error')}[/red]\n")
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[red]✗ Error: {e}[/red]\n")
        logger.error("FDA 524B ingestion failed", error=str(e))
        sys.exit(1)


@ingest.command('iec-62304')
def ingest_iec_62304():
    """Ingest IEC 62304 medical device software lifecycle standard."""
    console.print("\n[bold cyan]IEC 62304 Ingestion[/bold cyan]\n")

    try:
        from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent

        db = get_db()
        agent = YAMLRegulatoryAgent(db, framework_key="IEC_62304")

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task("Fetching IEC 62304 requirements...", total=None)
            result = agent.run()
            progress.update(task, completed=True)

        # Display results
        if result.get('status') == 'success':
            console.print(f"\n[green]✓ IEC 62304 ingestion completed[/green]")
            console.print(f"Execution time: {result.get('execution_time_seconds', 0):.2f}s")

            # Display collection breakdown
            if 'collections' in result:
                console.print("\nCollection Statistics:")
                for coll_name, stats in result['collections'].items():
                    console.print(f"  {coll_name}:")
                    console.print(f"    Created: {stats.get('created', 0)}")
                    console.print(f"    Updated: {stats.get('updated', 0)}")
            else:
                console.print(f"Documents created: {result.get('created', 0)}")
                console.print(f"Documents updated: {result.get('updated', 0)}")
            console.print()
        else:
            console.print(f"\n[red]✗ IEC 62304 ingestion failed: {result.get('error', 'Unknown error')}[/red]\n")
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[red]✗ Error: {e}[/red]\n")
        logger.error("IEC 62304 ingestion failed", error=str(e))
        sys.exit(1)


@ingest.command('yaml-framework')
@click.argument('framework_key')
def ingest_yaml_framework(framework_key: str):
    """
    Ingest any YAML-based regulatory framework.

    Arguments:
        framework_key: Framework identifier (e.g., DORA, NIS2, ISO_21434)

    Examples:
        complira ingest yaml-framework DORA
        complira ingest yaml-framework NIS2
        complira ingest yaml-framework ISO_21434
    """
    console.print(f"\n[bold cyan]{framework_key} Ingestion[/bold cyan]\n")

    try:
        from complira_graph.agents.yaml_regulatory import YAMLRegulatoryAgent

        db = get_db()
        agent = YAMLRegulatoryAgent(db, framework_key=framework_key)

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task(f"Fetching {framework_key} requirements...", total=None)
            result = agent.run()
            progress.update(task, completed=True)

        # Display results
        if result.get('status') == 'success':
            console.print(f"\n[green]✓ {framework_key} ingestion completed[/green]")
            console.print(f"Execution time: {result.get('execution_time_seconds', 0):.2f}s")

            # Display collection breakdown
            if 'collections' in result:
                console.print("\nCollection Statistics:")
                for coll_name, stats in result['collections'].items():
                    console.print(f"  {coll_name}:")
                    console.print(f"    Created: {stats.get('created', 0)}")
                    console.print(f"    Updated: {stats.get('updated', 0)}")
            else:
                console.print(f"Documents created: {result.get('created', 0)}")
                console.print(f"Documents updated: {result.get('updated', 0)}")
            console.print()
        else:
            console.print(f"\n[red]✗ {framework_key} ingestion failed: {result.get('error', 'Unknown error')}[/red]\n")
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[red]✗ Error: {e}[/red]\n")
        logger.error(f"{framework_key} ingestion failed", error=str(e))
        sys.exit(1)


@ingest.command('list')
def list_agents():
    """List all available ingestion agents."""
    console.print("\n[bold cyan]Available Ingestion Agents[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Command", style="cyan", no_wrap=True)
    table.add_column("Framework", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Status", style="blue")

    # Regulatory agents - specific implementations
    table.add_row("nist-ssdf", "NIST Secure Software Development Framework", "Regulatory", "✓ Available")
    table.add_row("cra", "EU Cyber Resilience Act", "Regulatory", "✓ Available")

    # YAML-based regulatory agents
    table.add_row("fda-524b", "FDA Section 524B (Medical Devices)", "Regulatory (YAML)", "✓ Available")
    table.add_row("iec-62304", "IEC 62304 (Medical Device Software)", "Regulatory (YAML)", "✓ Available")

    # Generic YAML framework
    table.add_row("yaml-framework <KEY>", "Any YAML-based Framework", "Regulatory (Generic)", "✓ Available")

    console.print(table)
    console.print("\n[bold]Examples:[/bold]")
    console.print("  complira ingest nist-ssdf")
    console.print("  complira ingest cra")
    console.print("  complira ingest fda-524b")
    console.print("  complira ingest yaml-framework DORA")
    console.print("\n[bold]YAML Frameworks:[/bold]")
    console.print("  Supported framework keys: FDA_524B, IEC_62304, DORA, NIS2, ISO_21434")
    console.print("  YAML files must exist at: data/regulations/{framework_key.lower()}.yaml\n")


# ========== Compliance Commands ==========

@cli.group()
def compliance():
    """
    Compliance and regulatory framework commands.

    Analyze compliance status, violations, and requirement impacts.
    """
    pass


@compliance.command(name='status')
@click.argument('tenant_id')
@click.option('--framework', help='Filter by specific framework key (e.g., CRA, NIST_SSDF)')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.option('--output', type=click.Path(), help='Save to file')
def compliance_status(tenant_id: str, framework: Optional[str], format: str, output: Optional[str]):
    """
    Show compliance status for all regulatory frameworks.

    Displays compliance scores, violation counts, and requirement statistics
    for each in-force regulatory framework.

    Examples:
        complira compliance status acme_corp
        complira compliance status acme_corp --framework CRA
        complira compliance status acme_corp --format json --output report.json
    """
    from .queries.compliance import ComplianceQueries

    console.print(f"\n[bold cyan]Compliance Status: {tenant_id}[/bold cyan]\n")

    try:
        db = get_db()
        frameworks = ComplianceQueries.get_framework_compliance(
            db,
            tenant_id,
            include_violations=False  # Don't include detailed violations for status view
        )

        if not frameworks:
            console.print("[yellow]No regulatory frameworks found or no requirements defined.[/yellow]\n")
            sys.exit(0)

        # Filter by framework if specified
        if framework:
            frameworks = [fw for fw in frameworks if fw['framework'] == framework]
            if not frameworks:
                console.print(f"[red]Framework not found: {framework}[/red]\n")
                sys.exit(1)

        # Output as JSON
        if format == 'json':
            output_data = json.dumps(frameworks, indent=2, default=str)

            if output:
                Path(output).write_text(output_data)
                console.print(f"[green]Results saved to {output}[/green]\n")
            else:
                console.print(output_data)

        else:
            # Table format
            table = Table(title=f"Compliance Status - {tenant_id}")
            table.add_column("Framework", style="cyan", no_wrap=True)
            table.add_column("Jurisdiction", style="white")
            table.add_column("Requirements", justify="right", style="white")
            table.add_column("Violated", justify="right", style="red")
            table.add_column("Compliant", justify="right", style="green")
            table.add_column("Score", justify="right", style="bold")
            table.add_column("Status", style="bold")

            for fw in frameworks:
                # Color-code compliance score
                score = fw['compliance_score']
                if score >= 0.95:
                    score_color = "green"
                    status_color = "green"
                elif score >= 0.80:
                    score_color = "yellow"
                    status_color = "yellow"
                else:
                    score_color = "red"
                    status_color = "red"

                table.add_row(
                    fw['framework_short_name'] or fw['framework_name'],
                    fw.get('jurisdiction', 'N/A'),
                    str(fw['total_requirements']),
                    str(fw['violated_requirements']),
                    str(fw['compliant_requirements']),
                    f"[{score_color}]{fw['compliance_percentage']}[/{score_color}]",
                    f"[{status_color}]{fw['status']}[/{status_color}]"
                )

            console.print(table)
            console.print()

            # Summary
            total_reqs = sum(fw['total_requirements'] for fw in frameworks)
            total_violated = sum(fw['violated_requirements'] for fw in frameworks)

            console.print(f"[bold]Total Requirements:[/bold] {total_reqs:,}")
            console.print(f"[bold]Total Violated:[/bold] {total_violated:,}")
            console.print(f"[bold]Overall Compliance:[/bold] {((total_reqs - total_violated) / total_reqs * 100):.1f}%\n")

            if output:
                Path(output).write_text(json.dumps(frameworks, indent=2, default=str))
                console.print(f"[green]Full data saved to {output}[/green]\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Compliance check failed: {e}[/bold red]\n")
        logger.error("Compliance status check failed", tenant_id=tenant_id, error=str(e))
        sys.exit(1)


@cli.group()
def violations():
    """
    Compliance violation commands.

    List and analyze violations of regulatory requirements.
    """
    pass


@violations.command(name='list')
@click.argument('tenant_id')
@click.option('--framework', help='Filter by framework key (e.g., CRA, NIST_SSDF)')
@click.option('--source', type=click.Choice(['cwe', 'scanner', 'all']), default='all',
              help='Violation source: cwe (Path A), scanner (Path B), or all')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.option('--output', type=click.Path(), help='Save to file')
@click.option('--limit', type=int, help='Limit number of violations displayed')
def list_violations(tenant_id: str, framework: Optional[str], source: str,
                   format: str, output: Optional[str], limit: Optional[int]):
    """
    List all compliance violations.

    Shows violations detected through:
    - Path A: CWE mappings (vulnerabilities → weaknesses → requirements)
    - Path B: Direct scanner findings (SAST/DAST/SCA → requirements)

    Examples:
        complira violations list acme_corp
        complira violations list acme_corp --framework CRA
        complira violations list acme_corp --source cwe --limit 20
        complira violations list acme_corp --format json --output violations.json
    """
    from .queries.compliance import ComplianceQueries

    console.print(f"\n[bold cyan]Compliance Violations: {tenant_id}[/bold cyan]\n")

    try:
        db = get_db()

        # Get violations based on source filter
        if source == 'cwe':
            all_violations = {
                'cwe_violations': ComplianceQueries.get_violations_via_cwe_mapping(db, tenant_id, framework),
                'direct_violations': [],
                'summary': {}
            }
        elif source == 'scanner':
            all_violations = {
                'cwe_violations': [],
                'direct_violations': ComplianceQueries.get_violations_via_scanner_findings(db, tenant_id, framework),
                'summary': {}
            }
        else:  # all
            all_violations = ComplianceQueries.get_all_violations(db, tenant_id, framework)

        cwe_violations = all_violations['cwe_violations']
        direct_violations = all_violations['direct_violations']

        if format == 'json':
            output_data = json.dumps(all_violations, indent=2, default=str)

            if output:
                Path(output).write_text(output_data)
                console.print(f"[green]Results saved to {output}[/green]\n")
            else:
                console.print(output_data)

        else:
            # Display CWE-based violations (Path A)
            if cwe_violations:
                cwe_table = Table(title="Path A: CWE Mapping Violations")
                cwe_table.add_column("Requirement", style="cyan", no_wrap=True)
                cwe_table.add_column("Framework", style="yellow", no_wrap=True)
                cwe_table.add_column("CVE", style="red", no_wrap=True)
                cwe_table.add_column("CWE", style="magenta", no_wrap=True)
                cwe_table.add_column("CVSS", justify="right", style="white")
                cwe_table.add_column("Component", style="white")

                display_count = limit if limit else len(cwe_violations)
                for violation in cwe_violations[:display_count]:
                    cwe_table.add_row(
                        violation.get('requirement_id', 'N/A'),
                        violation.get('framework', 'N/A'),
                        violation.get('cve_id', 'N/A'),
                        violation.get('cwe_id', 'N/A'),
                        f"{violation.get('cvss_v3_score', 0):.1f}" if violation.get('cvss_v3_score') else 'N/A',
                        violation.get('component_name', 'N/A')[:40]
                    )

                console.print(cwe_table)
                if limit and len(cwe_violations) > limit:
                    console.print(f"... and {len(cwe_violations) - limit} more CWE violations\n")
                else:
                    console.print()

            # Display scanner-based violations (Path B)
            if direct_violations:
                scanner_table = Table(title="Path B: Direct Scanner Finding Violations")
                scanner_table.add_column("Requirement", style="cyan", no_wrap=True)
                scanner_table.add_column("Framework", style="yellow", no_wrap=True)
                scanner_table.add_column("Finding Type", style="magenta", no_wrap=True)
                scanner_table.add_column("Severity", style="red", no_wrap=True)
                scanner_table.add_column("CWE", style="white", no_wrap=True)
                scanner_table.add_column("File", style="white")

                display_count = limit if limit else len(direct_violations)
                for violation in direct_violations[:display_count]:
                    scanner_table.add_row(
                        violation.get('requirement_id', 'N/A'),
                        violation.get('framework', 'N/A'),
                        violation.get('finding_type', 'N/A'),
                        violation.get('severity', 'N/A'),
                        violation.get('cwe_id', 'N/A'),
                        violation.get('file_path', 'N/A')[:40] if violation.get('file_path') else 'N/A'
                    )

                console.print(scanner_table)
                if limit and len(direct_violations) > limit:
                    console.print(f"... and {len(direct_violations) - limit} more scanner violations\n")
                else:
                    console.print()

            # Summary
            if not cwe_violations and not direct_violations:
                console.print("[green]✓ No compliance violations found![/green]\n")
            else:
                summary_table = Table(show_header=False, box=None)
                summary_table.add_column("Metric", style="cyan")
                summary_table.add_column("Count", style="white")

                summary_table.add_row("CWE-based violations (Path A)", f"[red]{len(cwe_violations)}[/red]")
                summary_table.add_row("Scanner violations (Path B)", f"[red]{len(direct_violations)}[/red]")
                summary_table.add_row("Total violations", f"[bold red]{len(cwe_violations) + len(direct_violations)}[/bold red]")

                if all_violations.get('summary'):
                    summary_table.add_row("Unique requirements violated",
                                        f"[yellow]{all_violations['summary'].get('unique_requirements', 0)}[/yellow]")

                console.print(summary_table)
                console.print()

            if output:
                Path(output).write_text(json.dumps(all_violations, indent=2, default=str))
                console.print(f"[green]Full data saved to {output}[/green]\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Violations query failed: {e}[/bold red]\n")
        logger.error("Violations query failed", tenant_id=tenant_id, error=str(e))
        sys.exit(1)


@cli.group()
def requirement():
    """
    Regulatory requirement commands.

    Analyze individual requirements and their impact.
    """
    pass


@requirement.command(name='show')
@click.argument('requirement_key')
@click.argument('tenant_id')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.option('--output', type=click.Path(), help='Save to file')
def show_requirement(requirement_key: str, tenant_id: str, format: str, output: Optional[str]):
    """
    Show requirement details and blast radius.

    Displays:
    - Requirement metadata
    - All affected components
    - Violations through both Path A (CWE) and Path B (scanner findings)
    - Total impact across tenant infrastructure

    Examples:
        complira requirement show CRA_I_1_a acme_corp
        complira requirement show NIST_SSDF_PO_1_1 acme_corp --format json
    """
    from .queries.compliance import ComplianceQueries

    console.print(f"\n[bold cyan]Requirement Blast Radius: {requirement_key}[/bold cyan]\n")

    try:
        db = get_db()
        blast_radius = ComplianceQueries.get_requirement_blast_radius(db, tenant_id, requirement_key)

        if not blast_radius.get('found'):
            console.print(f"[red]Requirement not found: {requirement_key}[/red]\n")
            sys.exit(1)

        if format == 'json':
            output_data = json.dumps(blast_radius, indent=2, default=str)

            if output:
                Path(output).write_text(output_data)
                console.print(f"[green]Results saved to {output}[/green]\n")
            else:
                console.print(output_data)

        else:
            # Requirement info
            console.print(f"[bold]Requirement ID:[/bold] {blast_radius['requirement_id']}")
            console.print(f"[bold]Framework:[/bold] {blast_radius['framework']}")
            console.print()

            # Summary
            summary_table = Table(title="Impact Summary", show_header=False)
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Count", style="white")

            summary_table.add_row("Affected Components", f"[red]{blast_radius['affected_components_count']}[/red]")
            summary_table.add_row("Total Violations", f"[red]{blast_radius['total_violations']}[/red]")
            summary_table.add_row("  Via CWE Mapping", str(blast_radius['cwe_violations_count']))
            summary_table.add_row("  Via Scanner Findings", str(blast_radius['direct_violations_count']))

            console.print(summary_table)
            console.print()

            # CWE violations detail
            if blast_radius['cwe_violations']:
                cwe_table = Table(title="CWE-Based Violations (Path A)")
                cwe_table.add_column("Component", style="cyan")
                cwe_table.add_column("CVE", style="red", no_wrap=True)
                cwe_table.add_column("CWE", style="magenta", no_wrap=True)
                cwe_table.add_column("CVSS", justify="right", style="white")

                for v in blast_radius['cwe_violations'][:20]:  # Limit to 20
                    comp = v.get('component', {})
                    vuln = v.get('vulnerability', {})
                    cwe = v.get('cwe', {})

                    cwe_table.add_row(
                        comp.get('name', 'N/A')[:30],
                        vuln.get('cve_id', 'N/A'),
                        cwe.get('cwe_id', 'N/A'),
                        f"{vuln.get('cvss_v3_score', 0):.1f}" if vuln.get('cvss_v3_score') else 'N/A'
                    )

                console.print(cwe_table)
                if len(blast_radius['cwe_violations']) > 20:
                    console.print(f"... and {len(blast_radius['cwe_violations']) - 20} more CWE violations")
                console.print()

            # Scanner violations detail
            if blast_radius['direct_violations']:
                scanner_table = Table(title="Scanner-Based Violations (Path B)")
                scanner_table.add_column("Component", style="cyan")
                scanner_table.add_column("Tool", style="yellow", no_wrap=True)
                scanner_table.add_column("Finding Type", style="magenta", no_wrap=True)
                scanner_table.add_column("Severity", style="red", no_wrap=True)
                scanner_table.add_column("File", style="white")

                for v in blast_radius['direct_violations'][:20]:  # Limit to 20
                    comp = v.get('component', {})
                    finding = v.get('finding', {})
                    session = v.get('scan_session', {})

                    scanner_table.add_row(
                        comp.get('name', 'N/A')[:30],
                        session.get('tool_name', 'N/A'),
                        finding.get('finding_type', 'N/A'),
                        finding.get('severity', 'N/A'),
                        finding.get('file_path', 'N/A')[:40] if finding.get('file_path') else 'N/A'
                    )

                console.print(scanner_table)
                if len(blast_radius['direct_violations']) > 20:
                    console.print(f"... and {len(blast_radius['direct_violations']) - 20} more scanner violations")
                console.print()

            if blast_radius['total_violations'] == 0:
                console.print("[green]✓ No violations found for this requirement[/green]\n")

            if output:
                Path(output).write_text(json.dumps(blast_radius, indent=2, default=str))
                console.print(f"[green]Full data saved to {output}[/green]\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Requirement query failed: {e}[/bold red]\n")
        logger.error("Requirement query failed", requirement_key=requirement_key, error=str(e))
        sys.exit(1)


# ========== Query Commands ==========

@cli.command(name='blast-radius')
@click.argument('cve_id')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.option('--output', type=click.Path(), help='Save to file')
def blast_radius(cve_id: str, format: str, output: Optional[str]):
    """
    Analyze regulatory compliance impact of a CVE.

    Traverses knowledge graph to find:
    - Related weaknesses (CWE)
    - Attack patterns (CAPEC, ATT&CK)
    - Affected regulatory controls (NIST 800-53, ISO 27001)
    - Exploit availability
    - KEV status

    Examples:
        complira blast-radius CVE-2024-1234
        complira blast-radius CVE-2024-1234 --format json
        complira blast-radius CVE-2024-1234 --output report.json
    """
    console.print(f"\n[bold cyan]Regulatory Blast Radius Analysis: {cve_id}[/bold cyan]\n")

    try:
        db = get_db()

        # Normalize CVE ID
        from .utils.keys import normalize_cve_id
        cve_key = normalize_cve_id(cve_id)

        # AQL query for blast radius
        query = """
        LET cve = DOCUMENT('vulnerabilities', @cve_key)

        // Get CWE weaknesses
        LET cwes = (
            FOR v, e IN 1..1 OUTBOUND cve has_weakness
                RETURN {
                    cwe_id: v.cwe_id,
                    name: v.name,
                    abstraction: v.abstraction
                }
        )

        // Get CAPEC attack patterns
        LET capecs = (
            FOR weakness IN cwes
                FOR v, e IN 1..1 INBOUND CONCAT('weaknesses/', weakness.cwe_id) capec_relates_to_cwe
                    RETURN DISTINCT {
                        capec_id: v.capec_id,
                        name: v.name,
                        abstraction: v.abstraction
                    }
        )

        // Get ATT&CK techniques
        LET attack_techniques = (
            FOR weakness IN cwes
                FOR v, e IN 1..2 OUTBOUND CONCAT('weaknesses/', weakness.cwe_id) ANY
                    FILTER IS_SAME_COLLECTION('attack_techniques', v)
                    RETURN DISTINCT {
                        technique_id: v.technique_id,
                        name: v.name,
                        tactic: v.tactic
                    }
        )

        // Get regulatory controls
        LET controls = (
            FOR v, e IN 1..1 OUTBOUND cve maps_to_requirement
                RETURN {
                    control_id: v.control_id OR v.cre_id OR v.scf_id,
                    name: v.name OR v.title,
                    framework: e.framework,
                    confidence: e.confidence,
                    collection: PARSE_IDENTIFIER(v._id).collection
                }
        )

        // Check KEV status
        LET kev = (
            FOR v, e IN 1..1 OUTBOUND cve exploited_in_wild
                RETURN {
                    vendor_project: v.vendor_project,
                    product: v.product,
                    due_date: v.due_date
                }
        )

        // Get exploits
        LET exploits = (
            FOR v, e IN 1..1 OUTBOUND cve has_exploit
                RETURN {
                    exploit_id: v.exploit_id OR v.edb_id OR v.msf_module,
                    name: v.name OR v.description,
                    type: PARSE_IDENTIFIER(v._id).collection
                }
        )

        // Get EPSS score
        LET epss = (
            FOR v, e IN 1..1 OUTBOUND cve has_epss_score
                SORT v.date DESC
                LIMIT 1
                RETURN {
                    epss: v.epss,
                    percentile: v.percentile,
                    date: v.date
                }
        )

        RETURN {
            cve: {
                cve_id: cve.cve_id,
                description: cve.description,
                cvss_v3_score: cve.cvss_v3_score,
                cvss_v3_vector: cve.cvss_v3_vector,
                published: cve.published
            },
            cwes: cwes,
            capecs: capecs,
            attack_techniques: attack_techniques,
            controls: controls,
            kev: LENGTH(kev) > 0 ? kev[0] : null,
            exploits: exploits,
            epss: LENGTH(epss) > 0 ? epss[0] : null,
            summary: {
                total_cwes: LENGTH(cwes),
                total_capecs: LENGTH(capecs),
                total_attack_techniques: LENGTH(attack_techniques),
                total_controls: LENGTH(controls),
                total_exploits: LENGTH(exploits),
                is_kev: LENGTH(kev) > 0,
                has_exploit: LENGTH(exploits) > 0
            }
        }
        """

        cursor = db.aql.execute(query, bind_vars={'cve_key': cve_key})
        result = next(cursor, None)

        if not result or not result.get('cve'):
            console.print(f"[red]CVE not found: {cve_id}[/red]\n")
            sys.exit(1)

        # Output results
        if format == 'json':
            output_data = json.dumps(result, indent=2, default=str)

            if output:
                Path(output).write_text(output_data)
                console.print(f"[green]Results saved to {output}[/green]\n")
            else:
                console.print(output_data)

        else:
            # Table format
            cve_data = result['cve']
            summary = result['summary']

            # CVE Info
            console.print(f"[bold]CVE ID:[/bold] {cve_data['cve_id']}")
            console.print(f"[bold]CVSS v3:[/bold] {cve_data['cvss_v3_score']}")
            console.print(f"[bold]Published:[/bold] {cve_data['published']}")
            console.print(f"\n[bold]Description:[/bold]\n{cve_data['description']}\n")

            # Summary
            summary_table = Table(title="Impact Summary", show_header=False)
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Count", style="white")

            summary_table.add_row("CWE Weaknesses", str(summary['total_cwes']))
            summary_table.add_row("CAPEC Patterns", str(summary['total_capecs']))
            summary_table.add_row("ATT&CK Techniques", str(summary['total_attack_techniques']))
            summary_table.add_row("Regulatory Controls", str(summary['total_controls']))
            summary_table.add_row("Exploits", str(summary['total_exploits']))
            summary_table.add_row("KEV Status", "[red]YES[/red]" if summary['is_kev'] else "No")

            console.print(summary_table)
            console.print()

            # KEV Warning
            if summary['is_kev']:
                kev_data = result['kev']
                console.print(f"[bold red]⚠ CISA KEV: Actively exploited in the wild![/bold red]")
                console.print(f"Vendor: {kev_data['vendor_project']}")
                console.print(f"Product: {kev_data['product']}")
                console.print(f"Due Date: {kev_data['due_date']}\n")

            # EPSS Score
            if result['epss']:
                epss_data = result['epss']
                console.print(f"[bold]EPSS Score:[/bold] {epss_data['epss']:.4f} (Percentile: {epss_data['percentile']:.2f})")
                console.print(f"Date: {epss_data['date']}\n")

            # Regulatory Controls
            if result['controls']:
                controls_table = Table(title="Affected Regulatory Controls")
                controls_table.add_column("Framework", style="cyan")
                controls_table.add_column("Control ID", style="yellow")
                controls_table.add_column("Name", style="white")
                controls_table.add_column("Confidence", style="green")

                for control in result['controls'][:10]:  # Limit to 10
                    controls_table.add_row(
                        control.get('framework', 'N/A'),
                        control.get('control_id', 'N/A'),
                        control.get('name', 'N/A')[:50],
                        f"{control.get('confidence', 0):.2f}" if control.get('confidence') else 'N/A'
                    )

                console.print(controls_table)
                console.print()

            if output:
                Path(output).write_text(json.dumps(result, indent=2, default=str))
                console.print(f"[green]Full results saved to {output}[/green]\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Query failed: {e}[/bold red]\n")
        logger.error("Blast radius query failed", cve_id=cve_id, error=str(e))
        sys.exit(1)


@cli.command(name='generate-vex')
@click.argument('sbom_path', type=click.Path(exists=True))
@click.option('--output', type=click.Path(), help='Output VEX file path')
@click.option('--format', type=click.Choice(['cyclonedx', 'csaf']), default='cyclonedx', help='VEX format')
def generate_vex(sbom_path: str, output: Optional[str], format: str):
    """
    Generate VEX (Vulnerability Exploitability eXchange) document for an SBOM.

    Analyzes SBOM components against knowledge graph to produce VEX statements.

    Examples:
        complira generate-vex sbom.json
        complira generate-vex sbom.json --output vex.json
        complira generate-vex sbom.json --format csaf
    """
    console.print(f"\n[bold cyan]Generating VEX Document[/bold cyan]\n")
    console.print(f"SBOM: {sbom_path}")
    console.print(f"Format: {format}\n")

    try:
        # Load SBOM
        sbom_data = json.loads(Path(sbom_path).read_text())

        # Extract components
        components = sbom_data.get('components', [])
        if not components:
            console.print("[red]No components found in SBOM[/red]\n")
            sys.exit(1)

        console.print(f"Found {len(components)} components\n")

        # Query vulnerabilities for components
        db = get_db()
        vex_statements = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Analyzing {len(components)} components...", total=len(components))

            for component in components:
                purl = component.get('purl')
                if not purl:
                    progress.advance(task)
                    continue

                # Query for vulnerabilities
                query = """
                FOR component IN components
                    FILTER component.purl == @purl
                    FOR vuln, e IN 1..1 INBOUND component affects_component
                        RETURN {
                            cve_id: vuln.cve_id,
                            cvss_v3_score: vuln.cvss_v3_score,
                            description: vuln.description
                        }
                """

                cursor = db.aql.execute(query, bind_vars={'purl': purl})
                vulns = list(cursor)

                if vulns:
                    vex_statements.append({
                        'component': {
                            'purl': purl,
                            'name': component.get('name'),
                            'version': component.get('version'),
                        },
                        'vulnerabilities': vulns,
                        'status': 'affected',
                    })

                progress.advance(task)

        # Generate VEX document
        vex_doc = {
            'bomFormat': 'CycloneDX',
            'specVersion': '1.5',
            'version': 1,
            'metadata': {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'tools': [{
                    'vendor': 'Complira',
                    'name': 'Knowledge Graph Engine',
                    'version': '1.0.0',
                }],
            },
            'vulnerabilities': [],
        }

        for statement in vex_statements:
            for vuln in statement['vulnerabilities']:
                vex_doc['vulnerabilities'].append({
                    'id': vuln['cve_id'],
                    'source': {'name': 'NVD'},
                    'ratings': [{
                        'score': vuln['cvss_v3_score'],
                        'severity': 'critical' if vuln['cvss_v3_score'] >= 9.0 else 'high',
                        'method': 'CVSSv3',
                    }] if vuln.get('cvss_v3_score') else [],
                    'description': vuln['description'],
                    'affects': [{
                        'ref': statement['component']['purl'],
                    }],
                })

        # Output
        vex_json = json.dumps(vex_doc, indent=2)

        if output:
            Path(output).write_text(vex_json)
            console.print(f"\n[green]✓ VEX document saved to {output}[/green]")
        else:
            console.print(vex_json)

        console.print(f"\nTotal vulnerabilities: {len(vex_doc['vulnerabilities'])}\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ VEX generation failed: {e}[/bold red]\n")
        logger.error("VEX generation failed", sbom_path=sbom_path, error=str(e))
        sys.exit(1)


@cli.command()
@click.argument('aql_query')
@click.option('--format', type=click.Choice(['table', 'json']), default='json', help='Output format')
@click.option('--output', type=click.Path(), help='Save to file')
def query(aql_query: str, format: str, output: Optional[str]):
    """
    Execute AQL query against knowledge graph.

    Examples:
        complira query "FOR v IN vulnerabilities LIMIT 10 RETURN v"
        complira query "FOR v IN vulnerabilities FILTER v.cvss_v3_score >= 9.0 RETURN v.cve_id"
    """
    console.print(f"\n[bold cyan]Executing AQL Query[/bold cyan]\n")

    try:
        db = get_db()
        cursor = db.aql.execute(aql_query)
        results = list(cursor)

        if format == 'json':
            output_data = json.dumps(results, indent=2, default=str)

            if output:
                Path(output).write_text(output_data)
                console.print(f"[green]Results saved to {output}[/green]\n")
            else:
                console.print(output_data)

        else:
            # Simple table format
            if results:
                console.print(f"Found {len(results)} results:\n")
                for i, result in enumerate(results[:20], 1):  # Limit to 20
                    console.print(f"{i}. {result}")
                if len(results) > 20:
                    console.print(f"\n... and {len(results) - 20} more")
            else:
                console.print("No results found")

        console.print()

    except Exception as e:
        console.print(f"\n[bold red]✗ Query failed: {e}[/bold red]\n")
        sys.exit(1)


# ========== System Commands ==========

@cli.command()
def status():
    """
    Check system health and display statistics.

    Shows:
    - Database connection status
    - Collection counts
    - Recent ingestion activity
    - System metrics
    """
    console.print("\n[bold cyan]Complira Knowledge Graph - System Status[/bold cyan]\n")

    try:
        # Health check
        is_healthy, message = health_check()

        if not is_healthy:
            console.print(f"[bold red]✗ Health check failed: {message}[/bold red]\n")
            sys.exit(1)

        console.print(f"[green]✓ Database connection: OK[/green]")

        # Get database
        db = get_db()
        settings = get_settings()

        console.print(f"Database: {settings.ARANGO_URL} / {settings.ARANGO_DATABASE}\n")

        # Collection statistics
        collections_table = Table(title="Document Collections")
        collections_table.add_column("Collection", style="cyan")
        collections_table.add_column("Count", style="white", justify="right")

        doc_collections = [
            'vulnerabilities', 'weaknesses', 'kev_entries', 'vulncheck_kev_entries',
            'exploit_modules', 'epss_history', 'attack_techniques', 'attack_patterns',
            'atlas_techniques', 'd3fend_techniques', 'threat_groups', 'regulatory_requirements',
            'oscal_controls', 'scf_controls', 'opencre_nodes', 'components', 'cpe_entries',
            'scorecard_results', 'licenses', 'package_health',
        ]

        total_docs = 0
        for coll_name in sorted(doc_collections):
            if db.has_collection(coll_name):
                count = db.collection(coll_name).count()
                total_docs += count
                collections_table.add_row(coll_name, f"{count:,}")

        console.print(collections_table)
        console.print(f"\n[bold]Total Documents:[/bold] {total_docs:,}\n")

        # Edge statistics
        edges_table = Table(title="Edge Collections")
        edges_table.add_column("Edge Type", style="cyan")
        edges_table.add_column("Count", style="white", justify="right")

        edge_collections = [
            'has_weakness', 'has_exploit', 'affects', 'maps_to_requirement', 'violates_requirement',
            'exploited_in_wild', 'has_epss', 'capec_relates_to_cwe',
            'capec_child_of', 'd3fend_counters_technique', 'atlas_maps_to_attack', 'aliases',
            'technique_exploits_weakness', 'capec_maps_to_attack', 'technique_mitigated_by_control',
            'child_of', 'peer_of', 'can_precede', 'requires',
            'cross_framework_mapping', 'opencre_links', 'depends_on', 'matched_by_cpe',
            'same_as', 'scored_by', 'licensed_under',
        ]

        total_edges = 0
        for edge_name in sorted(edge_collections):
            if db.has_collection(edge_name):
                count = db.collection(edge_name).count()
                total_edges += count
                edges_table.add_row(edge_name, f"{count:,}")

        console.print(edges_table)
        console.print(f"\n[bold]Total Edges:[/bold] {total_edges:,}\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Status check failed: {e}[/bold red]\n")
        sys.exit(1)


@cli.command()
@click.confirmation_option(prompt='Initialize database schema? This will create collections.')
def init():
    """
    Initialize database schema.

    Creates all document and edge collections with indexes.
    Safe to run multiple times (idempotent).
    """
    console.print("\n[bold cyan]Initializing Database Schema[/bold cyan]\n")

    try:
        db = get_db()
        init_schema(db)

        console.print("[green]✓ Database schema initialized successfully[/green]\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Initialization failed: {e}[/bold red]\n")
        sys.exit(1)


# ========== Analysis and Reporting Commands ==========

@cli.command()
@click.option('--format', 'output_format', type=click.Choice(['text', 'json', 'markdown']), default='text', help='Output format')
def report(output_format: str):
    """
    Generate prioritized vulnerability patching report.

    Analyzes CISA-enriched vulnerabilities to create risk-based
    prioritization using KEV status, SSVC scores, and CVSS severity.

    Examples:
        complira report
        complira report --format json
        complira report --format markdown > report.md
    """
    from .agents.analysis import CISAReportAgent

    try:
        db = get_db()
        agent = CISAReportAgent(db, output_format=output_format)

        if output_format == 'text':
            console.print("\n[bold cyan]Generating CISA Vulnerability Prioritization Report[/bold cyan]\n")

        result = agent.run()

        if result['status'] == 'success':
            # Print the formatted output
            print(result['output'])

            if output_format == 'text':
                console.print(f"\n[green]✓ Report generated in {result['execution_time_seconds']:.1f}s[/green]\n")
        else:
            console.print(f"\n[bold red]✗ Report generation failed: {result.get('error')}[/bold red]\n")
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[bold red]✗ Report generation failed: {e}[/bold red]\n")
        sys.exit(1)


@cli.command()
@click.option('--format', 'output_format', type=click.Choice(['text', 'json', 'markdown']), default='text', help='Output format')
def analyze(output_format: str):
    """
    Analyze CISA-enriched vulnerability data.

    Provides comprehensive analysis including KEV status, SSVC scores,
    exploitation trends, and technical impact distribution.

    Examples:
        complira analyze
        complira analyze --format json
        complira analyze --format markdown > analysis.md
    """
    from .agents.analysis import VulnerabilityAnalysisAgent

    try:
        db = get_db()
        agent = VulnerabilityAnalysisAgent(db, output_format=output_format)

        if output_format == 'text':
            console.print("\n[bold cyan]Analyzing CISA-Enriched Vulnerability Data[/bold cyan]\n")

        result = agent.run()

        if result['status'] == 'success':
            # Print the formatted output
            print(result['output'])

            if output_format == 'text':
                console.print(f"\n[green]✓ Analysis completed in {result['execution_time_seconds']:.1f}s[/green]\n")
        else:
            console.print(f"\n[bold red]✗ Analysis failed: {result.get('error')}[/bold red]\n")
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[bold red]✗ Analysis failed: {e}[/bold red]\n")
        sys.exit(1)


# ========== Schedule Commands ==========

@cli.group()
def schedule():
    """
    Manage Prefect schedules.
    """
    pass


@schedule.command(name='deploy')
@click.option('--work-pool', default='default-agent-pool', help='Prefect work pool name')
@click.option('--work-queue', default='default', help='Prefect work queue name')
def deploy_schedule(work_pool: str, work_queue: str):
    """
    Deploy Prefect schedules for automated updates.

    Examples:
        complira schedule deploy
        complira schedule deploy --work-pool my-pool
    """
    console.print("\n[bold cyan]Deploying Prefect Schedules[/bold cyan]\n")

    try:
        deploy_schedules(work_pool=work_pool, work_queue=work_queue)

        console.print("\n[green]✓ Schedules deployed successfully[/green]")
        console.print("\nNext steps:")
        console.print("  1. Start Prefect server: prefect server start")
        console.print(f"  2. Start agent: prefect agent start -p {work_pool}")
        console.print("  3. View schedules: prefect deployment ls\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Deployment failed: {e}[/bold red]\n")
        sys.exit(1)


@schedule.command(name='show')
def show_schedule():
    """
    Show configured schedules.
    """
    show_schedules()


# ========== Entry Point ==========

def main():
    """CLI entry point."""
    cli()


if __name__ == '__main__':
    main()
