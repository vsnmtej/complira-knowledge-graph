"""
Monitoring and Observability Layer.

Provides metrics, logging, and health monitoring for the knowledge graph engine.

Modules:
- metrics: Prometheus metrics for monitoring
- logging: Structured logging with structlog

Usage:
    # Start metrics server
    from complira_graph.monitoring import start_metrics_server
    start_metrics_server(port=9090)

    # Configure logging
    from complira_graph.monitoring import configure_logging, get_logger
    configure_logging(level='INFO', json_output=True)
    logger = get_logger(__name__)

    # Record metrics
    from complira_graph.monitoring import record_agent_execution
    record_agent_execution('CWEAgent', 45.2, 'success', records_created=1000)
"""

from .metrics import (
    start_metrics_server,
    record_agent_execution,
    record_llm_call,
    record_llm_enrichment,
    record_db_query,
    record_circuit_breaker_state,
    record_circuit_breaker_event,
    record_http_request,
    record_rate_limit_delay,
    record_workflow_execution,
    update_db_collection_stats,
    update_health_metrics,
    track_agent_execution,
    track_db_query,
)

from .logging import (
    configure_logging,
    configure_production_logging,
    configure_development_logging,
    get_logger,
    LogContext,
    with_log_context,
    log_agent_start,
    log_agent_complete,
    log_agent_error,
    log_llm_call,
    log_circuit_breaker_event,
    AuditLogger,
)

__all__ = [
    # Metrics
    'start_metrics_server',
    'record_agent_execution',
    'record_llm_call',
    'record_llm_enrichment',
    'record_db_query',
    'record_circuit_breaker_state',
    'record_circuit_breaker_event',
    'record_http_request',
    'record_rate_limit_delay',
    'record_workflow_execution',
    'update_db_collection_stats',
    'update_health_metrics',
    'track_agent_execution',
    'track_db_query',

    # Logging
    'configure_logging',
    'configure_production_logging',
    'configure_development_logging',
    'get_logger',
    'LogContext',
    'with_log_context',
    'log_agent_start',
    'log_agent_complete',
    'log_agent_error',
    'log_llm_call',
    'log_circuit_breaker_event',
    'AuditLogger',
]
