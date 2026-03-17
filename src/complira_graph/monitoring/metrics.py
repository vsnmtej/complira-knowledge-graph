"""
Prometheus Metrics for Knowledge Graph Monitoring.

Provides instrumentation for:
- Agent execution (duration, records processed, failures)
- LLM usage (tokens, costs, API calls)
- Database operations (query performance, connection pool)
- Circuit breaker state
- System health

Exports metrics on :9090/metrics for Prometheus scraping.
"""

from typing import Dict, Any, Optional
import time
from functools import wraps
from contextlib import contextmanager

import structlog
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    Info,
    start_http_server,
    REGISTRY,
)

logger = structlog.get_logger()


# ========== Agent Metrics ==========

# Agent execution
agent_runs_total = Counter(
    'complira_agent_runs_total',
    'Total number of agent executions',
    ['agent_name', 'status'],  # status: success, failed
)

agent_duration_seconds = Histogram(
    'complira_agent_duration_seconds',
    'Agent execution duration in seconds',
    ['agent_name'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],  # 1s to 1h
)

agent_records_processed = Counter(
    'complira_agent_records_processed_total',
    'Total records processed by agents',
    ['agent_name', 'operation'],  # operation: created, updated, skipped
)

agent_errors_total = Counter(
    'complira_agent_errors_total',
    'Total agent execution errors',
    ['agent_name', 'error_type'],
)

agent_last_success_timestamp = Gauge(
    'complira_agent_last_success_timestamp',
    'Unix timestamp of last successful agent run',
    ['agent_name'],
)


# ========== LLM Metrics ==========

llm_api_calls_total = Counter(
    'complira_llm_api_calls_total',
    'Total LLM API calls',
    ['agent_name', 'model', 'status'],  # status: success, failed
)

llm_tokens_total = Counter(
    'complira_llm_tokens_total',
    'Total tokens consumed by LLM',
    ['agent_name', 'model', 'token_type'],  # token_type: input, output
)

llm_api_duration_seconds = Histogram(
    'complira_llm_api_duration_seconds',
    'LLM API call duration',
    ['agent_name', 'model'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
)

llm_cost_dollars = Counter(
    'complira_llm_cost_dollars_total',
    'Total LLM API cost in USD',
    ['agent_name', 'model'],
)

llm_confidence_score = Histogram(
    'complira_llm_confidence_score',
    'LLM output confidence scores',
    ['agent_name', 'model'],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0],
)

llm_enrichments_total = Counter(
    'complira_llm_enrichments_total',
    'Total LLM enrichments created',
    ['agent_name', 'enrichment_type'],
)


# ========== Database Metrics ==========

db_queries_total = Counter(
    'complira_db_queries_total',
    'Total database queries',
    ['query_type', 'status'],  # query_type: aql, insert, update, delete
)

db_query_duration_seconds = Histogram(
    'complira_db_query_duration_seconds',
    'Database query duration',
    ['query_type'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10],
)

db_connections_active = Gauge(
    'complira_db_connections_active',
    'Active database connections',
)

db_collections_count = Gauge(
    'complira_db_collections_count',
    'Number of collections in database',
)

db_documents_total = Gauge(
    'complira_db_documents_total',
    'Total documents in database',
    ['collection'],
)

db_edges_total = Gauge(
    'complira_db_edges_total',
    'Total edges in database',
    ['edge_type'],
)


# ========== Circuit Breaker Metrics ==========

circuit_breaker_state = Gauge(
    'complira_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['service'],
)

circuit_breaker_failures_total = Counter(
    'complira_circuit_breaker_failures_total',
    'Total circuit breaker failures',
    ['service'],
)

circuit_breaker_successes_total = Counter(
    'complira_circuit_breaker_successes_total',
    'Total circuit breaker successes',
    ['service'],
)


# ========== HTTP Client Metrics ==========

http_requests_total = Counter(
    'complira_http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'status_code'],
)

http_request_duration_seconds = Histogram(
    'complira_http_request_duration_seconds',
    'HTTP request duration',
    ['service', 'method'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)

http_rate_limit_delays_total = Counter(
    'complira_http_rate_limit_delays_total',
    'Total rate limit delays',
    ['service'],
)


# ========== System Metrics ==========

system_info = Info(
    'complira_system',
    'System information',
)

workflow_runs_total = Counter(
    'complira_workflow_runs_total',
    'Total workflow executions',
    ['workflow_name', 'status'],
)

workflow_duration_seconds = Histogram(
    'complira_workflow_duration_seconds',
    'Workflow execution duration',
    ['workflow_name'],
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400],  # 1m to 4h
)


# ========== Helper Functions ==========

def record_agent_execution(
    agent_name: str,
    duration_seconds: float,
    status: str,
    records_created: int = 0,
    records_updated: int = 0,
    records_skipped: int = 0,
    error_type: Optional[str] = None,
):
    """
    Record agent execution metrics.

    Args:
        agent_name: Name of agent
        duration_seconds: Execution duration
        status: 'success' or 'failed'
        records_created: Number of records created
        records_updated: Number of records updated
        records_skipped: Number of records skipped
        error_type: Type of error (if failed)
    """
    agent_runs_total.labels(agent_name=agent_name, status=status).inc()
    agent_duration_seconds.labels(agent_name=agent_name).observe(duration_seconds)

    if records_created > 0:
        agent_records_processed.labels(agent_name=agent_name, operation='created').inc(records_created)
    if records_updated > 0:
        agent_records_processed.labels(agent_name=agent_name, operation='updated').inc(records_updated)
    if records_skipped > 0:
        agent_records_processed.labels(agent_name=agent_name, operation='skipped').inc(records_skipped)

    if status == 'success':
        agent_last_success_timestamp.labels(agent_name=agent_name).set(time.time())
    elif error_type:
        agent_errors_total.labels(agent_name=agent_name, error_type=error_type).inc()


def record_llm_call(
    agent_name: str,
    model: str,
    duration_seconds: float,
    input_tokens: int,
    output_tokens: int,
    cost_dollars: float,
    status: str = 'success',
    confidence: Optional[float] = None,
):
    """
    Record LLM API call metrics.

    Args:
        agent_name: Name of LLM agent
        model: Model name (e.g., claude-haiku-4.5)
        duration_seconds: API call duration
        input_tokens: Input tokens consumed
        output_tokens: Output tokens generated
        cost_dollars: Cost in USD
        status: 'success' or 'failed'
        confidence: Confidence score (0-1)
    """
    llm_api_calls_total.labels(agent_name=agent_name, model=model, status=status).inc()
    llm_api_duration_seconds.labels(agent_name=agent_name, model=model).observe(duration_seconds)

    if status == 'success':
        llm_tokens_total.labels(agent_name=agent_name, model=model, token_type='input').inc(input_tokens)
        llm_tokens_total.labels(agent_name=agent_name, model=model, token_type='output').inc(output_tokens)
        llm_cost_dollars.labels(agent_name=agent_name, model=model).inc(cost_dollars)

        if confidence is not None:
            llm_confidence_score.labels(agent_name=agent_name, model=model).observe(confidence)


def record_llm_enrichment(agent_name: str, enrichment_type: str):
    """
    Record LLM enrichment creation.

    Args:
        agent_name: Name of LLM agent
        enrichment_type: Type of enrichment (e.g., 'cwe_classification', 'vex_document')
    """
    llm_enrichments_total.labels(agent_name=agent_name, enrichment_type=enrichment_type).inc()


def record_db_query(query_type: str, duration_seconds: float, status: str = 'success'):
    """
    Record database query metrics.

    Args:
        query_type: Type of query (aql, insert, update, delete)
        duration_seconds: Query duration
        status: 'success' or 'failed'
    """
    db_queries_total.labels(query_type=query_type, status=status).inc()
    db_query_duration_seconds.labels(query_type=query_type).observe(duration_seconds)


def update_db_collection_stats(db):
    """
    Update database collection statistics.

    Args:
        db: ArangoDB database instance
    """
    doc_collections = [
        'vulnerabilities', 'weaknesses', 'attack_techniques', 'attack_patterns',
        'threat_groups', 'd3fend_techniques', 'atlas_techniques', 'kev_entries',
        'exploit_modules', 'nuclei_templates', 'poc_repositories', 'components',
        'oscal_controls', 'scf_controls', 'opencre_nodes', 'licenses',
        'package_health', 'scorecard_results', 'epss_history', 'cpe_entries',
    ]

    edge_collections = [
        'has_weakness', 'has_exploit', 'affects_component', 'maps_to_requirement',
        'exploited_in_wild', 'has_epss_score', 'capec_relates_to_cwe',
        'd3fend_counters_technique', 'atlas_maps_to_attack',
    ]

    for coll_name in doc_collections:
        if db.has_collection(coll_name):
            count = db.collection(coll_name).count()
            db_documents_total.labels(collection=coll_name).set(count)

    for edge_name in edge_collections:
        if db.has_collection(edge_name):
            count = db.collection(edge_name).count()
            db_edges_total.labels(edge_type=edge_name).set(count)

    db_collections_count.set(len([c for c in doc_collections + edge_collections if db.has_collection(c)]))


def record_circuit_breaker_state(service: str, state: str):
    """
    Record circuit breaker state.

    Args:
        service: Service name (e.g., 'nvd_nist')
        state: 'closed', 'open', 'half_open'
    """
    state_map = {'closed': 0, 'open': 1, 'half_open': 2}
    circuit_breaker_state.labels(service=service).set(state_map.get(state, 0))


def record_circuit_breaker_event(service: str, event: str):
    """
    Record circuit breaker event.

    Args:
        service: Service name
        event: 'failure' or 'success'
    """
    if event == 'failure':
        circuit_breaker_failures_total.labels(service=service).inc()
    else:
        circuit_breaker_successes_total.labels(service=service).inc()


def record_http_request(
    service: str,
    method: str,
    status_code: int,
    duration_seconds: float,
):
    """
    Record HTTP request metrics.

    Args:
        service: Service name (e.g., 'nvd_nist')
        method: HTTP method (GET, POST, etc.)
        status_code: HTTP status code
        duration_seconds: Request duration
    """
    http_requests_total.labels(service=service, method=method, status_code=str(status_code)).inc()
    http_request_duration_seconds.labels(service=service, method=method).observe(duration_seconds)


def record_rate_limit_delay(service: str):
    """
    Record rate limit delay event.

    Args:
        service: Service name
    """
    http_rate_limit_delays_total.labels(service=service).inc()


def record_workflow_execution(workflow_name: str, duration_seconds: float, status: str):
    """
    Record workflow execution metrics.

    Args:
        workflow_name: Name of workflow (e.g., 'seed_knowledge_graph')
        duration_seconds: Execution duration
        status: 'success' or 'failed'
    """
    workflow_runs_total.labels(workflow_name=workflow_name, status=status).inc()
    workflow_duration_seconds.labels(workflow_name=workflow_name).observe(duration_seconds)


# ========== Decorators ==========

def track_agent_execution(agent_name: str):
    """
    Decorator to track agent execution metrics.

    Usage:
        @track_agent_execution('CWEAgent')
        def run(self):
            # agent logic
            return result
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'success'
            error_type = None
            result = None

            try:
                result = func(*args, **kwargs)
                return result

            except Exception as e:
                status = 'failed'
                error_type = type(e).__name__
                raise

            finally:
                duration = time.time() - start_time

                # Extract metrics from result
                records_created = result.get('created', 0) if result and isinstance(result, dict) else 0
                records_updated = result.get('updated', 0) if result and isinstance(result, dict) else 0
                records_skipped = result.get('skipped', 0) if result and isinstance(result, dict) else 0

                record_agent_execution(
                    agent_name=agent_name,
                    duration_seconds=duration,
                    status=status,
                    records_created=records_created,
                    records_updated=records_updated,
                    records_skipped=records_skipped,
                    error_type=error_type,
                )

        return wrapper
    return decorator


@contextmanager
def track_db_query(query_type: str):
    """
    Context manager to track database query metrics.

    Usage:
        with track_db_query('aql'):
            cursor = db.aql.execute(query)
    """
    start_time = time.time()
    status = 'success'

    try:
        yield

    except Exception:
        status = 'failed'
        raise

    finally:
        duration = time.time() - start_time
        record_db_query(query_type, duration, status)


# ========== Metrics Server ==========

def start_metrics_server(port: int = 9090, addr: str = '0.0.0.0'):
    """
    Start Prometheus metrics HTTP server.

    Args:
        port: Port to listen on (default: 9090)
        addr: Address to bind (default: 0.0.0.0)

    Example:
        start_metrics_server(port=9090)
    """
    logger.info("Starting Prometheus metrics server", port=port, addr=addr)

    # Set system info
    from ..config import get_settings
    settings = get_settings()

    system_info.info({
        'version': '1.0.0',
        'database': settings.ARANGO_DATABASE,
        'database_url': settings.ARANGO_URL,
    })

    # Start HTTP server
    start_http_server(port=port, addr=addr)

    logger.info("Metrics server started", endpoint=f"http://{addr}:{port}/metrics")


# ========== Health Check Metrics ==========

def update_health_metrics():
    """
    Update system health metrics.

    Should be called periodically (e.g., every 60 seconds).
    """
    from ..db import get_db, health_check

    try:
        # Check database health
        is_healthy, _ = health_check()

        if is_healthy:
            db = get_db()
            update_db_collection_stats(db)

    except Exception as e:
        logger.error("Failed to update health metrics", error=str(e))
