"""
Orchestration Layer for Knowledge Graph Population.

Provides workflow orchestration, dependency management, and scheduling
for all data ingestion and enrichment agents.

Modules:
- dag: DAG builder with topological sorting (Kahn's algorithm)
- seed: Prefect workflows for full seed and incremental updates
- scheduler: Cron schedules and Prefect deployments

Usage:
    # Full seed workflow
    from complira_graph.orchestrator import execute_seed_dag
    result = execute_seed_dag(skip_llm=False)

    # Incremental update
    from complira_graph.orchestrator import execute_incremental_update
    result = execute_incremental_update(agents=['NVDAgent', 'KEVAgent'])

    # Deploy schedules
    from complira_graph.orchestrator import deploy_schedules
    deploy_schedules()
"""

from .dag import DAGBuilder, get_execution_order, validate_dependencies
from .seed import execute_seed_dag, execute_incremental_update, seed_graph, incremental_update
from .scheduler import (
    deploy_schedules,
    show_schedules,
    scheduled_incremental_update,
    scheduled_full_seed,
    SCHEDULE_CONFIGS,
)

__all__ = [
    # DAG
    'DAGBuilder',
    'get_execution_order',
    'validate_dependencies',

    # Seed workflows
    'execute_seed_dag',
    'execute_incremental_update',
    'seed_graph',
    'incremental_update',

    # Scheduler
    'deploy_schedules',
    'show_schedules',
    'scheduled_incremental_update',
    'scheduled_full_seed',
    'SCHEDULE_CONFIGS',
]
