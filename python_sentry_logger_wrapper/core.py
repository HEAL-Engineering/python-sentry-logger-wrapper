"""Core functionality for the python-sentry-logger-wrapper package."""

import logging
import sys
from typing import TYPE_CHECKING, Literal, Optional

import sentry_sdk
import structlog
from sentry_sdk.integrations.logging import LoggingIntegration
from structlog.stdlib import BoundLogger

from ._processors import (
    add_sentry_trace_id,
    nest_custom_fields,
    remove_processors_meta_safe,
    rename_and_flatten_fields,
)

RendererChoice = Literal["json", "console", "auto"]
_VALID_RENDERERS = frozenset({"json", "console", "auto"})

# Type hint for static analysis - import is conditional at runtime
if TYPE_CHECKING:
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

# Optional Lambda integration - requires 'lambda' extra: uv add "python-sentry-logger-wrapper[lambda]"
try:
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

    HAS_LAMBDA_INTEGRATION = True
except ImportError:
    HAS_LAMBDA_INTEGRATION = False

_is_configured = False


def get_logger(
    service_name: str,
    log_level: int = logging.INFO,
    sentry_dsn: Optional[str] = None,
    sentry_breadcrumbs_level: int = logging.INFO,
    sentry_event_level: int = logging.ERROR,
    sentry_logs_level: int = logging.INFO,
    sentry_environment: Optional[str] = None,
    traces_sample_rate: float = 0.0,
    sentry_send_pii: bool = False,
    lambda_integration: bool = False,
    lambda_timeout_warning: bool = True,
    renderer: RendererChoice = "json",
) -> BoundLogger:
    """
    Configures and returns a standard logger with optional Sentry integration.

    This function initializes structlog with a processor chain to produce
    standardized logs to stdout. It also configures the standard logging
    library to route its logs through the same system, ensuring logs from
    third-party libraries are rendered consistently.

    Args:
        service_name: The name of the service, which will be included in all logs.
        log_level: The minimum log level to output to stdout (e.g., logging.INFO, logging.DEBUG).
        sentry_dsn: Optional Sentry DSN for error tracking and log monitoring.
        sentry_breadcrumbs_level: Minimum level for Sentry **breadcrumbs** — context
            attached to error events (default: INFO). Maps to ``LoggingIntegration(level=...)``.
        sentry_event_level: Minimum level at which a log becomes a Sentry **event** —
            an Issue in the Errors product (default: ERROR). Maps to
            ``LoggingIntegration(event_level=...)``.
        sentry_logs_level: Minimum level captured by Sentry's **Logs** product —
            structured logs separate from errors (default: INFO). Raise to
            ``logging.WARNING`` (or higher) to drop info-level logs from Sentry Logs
            without affecting breadcrumbs or event capture — useful for cutting Sentry
            quota on chatty services. Maps to ``LoggingIntegration(sentry_logs_level=...)``.
        sentry_environment: Optional environment name for Sentry (e.g., "production", "staging").
        traces_sample_rate: Performance tracing sample rate, 0.0 to 1.0 (default 0.0 — off).
            Passed straight to ``sentry_sdk.init(traces_sample_rate=...)``. Set to 0.1 for
            10% sampling, 1.0 for all transactions. Quota note: Sentry's free plan includes
            10k performance units/month — anything above ~0.1 on a busy service eats that
            fast. Leave at 0.0 unless you need tracing.
        sentry_send_pii: Whether to send PII (user IPs, cookies, headers) to Sentry (default False).
        lambda_integration: Enable AWS Lambda integration for Sentry (default False).
            Requires the 'lambda' extra: uv add "python-sentry-logger-wrapper[lambda]"
        lambda_timeout_warning: When lambda_integration=True, whether to warn about
            Lambda timeouts (default True).
        renderer: How to format stdout output. One of:
            - "json" (default): structured JSON, suited for log aggregators (ELK, Datadog,
              CloudWatch). Backwards-compatible — existing consumers see no change.
            - "console": colored, human-readable output via ``structlog.dev.ConsoleRenderer``.
              For local development.
            - "auto": resolves to "console" when ``sys.stdout.isatty()`` is True (interactive
              terminal), else "json" (piped, redirected, Docker, CI, k8s). Mirrors the
              ``ls --color=auto`` convention.
            Renderer choice does NOT affect Sentry ingestion — Sentry's ``LoggingIntegration``
            captures events at the stdlib handler level, before this renderer runs.

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
         "logger": "my-service", "message": "Service started",
         "details": {"version": "1.0.0"}}
    """
    if renderer not in _VALID_RENDERERS:
        raise ValueError(
            f"renderer must be one of {sorted(_VALID_RENDERERS)}, got {renderer!r}"
        )

    global _is_configured

    if not _is_configured:
        # Initialize Sentry if DSN provided
        if (
            sentry_environment == "production" or sentry_environment == "test"
        ) and sentry_dsn:

            def before_send_log(event, hint):
                """
                Filter items going to Sentry's Logs product.

                Belt-and-suspenders with LoggingIntegration(sentry_logs_level=...):
                drops anything below sentry_logs_level (the Logs threshold, NOT the
                events/Issues threshold) and strips uvicorn /health chatter so the
                Logs view stays useful and quota stays sane.
                """

                # Filter by log severity level — uses sentry_logs_level (Logs product
                # threshold), NOT sentry_event_level (Issues threshold). The two
                # pipelines are independent.
                severity_text = event.get("severity_text")
                if severity_text:
                    # Map Sentry severity levels to Python logging levels
                    severity_map = {
                        "debug": logging.DEBUG,
                        "info": logging.INFO,
                        "warn": logging.WARNING,
                        "warning": logging.WARNING,
                        "error": logging.ERROR,
                        "fatal": logging.CRITICAL,
                    }
                    event_level = severity_map.get(severity_text.lower(), logging.INFO)
                    if event_level < sentry_logs_level:
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
                logging.DEBUG: "debug",
                logging.INFO: "info",
                logging.WARNING: "warning",
                logging.ERROR: "error",
                logging.CRITICAL: "fatal",
            }
            min_breadcrumb_level = breadcrumb_level_map.get(
                sentry_breadcrumbs_level, "info"
            )
            breadcrumb_levels = ["debug", "info", "warning", "error", "fatal"]
            allowed_breadcrumb_levels = breadcrumb_levels[
                breadcrumb_levels.index(min_breadcrumb_level) :
            ]

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
                if crumb.get("category", "") == "uvicorn.access":
                    message = crumb.get("message", "")
                    if "GET /health" in message:
                        return None

                crumb_level = crumb.get("level")

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

            # Build integrations list
            # Note: Sentry deduplicates by integration type, so our custom LoggingIntegration
            # replaces the default one rather than causing duplicate logs
            integrations = [
                LoggingIntegration(
                    level=sentry_breadcrumbs_level,
                    event_level=sentry_event_level,
                    sentry_logs_level=sentry_logs_level,
                ),
            ]

            # Add Lambda integration if requested and available
            if lambda_integration:
                if not HAS_LAMBDA_INTEGRATION:
                    raise ImportError(
                        "Lambda integration requires the 'lambda' extra. "
                        "Install with: uv add 'python-sentry-logger-wrapper[lambda]'"
                    )
                integrations.append(
                    AwsLambdaIntegration(timeout_warning=lambda_timeout_warning)
                )

            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=sentry_environment,
                traces_sample_rate=traces_sample_rate,
                enable_logs=True,
                before_send=before_send,
                before_send_log=before_send_log,
                before_send_transaction=before_send_transaction,
                before_breadcrumb=before_breadcrumb,
                send_default_pii=sentry_send_pii,
                integrations=integrations,
            )
        elif sentry_dsn:
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=sentry_environment,
                default_integrations=False,
                traces_sample_rate=0.0,
            )

        # "auto" → console under a TTY, else JSON. Resolved once at configure time.
        resolved_renderer: Literal["json", "console"] = (
            ("console" if sys.stdout.isatty() else "json")
            if renderer == "auto"
            else renderer
        )

        shared_processors: list = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
        ]
        # ConsoleRenderer pretty-prints tracebacks itself from raw exc_info; running
        # format_exc_info first stringifies them and produces worse output.
        if resolved_renderer == "json":
            shared_processors.append(structlog.processors.format_exc_info)
        shared_processors.extend([rename_and_flatten_fields, nest_custom_fields])

        if sentry_dsn:
            shared_processors.append(add_sentry_trace_id)

        if resolved_renderer == "console":
            final_renderer = structlog.dev.ConsoleRenderer(colors=True)
        else:
            final_renderer = structlog.processors.JSONRenderer(ensure_ascii=False)

        structlog.configure(
            processors=shared_processors
            + [
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
                final_renderer,
            ],
        )

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        root_logger.setLevel(log_level)

        _is_configured = True

    # Tag every call (not just first-time setup) so callers with different
    # service_names get the right tag — last call wins. Safe no-op when
    # Sentry isn't initialized.
    if sentry_dsn:
        sentry_sdk.set_tag("service", service_name)

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
