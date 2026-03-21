"""
Seed Workflow - Initial Knowledge Graph Population.

Orchestrates the execution of all data ingestion and enrichment agents
in dependency order using Prefect 3.x.

Workflow:
1. Execute deterministic agents in batches (parallel where possible)
2. Execute LLM enrichment agents sequentially (after deterministic data)
3. Track execution metrics and failures
4. Provide resumability on failure
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio
import structlog

from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner

from .dag import DAGBuilder, get_execution_order
from ..db import get_db, init_schema
from ..config import get_settings

# Import all agents
from ..agents.cwe import CWEAgent
from ..agents.attack import ATTACKAgent
from ..agents.capec import CAPECAgent
from ..agents.d3fend import D3FENDAgent
from ..agents.atlas import ATLASAgent
from ..agents.spdx_licenses import SPDXLicensesAgent
from ..agents.oscal import OSCALAgent
from ..agents.scf import SCFAgent
from ..agents.opencre import OpenCREAgent
from ..agents.cpe import CPEAgent
from ..agents.nvd import NVDAgent
from ..agents.osv import OSVAgent
from ..agents.ghsa import GHSAAgent
from ..agents.epss import EPSSAgent
from ..agents.kev import KEVAgent
from ..agents.vulncheck_kev import VulnCheckKEVAgent
from ..agents.vulnrichment import VulnrichmentAgent
from ..agents.cisa_adp import CISAADPAgent
from ..agents.metasploit import MetasploitAgent
from ..agents.exploitdb import ExploitDBAgent
from ..agents.nuclei import NucleiAgent
from ..agents.poc_in_github import PoCInGitHubAgent
from ..agents.deps_dev import DepsDevAgent
from ..agents.ecosystems import EcosystemsAgent
from ..agents.endoflife import EndOfLifeAgent
from ..agents.scorecard import ScorecardAgent

# LLM agents
from ..llm_agents.cwe_classifier import CWEClassifierAgent
from ..llm_agents.purl_to_cpe import PURLtoCPEAgent
from ..llm_agents.vex_synthesizer_v2 import VEXSynthesizerV2
from ..llm_agents.regulatory_mapper import RegulatoryMapperAgent
from ..llm_agents.cve_entity_extractor import CVEEntityExtractorAgent

# Alias for backward compatibility
VEXSynthesizerAgent = VEXSynthesizerV2

logger = structlog.get_logger()


# ========== Agent Registry ==========

AGENT_REGISTRY: Dict[str, type] = {
    # Foundation agents
    'CWEAgent': CWEAgent,
    'ATTACKAgent': ATTACKAgent,
    'CAPECAgent': CAPECAgent,
    'D3FENDAgent': D3FENDAgent,
    'ATLASAgent': ATLASAgent,
    'SPDXLicensesAgent': SPDXLicensesAgent,
    'OSCALAgent': OSCALAgent,
    'SCFAgent': SCFAgent,
    'OpenCREAgent': OpenCREAgent,

    # Vulnerability agents
    'NVDAgent': NVDAgent,
    'CPEAgent': CPEAgent,
    'OSVAgent': OSVAgent,
    'GHSAAgent': GHSAAgent,
    'EPSSAgent': EPSSAgent,
    'KEVAgent': KEVAgent,
    'VulnCheckKEVAgent': VulnCheckKEVAgent,
    'CISAADPAgent': CISAADPAgent,
    'VulnrichmentAgent': VulnrichmentAgent,

    # Exploit agents
    'MetasploitAgent': MetasploitAgent,
    'ExploitDBAgent': ExploitDBAgent,
    'NucleiAgent': NucleiAgent,
    'PoCInGitHubAgent': PoCInGitHubAgent,

    # Component agents
    'DepsDevAgent': DepsDevAgent,
    'EcosystemsAgent': EcosystemsAgent,
    'EndOfLifeAgent': EndOfLifeAgent,
    'ScorecardAgent': ScorecardAgent,

    # LLM agents
    'CWEClassifierAgent': CWEClassifierAgent,
    'PURLtoCPEAgent': PURLtoCPEAgent,
    'VEXSynthesizerAgent': VEXSynthesizerAgent,
    'RegulatoryMapperAgent': RegulatoryMapperAgent,
    'CVEEntityExtractorAgent': CVEEntityExtractorAgent,
}


# ========== Prefect Tasks ==========

@task(name="run_agent", retries=2, retry_delay_seconds=60)
def run_agent(agent_name: str, db_config: Dict) -> Dict[str, Any]:
    """
    Execute a single agent.

    Args:
        agent_name: Name of agent class
        db_config: Database configuration

    Returns:
        dict: Execution statistics

    Raises:
        Exception: On agent failure (after retries)
    """
    logger.info("Starting agent execution", agent=agent_name)

    try:
        # Get database connection
        db = get_db()

        # Instantiate agent
        agent_class = AGENT_REGISTRY[agent_name]

        # Check if LLM agent (requires anthropic_client)
        if agent_name.endswith('Agent') and agent_name in ['CWEClassifierAgent', 'PURLtoCPEAgent', 'VEXSynthesizerAgent', 'RegulatoryMapperAgent', 'CVEEntityExtractorAgent']:
            # LLM agent - needs anthropic client
            import anthropic
            settings = get_settings()
            anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            agent = agent_class(db, anthropic_client)
        else:
            # Deterministic agent - only needs db
            agent = agent_class(db)

        # Run agent
        start_time = datetime.now()
        result = agent.run()
        execution_time = (datetime.now() - start_time).total_seconds()

        logger.info(
            "Agent execution completed",
            agent=agent_name,
            status=result.get('status'),
            execution_time=execution_time,
            **{k: v for k, v in result.items() if k not in ['agent', 'status']},
        )

        return result

    except Exception as e:
        logger.error(
            "Agent execution failed",
            agent=agent_name,
            error=str(e),
        )
        raise


@task(name="initialize_database")
def initialize_database() -> bool:
    """
    Initialize database schema.

    Returns:
        bool: True if successful
    """
    logger.info("Initializing database schema")

    try:
        db = get_db()
        init_schema(db)

        logger.info("Database schema initialized successfully")
        return True

    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        raise


# ========== Prefect Flows ==========

@flow(
    name="seed_knowledge_graph",
    description="Populate knowledge graph with all data sources",
    task_runner=ConcurrentTaskRunner(),
)
def execute_seed_dag(
    skip_llm: bool = False,
    llm_batch_size: Optional[int] = None,
    max_concurrent: int = 4,
) -> Dict[str, Any]:
    """
    Execute complete seed workflow with all agents.

    Args:
        skip_llm: Skip LLM enrichment agents (default: False)
        llm_batch_size: Override batch size for LLM agents
        max_concurrent: Max concurrent agents (default: 4)

    Returns:
        dict: Workflow execution statistics

    Workflow Steps:
        1. Initialize database schema
        2. Execute deterministic agents in batches (parallel)
        3. Execute LLM agents sequentially (optional)
        4. Aggregate statistics
    """
    logger.info(
        "Starting seed workflow",
        skip_llm=skip_llm,
        max_concurrent=max_concurrent,
    )

    workflow_start = datetime.now()

    # Step 1: Initialize database
    initialize_database()

    # Step 2: Build execution DAG
    dag_builder = DAGBuilder()
    batches = dag_builder.build()

    logger.info(
        "Execution plan ready",
        total_batches=len(batches),
        total_agents=sum(len(batch) for batch in batches),
    )

    # Get database config for tasks
    settings = get_settings()
    db_config = {
        'url': settings.ARANGO_URL,
        'database': settings.ARANGO_DATABASE,
        'password': settings.ARANGO_PASSWORD,
    }

    # Step 3: Execute deterministic agents in batches
    all_results = []

    for batch_num, batch in enumerate(batches, 1):
        # Filter out LLM agents if skip_llm=True
        if skip_llm:
            batch = [a for a in batch if a not in [
                'CWEClassifierAgent', 'PURLtoCPEAgent', 'VEXSynthesizerAgent',
                'RegulatoryMapperAgent', 'CVEEntityExtractorAgent'
            ]]

        if not batch:
            continue

        logger.info(
            f"Executing batch {batch_num}/{len(batches)}",
            agents=batch,
            batch_size=len(batch),
        )

        # Execute batch in parallel (up to max_concurrent)
        # Use Prefect's task concurrency
        batch_results = []
        for agent_name in batch:
            future = run_agent.submit(agent_name, db_config)
            batch_results.append((agent_name, future))

        # Wait for batch completion
        for agent_name, future in batch_results:
            try:
                result = future.result()
                all_results.append(result)
            except Exception as e:
                logger.error(
                    "Agent failed in batch",
                    agent=agent_name,
                    batch=batch_num,
                    error=str(e),
                )
                # Continue with other agents (don't fail entire batch)

    # Step 4: Aggregate statistics
    workflow_end = datetime.now()
    total_execution_time = (workflow_end - workflow_start).total_seconds()

    stats = {
        'workflow': 'seed_knowledge_graph',
        'status': 'completed',
        'total_execution_time_seconds': total_execution_time,
        'total_agents_executed': len(all_results),
        'successful_agents': len([r for r in all_results if r.get('status') == 'success']),
        'failed_agents': len([r for r in all_results if r.get('status') == 'failed']),
        'total_records_created': sum(r.get('created', 0) for r in all_results if isinstance(r.get('created'), int)),
        'total_records_updated': sum(r.get('updated', 0) for r in all_results if isinstance(r.get('updated'), int)),
        'agent_results': all_results,
        'started_at': workflow_start.isoformat(),
        'completed_at': workflow_end.isoformat(),
    }

    logger.info(
        "Seed workflow completed",
        **{k: v for k, v in stats.items() if k != 'agent_results'},
    )

    return stats


@flow(name="seed_incremental")
def execute_incremental_update(agents: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Execute incremental update for specific agents.

    Args:
        agents: List of agent names to run (default: high-frequency agents)

    Returns:
        dict: Execution statistics

    Default High-Frequency Agents:
        - NVDAgent (CVE updates)
        - KEVAgent (Known exploited vulnerabilities)
        - EPSSAgent (Daily EPSS scores)
        - GHSAAgent (GitHub advisories)
    """
    if agents is None:
        # Default: high-frequency update agents
        agents = ['NVDAgent', 'KEVAgent', 'EPSSAgent', 'GHSAAgent']

    logger.info("Starting incremental update", agents=agents)

    settings = get_settings()
    db_config = {
        'url': settings.ARANGO_URL,
        'database': settings.ARANGO_DATABASE,
        'password': settings.ARANGO_PASSWORD,
    }

    # Execute agents sequentially (no dependencies for incremental)
    results = []
    for agent_name in agents:
        try:
            result = run_agent(agent_name, db_config)
            results.append(result)
        except Exception as e:
            logger.error(
                "Incremental update agent failed",
                agent=agent_name,
                error=str(e),
            )

    stats = {
        'workflow': 'incremental_update',
        'status': 'completed',
        'agents_executed': len(results),
        'successful': len([r for r in results if r.get('status') == 'success']),
        'failed': len([r for r in results if r.get('status') == 'failed']),
        'results': results,
    }

    logger.info("Incremental update completed", **{k: v for k, v in stats.items() if k != 'results'})

    return stats


# ========== CLI Entry Points ==========

def seed_graph(skip_llm: bool = False):
    """
    CLI entry point for seeding the knowledge graph.

    Args:
        skip_llm: Skip LLM enrichment agents
    """
    result = execute_seed_dag(skip_llm=skip_llm)
    return result


def incremental_update(agents: List[str] = None):
    """
    CLI entry point for incremental updates.

    Args:
        agents: List of agent names
    """
    result = execute_incremental_update(agents=agents)
    return result


if __name__ == '__main__':
    # Run seed workflow when executed directly
    import sys

    skip_llm = '--skip-llm' in sys.argv

    print("Starting knowledge graph seed workflow...")
    print(f"Skip LLM agents: {skip_llm}")
    print("")

    result = seed_graph(skip_llm=skip_llm)

    print("")
    print("=" * 80)
    print("SEED WORKFLOW COMPLETED")
    print("=" * 80)
    print(f"Total Execution Time: {result['total_execution_time_seconds']:.2f} seconds")
    print(f"Agents Executed: {result['total_agents_executed']}")
    print(f"Successful: {result['successful_agents']}")
    print(f"Failed: {result['failed_agents']}")
    print(f"Records Created: {result['total_records_created']:,}")
    print(f"Records Updated: {result['total_records_updated']:,}")
    print("=" * 80)
