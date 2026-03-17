"""
Structured Logging Configuration for Knowledge Graph Engine.

Provides centralized logging configuration using structlog with:
- JSON output for production
- Human-readable output for development
- Contextual bindings (tenant, product, agent, trace_id)
- Log correlation across distributed operations
- Integration with Prometheus metrics

Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
"""

import sys
import logging
import uuid
from typing import Dict, Any, Optional
from pathlib import Path

import structlog
from structlog.types import EventDict, Processor


# ========== Log Processors ==========

def add_app_context(logger, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add application context to log events.

    Args:
        logger: Logger instance
        method_name: Log method name
        event_dict: Event dictionary

    Returns:
        EventDict: Enhanced event dictionary
    """
    event_dict['app'] = 'complira-graph'
    event_dict['version'] = '1.0.0'
    return event_dict


def add_trace_id(logger, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add trace ID for log correlation.

    Generates a unique trace ID if not already present.

    Args:
        logger: Logger instance
        method_name: Log method name
        event_dict: Event dictionary

    Returns:
        EventDict: Enhanced event dictionary
    """
    if 'trace_id' not in event_dict:
        # Check if trace_id is in bound context
        bound_trace_id = getattr(logger, '_context', {}).get('trace_id')
        if bound_trace_id:
            event_dict['trace_id'] = bound_trace_id
        else:
            event_dict['trace_id'] = str(uuid.uuid4())

    return event_dict


def censor_sensitive_data(logger, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Censor sensitive data from logs.

    Replaces sensitive fields with [REDACTED].

    Args:
        logger: Logger instance
        method_name: Log method name
        event_dict: Event dictionary

    Returns:
        EventDict: Sanitized event dictionary
    """
    sensitive_keys = [
        'password',
        'api_key',
        'token',
        'secret',
        'authorization',
        'anthropic_api_key',
    ]

    for key in sensitive_keys:
        if key in event_dict:
            event_dict[key] = '[REDACTED]'

        # Also check nested dicts
        for event_key, event_value in event_dict.items():
            if isinstance(event_value, dict):
                for sensitive_key in sensitive_keys:
                    if sensitive_key in event_value:
                        event_value[sensitive_key] = '[REDACTED]'

    return event_dict


def add_error_details(logger, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Extract exception details from exc_info.

    Args:
        logger: Logger instance
        method_name: Log method name
        event_dict: Event dictionary

    Returns:
        EventDict: Enhanced event dictionary
    """
    exc_info = event_dict.get('exc_info')

    if exc_info:
        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            exc_type, exc_value, exc_tb = exc_info
            event_dict['exception_type'] = exc_type.__name__ if exc_type else None
            event_dict['exception_message'] = str(exc_value) if exc_value else None

    return event_dict


# ========== Logging Configuration ==========

def configure_logging(
    level: str = 'INFO',
    json_output: bool = False,
    log_file: Optional[Path] = None,
    enable_colors: bool = True,
) -> None:
    """
    Configure structlog for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: Output logs in JSON format (for production)
        log_file: Optional file path for log output
        enable_colors: Enable colored output (for console)

    Example:
        # Development
        configure_logging(level='DEBUG', json_output=False)

        # Production
        configure_logging(level='INFO', json_output=True, log_file=Path('/var/log/complira.log'))
    """
    # Set log level
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure stdlib logging
    logging.basicConfig(
        format='%(message)s',
        stream=sys.stdout,
        level=log_level,
    )

    # Build processor chain
    processors: list[Processor] = [
        # Add context
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt='iso', utc=True),
        add_app_context,
        add_trace_id,
        censor_sensitive_data,
        add_error_details,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]

    # Choose final renderer
    if json_output:
        # JSON output for production/parsing
        processors.extend([
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ])
    else:
        # Human-readable output for development
        processors.extend([
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=enable_colors),
        ])

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Optional file logging
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(str(log_file))
        file_handler.setLevel(log_level)

        # JSON format for file logs
        file_formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(file_formatter)

        # Add to root logger
        logging.getLogger().addHandler(file_handler)


def get_logger(
    name: Optional[str] = None,
    **initial_context: Any,
) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger with optional context.

    Args:
        name: Logger name (typically __name__)
        **initial_context: Initial context to bind to logger

    Returns:
        BoundLogger: Configured logger instance

    Example:
        logger = get_logger(__name__, agent='CWEAgent', tenant_id='tenant-123')
        logger.info("Processing CWE data", total_records=1000)
    """
    logger = structlog.get_logger(name)

    if initial_context:
        logger = logger.bind(**initial_context)

    return logger


# ========== Context Managers ==========

class LogContext:
    """
    Context manager for temporary log context.

    Binds context for the duration of the block, then unbinds.

    Example:
        with LogContext(agent='CWEAgent', trace_id='abc-123'):
            logger.info("Processing data")  # Includes agent and trace_id
    """

    def __init__(self, **context: Any):
        """
        Initialize log context.

        Args:
            **context: Context to bind
        """
        self.context = context
        self.logger = structlog.get_logger()
        self.old_context = None

    def __enter__(self):
        """Bind context."""
        self.old_context = getattr(self.logger, '_context', {}).copy()
        self.logger = self.logger.bind(**self.context)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore old context."""
        if self.old_context is not None:
            # Restore old context
            self.logger._context = self.old_context


def with_log_context(**context: Any):
    """
    Decorator to add context to all logs within a function.

    Args:
        **context: Context to bind

    Example:
        @with_log_context(agent='CWEAgent')
        def run(self):
            logger.info("Starting agent")  # Includes agent='CWEAgent'
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with LogContext(**context):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# ========== Agent Logging Helpers ==========

def log_agent_start(logger, agent_name: str, **context: Any) -> None:
    """
    Log agent start with standard format.

    Args:
        logger: Logger instance
        agent_name: Name of agent
        **context: Additional context
    """
    logger.info(
        "Agent started",
        agent=agent_name,
        event='agent_start',
        **context,
    )


def log_agent_complete(
    logger,
    agent_name: str,
    duration_seconds: float,
    records_created: int = 0,
    records_updated: int = 0,
    **context: Any,
) -> None:
    """
    Log agent completion with standard format.

    Args:
        logger: Logger instance
        agent_name: Name of agent
        duration_seconds: Execution duration
        records_created: Number of records created
        records_updated: Number of records updated
        **context: Additional context
    """
    logger.info(
        "Agent completed",
        agent=agent_name,
        event='agent_complete',
        duration_seconds=duration_seconds,
        records_created=records_created,
        records_updated=records_updated,
        **context,
    )


def log_agent_error(
    logger,
    agent_name: str,
    error: Exception,
    **context: Any,
) -> None:
    """
    Log agent error with standard format.

    Args:
        logger: Logger instance
        agent_name: Name of agent
        error: Exception instance
        **context: Additional context
    """
    logger.error(
        "Agent failed",
        agent=agent_name,
        event='agent_error',
        error=str(error),
        error_type=type(error).__name__,
        exc_info=True,
        **context,
    )


def log_llm_call(
    logger,
    agent_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_seconds: float,
    **context: Any,
) -> None:
    """
    Log LLM API call with standard format.

    Args:
        logger: Logger instance
        agent_name: Name of LLM agent
        model: Model name
        input_tokens: Input tokens
        output_tokens: Output tokens
        duration_seconds: API call duration
        **context: Additional context
    """
    logger.info(
        "LLM API call",
        agent=agent_name,
        event='llm_call',
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_seconds=duration_seconds,
        **context,
    )


def log_circuit_breaker_event(
    logger,
    service: str,
    event: str,
    state: str,
    **context: Any,
) -> None:
    """
    Log circuit breaker event.

    Args:
        logger: Logger instance
        service: Service name
        event: Event type (opened, closed, half_opened, failure, success)
        state: Current state (open, closed, half_open)
        **context: Additional context
    """
    level = 'warning' if event in ['opened', 'failure'] else 'info'

    getattr(logger, level)(
        f"Circuit breaker {event}",
        service=service,
        event=f'circuit_breaker_{event}',
        state=state,
        **context,
    )


# ========== Audit Logging ==========

class AuditLogger:
    """
    Specialized logger for audit events.

    Logs security-relevant events (access, modifications, errors) to separate audit log.
    """

    def __init__(self, audit_log_file: Optional[Path] = None):
        """
        Initialize audit logger.

        Args:
            audit_log_file: Path to audit log file
        """
        self.logger = get_logger('audit')

        if audit_log_file:
            audit_log_file.parent.mkdir(parents=True, exist_ok=True)

            handler = logging.FileHandler(str(audit_log_file))
            handler.setLevel(logging.INFO)
            handler.setFormatter(logging.Formatter('%(message)s'))

            logging.getLogger('audit').addHandler(handler)

    def log_access(
        self,
        resource: str,
        action: str,
        user: Optional[str] = None,
        **context: Any,
    ) -> None:
        """
        Log resource access.

        Args:
            resource: Resource accessed (e.g., collection name, CVE ID)
            action: Action performed (read, write, delete)
            user: User/service performing action
            **context: Additional context
        """
        self.logger.info(
            "Resource access",
            event='access',
            resource=resource,
            action=action,
            user=user or 'system',
            **context,
        )

    def log_modification(
        self,
        resource: str,
        action: str,
        changes: Dict[str, Any],
        user: Optional[str] = None,
        **context: Any,
    ) -> None:
        """
        Log resource modification.

        Args:
            resource: Resource modified
            action: Action performed (create, update, delete)
            changes: Changes made
            user: User/service performing action
            **context: Additional context
        """
        self.logger.info(
            "Resource modification",
            event='modification',
            resource=resource,
            action=action,
            changes=changes,
            user=user or 'system',
            **context,
        )

    def log_security_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        **context: Any,
    ) -> None:
        """
        Log security event.

        Args:
            event_type: Type of security event
            severity: Severity level (low, medium, high, critical)
            description: Event description
            **context: Additional context
        """
        log_method = getattr(self.logger, 'warning' if severity in ['high', 'critical'] else 'info')

        log_method(
            description,
            event='security',
            event_type=event_type,
            severity=severity,
            **context,
        )


# ========== Production Configuration Presets ==========

def configure_production_logging(log_dir: Path = Path('/var/log/complira')):
    """
    Configure logging for production environment.

    Args:
        log_dir: Directory for log files
    """
    configure_logging(
        level='INFO',
        json_output=True,
        log_file=log_dir / 'complira-graph.log',
        enable_colors=False,
    )


def configure_development_logging():
    """
    Configure logging for development environment.
    """
    configure_logging(
        level='DEBUG',
        json_output=False,
        enable_colors=True,
    )


# ========== Default Configuration ==========

# Auto-configure based on environment
import os

if os.getenv('ENVIRONMENT', 'development') == 'production':
    configure_production_logging()
else:
    configure_development_logging()
