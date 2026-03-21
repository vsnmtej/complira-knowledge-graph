"""
Scheduler for Knowledge Graph Incremental Updates.

Defines Prefect schedules and deployments for periodic data ingestion:
- Hourly: KEV (Known Exploited Vulnerabilities)
- 2-hour: NVD (CVE updates)
- Daily: EPSS, OSV, GHSA (vulnerability enrichment)
- Weekly: Foundation data (ATT&CK, CAPEC, CWE, etc.)

Uses Prefect 3.x deployments with cron schedules.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import structlog

from prefect import flow

from .seed import execute_incremental_update, execute_seed_dag
from ..config import get_settings

logger = structlog.get_logger()


# ========== Schedule Definitions ==========

SCHEDULE_CONFIGS: Dict[str, Dict] = {
    # Critical: Hourly updates
    'kev_hourly': {
        'name': 'KEV Hourly Update',
        'cron': '0 * * * *',  # Top of every hour
        'agents': ['KEVAgent'],
        'description': 'CISA Known Exploited Vulnerabilities (hourly)',
    },

    # High-frequency: Every 2 hours
    'nvd_2hour': {
        'name': 'NVD 2-Hour Update',
        'cron': '0 */2 * * *',  # Every 2 hours
        'agents': ['NVDAgent'],
        'description': 'National Vulnerability Database CVEs (2-hour)',
    },

    # Daily updates: 3 AM UTC
    'vulnerability_daily': {
        'name': 'Vulnerability Data Daily Update',
        'cron': '0 3 * * *',  # 3 AM UTC daily
        'agents': ['EPSSAgent', 'OSVAgent', 'GHSAAgent', 'VulnrichmentAgent'],
        'description': 'EPSS scores, OSV, GitHub Security Advisories (daily)',
    },

    # Daily updates: 4 AM UTC (after vulnerabilities)
    'exploits_daily': {
        'name': 'Exploit Data Daily Update',
        'cron': '0 4 * * *',  # 4 AM UTC daily
        'agents': ['MetasploitAgent', 'ExploitDBAgent', 'NucleiAgent', 'PoCInGitHubAgent'],
        'description': 'Exploit databases and PoCs (daily)',
    },

    # Daily updates: 5 AM UTC
    'components_daily': {
        'name': 'Component Data Daily Update',
        'cron': '0 5 * * *',  # 5 AM UTC daily
        'agents': ['DepsDevAgent', 'EcosystemsAgent', 'EndOfLifeAgent', 'ScorecardAgent'],
        'description': 'Package metadata and security scorecards (daily)',
    },

    # Weekly updates: Sunday 2 AM UTC
    'foundation_weekly': {
        'name': 'Foundation Data Weekly Update',
        'cron': '0 2 * * 0',  # Sunday 2 AM UTC
        'agents': [
            'CWEAgent',
            'ATTACKAgent',
            'CAPECAgent',
            'D3FENDAgent',
            'ATLASAgent',
            'OSCALAgent',
            'SCFAgent',
            'OpenCREAgent',
        ],
        'description': 'Foundation taxonomies and frameworks (weekly)',
    },

    # Weekly updates: Sunday 6 AM UTC
    'llm_enrichment_weekly': {
        'name': 'LLM Enrichment Weekly Update',
        'cron': '0 6 * * 0',  # Sunday 6 AM UTC
        'agents': [
            'CWEClassifierAgent',
            'PURLtoCPEAgent',
            'VEXSynthesizerAgent',
            'RegulatoryMapperAgent',
            'CVEEntityExtractorAgent',
        ],
        'description': 'LLM-based enrichment agents (weekly)',
    },

    # Monthly: Full reseed on 1st of month at 1 AM UTC
    'full_seed_monthly': {
        'name': 'Full Seed Monthly',
        'cron': '0 1 1 * *',  # 1st of month, 1 AM UTC
        'agents': None,  # Uses full seed workflow
        'description': 'Complete knowledge graph reseed (monthly)',
    },
}


# ========== Prefect Flow Wrappers ==========

@flow(name="scheduled_incremental_update")
def scheduled_incremental_update(schedule_name: str) -> Dict:
    """
    Wrapper flow for scheduled incremental updates.

    Args:
        schedule_name: Key from SCHEDULE_CONFIGS

    Returns:
        dict: Execution statistics
    """
    config = SCHEDULE_CONFIGS.get(schedule_name)

    if not config:
        raise ValueError(f"Unknown schedule: {schedule_name}")

    logger.info(
        "Starting scheduled update",
        schedule_name=schedule_name,
        agents=config['agents'],
    )

    # Execute incremental update
    result = execute_incremental_update(agents=config['agents'])

    logger.info(
        "Scheduled update completed",
        schedule_name=schedule_name,
        status=result.get('status'),
        agents_executed=result.get('agents_executed'),
    )

    return result


@flow(name="scheduled_full_seed")
def scheduled_full_seed(skip_llm: bool = False) -> Dict:
    """
    Wrapper flow for scheduled full seed.

    Args:
        skip_llm: Skip LLM enrichment agents

    Returns:
        dict: Execution statistics
    """
    logger.info("Starting scheduled full seed", skip_llm=skip_llm)

    result = execute_seed_dag(skip_llm=skip_llm)

    logger.info(
        "Scheduled full seed completed",
        status=result.get('status'),
        total_agents=result.get('total_agents_executed'),
        execution_time=result.get('total_execution_time_seconds'),
    )

    return result


# ========== Deployment Management ==========

def deploy_all_schedules(
    work_pool_name: str = "default-agent-pool",
    work_queue_name: str = "default",
) -> None:
    """
    Instructions for deploying schedules to Prefect server.

    Note: In Prefect 3.x, use `prefect deploy` or `flow.serve()`/`flow.deploy()`.

    Args:
        work_pool_name: Prefect work pool name
        work_queue_name: Prefect work queue name
    """
    logger.info("Schedule deployment information")

    print("\nTo deploy schedules in Prefect 3.x, use one of these methods:")
    print("\n1. Using prefect.yaml (recommended):")
    print("   Create a prefect.yaml file with your deployment configuration")
    print("   Then run: prefect deploy")
    print("\n2. Using flow.serve() for development:")
    print("   Run flows directly with: python -m complira_graph.orchestrator.scheduler")
    print("\n3. Using flow.deploy() programmatically:")
    print("   Call flow.deploy() in your code with schedule configuration")
    print(f"\nConfigured schedules: {len(SCHEDULE_CONFIGS)}")

    for schedule_key, config in SCHEDULE_CONFIGS.items():
        print(f"\n  - {config['name']}")
        print(f"    Cron: {config['cron']}")
        print(f"    Description: {config['description']}")

    logger.info(
        "Schedule information displayed",
        total_schedules=len(SCHEDULE_CONFIGS),
    )


# ========== Schedule Information ==========

def print_schedule_summary() -> None:
    """
    Print summary of all configured schedules.
    """
    print("=" * 80)
    print("KNOWLEDGE GRAPH UPDATE SCHEDULES")
    print("=" * 80)
    print()

    for schedule_key, config in SCHEDULE_CONFIGS.items():
        cron = config['schedule'].cron
        agents = config.get('agents')

        print(f"{config['name']}")
        print(f"  Schedule: {cron}")
        print(f"  Description: {config['description']}")

        if agents:
            print(f"  Agents ({len(agents)}):")
            for agent in agents:
                print(f"    • {agent}")
        else:
            print(f"  Agents: Full seed workflow (all agents)")

        print()

    print("=" * 80)


def get_next_run_times(hours: int = 24) -> Dict[str, datetime]:
    """
    Calculate next run times for all schedules.

    Args:
        hours: Look ahead window in hours

    Returns:
        dict: Schedule name -> next run time
    """
    from croniter import croniter

    now = datetime.utcnow()
    next_runs = {}

    for schedule_key, config in SCHEDULE_CONFIGS.items():
        cron = config['cron']
        iter = croniter(cron, now)
        next_run = iter.get_next(datetime)

        if next_run <= now + timedelta(hours=hours):
            next_runs[config['name']] = next_run

    return next_runs


# ========== CLI Entry Points ==========

def deploy_schedules(
    work_pool: str = "default-agent-pool",
    work_queue: str = "default",
) -> None:
    """
    CLI entry point for displaying schedule deployment information.

    Args:
        work_pool: Prefect work pool name (for reference)
        work_queue: Prefect work queue name (for reference)
    """
    print("\n" + "=" * 80)
    print("COMPLIRA KNOWLEDGE GRAPH - SCHEDULE DEPLOYMENT")
    print("=" * 80)

    deploy_all_schedules(work_pool_name=work_pool, work_queue_name=work_queue)

    print("\n" + "=" * 80)
    print("For manual workflow execution, use:")
    print("  complira seed              # Full seed workflow")
    print("  complira incremental       # Incremental updates")
    print("=" * 80 + "\n")


def show_schedules() -> None:
    """
    CLI entry point for displaying schedule information.
    """
    print_schedule_summary()

    print()
    print("NEXT RUN TIMES (24 hours)")
    print("=" * 80)

    next_runs = get_next_run_times(hours=24)

    if next_runs:
        for schedule_name, run_time in sorted(next_runs.items(), key=lambda x: x[1]):
            time_until = run_time - datetime.utcnow()
            hours_until = time_until.total_seconds() / 3600

            print(f"{schedule_name}")
            print(f"  Next run: {run_time.isoformat()} UTC (in {hours_until:.1f} hours)")
            print()
    else:
        print("No schedules in next 24 hours")

    print("=" * 80)


if __name__ == '__main__':
    # Run when executed directly
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'deploy':
        # Deploy schedules
        deploy_schedules()
    else:
        # Show schedules
        show_schedules()
