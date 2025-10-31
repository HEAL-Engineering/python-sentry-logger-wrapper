"""Core functionality for the heal-logger package."""
import logging
import sys
from typing import Optional

import structlog
from structlog.stdlib import BoundLogger
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from ._processors import nest_custom_fields, rename_and_flatten_fields, remove_processors_meta_safe, add_sentry_trace_id

_is_configured = False


def get_logger(
    service_name: str,
    log_level: int = logging.INFO,
    sentry_dsn: Optional[str] = None,
    sentry_breadcrumbs_level: int = logging.INFO,
    sentry_log_level: int = logging.ERROR,
    sentry_environment: Optional[str] = None,
    sentry_sample_rate: float = 1.0,
    sentry_send_pii: bool = False
) -> BoundLogger:
    """
    Configures and returns a standard logger with optional Sentry integration.

    This function initializes structlog with a processor chain to produce
    standardized JSON logs to stdout. It also configures the standard
    logging library to route its logs through the same system, ensuring
    logs from third-party libraries are also captured in JSON format.

    Args:
        service_name: The name of the service, which will be included in all logs.
        log_level: The minimum log level to output to stdout (e.g., logging.INFO, logging.DEBUG).
        sentry_dsn: Optional Sentry DSN for error tracking and log monitoring.
        sentry_breadcrumbs_level: Minimum log level for Sentry breadcrumbs (default: INFO).
        sentry_log_level: Minimum log level for Sentry events (default: ERROR).
        sentry_environment: Optional environment name for Sentry (e.g., "production", "staging").
        sentry_sample_rate: Sample rate for Sentry traces (0.0 to 1.0, default 1.0).
        sentry_send_pii: Whether to send PII (user IPs, cookies, headers) to Sentry (default False).

    Note:
        Health check filtering: In production/test environments, all /health endpoint
        logs, breadcrumbs, and transactions are automatically filtered out to prevent
        Sentry quota exhaustion from monitoring probes.

    Returns:
        A structlog bound logger instance ready for use.

    Example:
        >>> logger = get_logger("my-service", sentry_dsn="https://...")
        >>> logger.info("Service started", version="1.0.0")
        {"timestamp": "2024-01-15T10:30:00Z", "log_level": "INFO",
         "service_name": "my-service", "message": "Service started",
         "details": {"version": "1.0.0"}}
    """
    global _is_configured

    if not _is_configured:
        # Initialize Sentry if DSN provided
        if (sentry_environment == "production" or sentry_environment == "test") and sentry_dsn:

            def before_send_log(event, hint):
                """
                Filter logs before sending to Sentry.

                This prevents health check endpoint spam in Sentry and enforces
                minimum log levels. Health checks can generate thousands of logs
                per day and pollute your Sentry quota and dashboard.

                Filters applied:
                - Removes logs below sentry_log_level (default: ERROR)
                - Removes uvicorn.access logs from GET /health endpoint
                """

                # Filter by log severity level
                severity_text = event.get("severity_text")
                if severity_text:
                    # Map Sentry severity levels to Python logging levels
                    severity_map = {
                        'debug': logging.DEBUG,
                        'info': logging.INFO,
                        'warn': logging.WARNING,
                        'warning': logging.WARNING,
                        'error': logging.ERROR,
                        'fatal': logging.CRITICAL,
                    }
                    event_level = severity_map.get(severity_text.lower(), logging.INFO)
                    if event_level < sentry_log_level:
                        return None

                # Check logger field (for event-level logs)
                logger_name = event.get("logger", "")

                # Also check attributes for log records
                if not logger_name:
                    logger_name = event.get("attributes", {}).get("logger.name", "")

                if logger_name == "uvicorn.access":
                    # Check both body (log records) and logentry (events)
                    message = event.get("body", "")
                    if not message:
                        message = event.get("logentry", {}).get("formatted", "")

                    if "GET /health" in message and "HTTP" in message:
                        return None

                return event

            # Map logging levels to Sentry breadcrumb level strings
            breadcrumb_level_map = {
                logging.DEBUG: 'debug',
                logging.INFO: 'info',
                logging.WARNING: 'warning',
                logging.ERROR: 'error',
                logging.CRITICAL: 'fatal',
            }
            min_breadcrumb_level = breadcrumb_level_map.get(sentry_breadcrumbs_level, 'info')
            breadcrumb_levels = ['debug', 'info', 'warning', 'error', 'fatal']
            allowed_breadcrumb_levels = breadcrumb_levels[breadcrumb_levels.index(min_breadcrumb_level):]

            def before_breadcrumb(crumb, hint):
                """
                Filter breadcrumbs before adding to Sentry events.

                Breadcrumbs are INFO/WARNING logs that get attached to ERROR events
                for context. This prevents health check breadcrumbs from cluttering
                your error reports and consuming unnecessary Sentry quota.

                Filters applied:
                - Removes uvicorn.access breadcrumbs from GET /health endpoint
                - Enforces minimum breadcrumb level (sentry_breadcrumbs_level)
                """
                # Filter out uvicorn health check breadcrumbs
                if crumb.get('category', "") == 'uvicorn.access':
                    message = crumb.get('message', '')
                    if 'GET /health' in message:
                        return None

                crumb_level = crumb.get('level')

                # If breadcrumb has no level (e.g., HTTP, DB queries), check type
                if crumb_level is None:
                    # Only allow non-logging breadcrumbs if breadcrumb level is INFO or lower
                    # This keeps HTTP/DB breadcrumbs when you want verbose breadcrumbs
                    return crumb if sentry_breadcrumbs_level <= logging.INFO else None

                # For breadcrumbs with levels (logs), filter by level
                return crumb if crumb_level in allowed_breadcrumb_levels else None

            def before_send_transaction(event, hint):
                """
                Filter transactions before sending to Sentry.

                Prevents /health endpoint transactions from being sent to Sentry.
                Health checks create a transaction for every probe, which can
                quickly exhaust your Sentry performance monitoring quota.
                """
                transaction_name = event.get("transaction", "")
                if transaction_name == "/health":
                    return None
                return event

            def before_send(event, hint):
                """
                Filter events before sending to Sentry (for LoggingIntegration).

                Additional filter specifically for events created by LoggingIntegration
                to catch any health check logs that might slip through other filters.
                """
                logger_name = event.get("logger", "")
                if logger_name == "uvicorn.access":
                    message = event.get("logentry", {}).get("formatted", "")
                    if "GET /health" in message and "HTTP" in message:
                        return None
                return event

            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=sentry_environment,
                traces_sample_rate=sentry_sample_rate,
                enable_tracing=True,
                enable_logs=True,
                before_send=before_send,
                before_send_log=before_send_log,
                before_send_transaction=before_send_transaction,
                before_breadcrumb=before_breadcrumb,
                send_default_pii=sentry_send_pii,
                integrations=[
                    LoggingIntegration(
                        level=sentry_breadcrumbs_level,
                        event_level=sentry_log_level,
                    ),
                ],
            )
        elif sentry_dsn:
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=sentry_environment,
                default_integrations=False,
                traces_sample_rate=0.0,
                enable_tracing=False,
            )
            

        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            rename_and_flatten_fields,
            nest_custom_fields
        ]

        if sentry_dsn:
            shared_processors.append(add_sentry_trace_id)

        structlog.configure(
            processors=shared_processors + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                remove_processors_meta_safe,
                structlog.processors.JSONRenderer(ensure_ascii=False),
            ],
        )

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        root_logger.setLevel(log_level)

        _is_configured = True

    logger = structlog.get_logger(service_name)
    
    return logger


def reset_configuration():
    """
    Resets the logger configuration. Useful for testing or reconfiguration.
    
    Warning: This should generally not be used in production code.
    """
    global _is_configured
    _is_configured = False
    structlog.reset_defaults()