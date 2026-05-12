"""get_logger() setup behavior — wiring of Sentry params, idempotence, no-DSN branch."""

from __future__ import annotations

import logging

import structlog

from python_sentry_logger_wrapper import get_logger


def test_get_logger_is_idempotent(mock_sentry_sdk):
    """Calling get_logger twice must not re-configure structlog or re-init Sentry."""
    get_logger(
        "svc-a",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    first_processors = structlog.get_config()["processors"]
    first_init_calls = mock_sentry_sdk["init"].call_count

    get_logger(
        "svc-a",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    second_processors = structlog.get_config()["processors"]

    assert structlog.is_configured()
    assert len(second_processors) == len(first_processors)
    assert mock_sentry_sdk["init"].call_count == first_init_calls


def test_no_dsn_does_not_init_sentry(mock_sentry_sdk):
    """When sentry_dsn is None, sentry_sdk.init must not be called."""
    get_logger("svc", sentry_dsn=None)
    assert mock_sentry_sdk["init"].call_count == 0


def test_empty_dsn_does_not_init_sentry(mock_sentry_sdk):
    """Empty string DSN is falsy and should be treated like None."""
    get_logger("svc", sentry_dsn="")
    assert mock_sentry_sdk["init"].call_count == 0


def test_dsn_with_production_inits_sentry(mock_sentry_sdk):
    """DSN + production env triggers full sentry_sdk.init with logging integration."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    assert mock_sentry_sdk["init"].call_count == 1
    kwargs = mock_sentry_sdk["init"].call_args.kwargs
    assert kwargs["dsn"] == "https://k@o.ingest.sentry.io/1"
    assert kwargs["environment"] == "production"
    assert kwargs["enable_logs"] is True


def test_dsn_without_production_uses_minimal_init(mock_sentry_sdk):
    """DSN with non-production env uses the minimal init path (no integrations)."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="development",
    )
    assert mock_sentry_sdk["init"].call_count == 1
    kwargs = mock_sentry_sdk["init"].call_args.kwargs
    assert kwargs.get("default_integrations") is False
    assert kwargs["traces_sample_rate"] == 0.0


def test_sentry_logs_level_flows_to_logging_integration(mock_sentry_sdk):
    """sentry_logs_level kwarg lands on LoggingIntegration(sentry_logs_level=...)."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
        sentry_logs_level=logging.WARNING,
    )
    mock_sentry_sdk["LoggingIntegration"].assert_called_once()
    kwargs = mock_sentry_sdk["LoggingIntegration"].call_args.kwargs
    assert kwargs["sentry_logs_level"] == logging.WARNING


def test_sentry_logs_level_defaults_to_info(mock_sentry_sdk):
    """Default sentry_logs_level is logging.INFO."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    kwargs = mock_sentry_sdk["LoggingIntegration"].call_args.kwargs
    assert kwargs["sentry_logs_level"] == logging.INFO


def test_sentry_event_level_flows_to_logging_integration(mock_sentry_sdk):
    """sentry_event_level kwarg lands on LoggingIntegration(event_level=...)."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
        sentry_event_level=logging.CRITICAL,
    )
    kwargs = mock_sentry_sdk["LoggingIntegration"].call_args.kwargs
    assert kwargs["event_level"] == logging.CRITICAL


def test_sentry_breadcrumbs_level_flows_to_logging_integration(mock_sentry_sdk):
    """sentry_breadcrumbs_level kwarg lands on LoggingIntegration(level=...)."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
        sentry_breadcrumbs_level=logging.WARNING,
    )
    kwargs = mock_sentry_sdk["LoggingIntegration"].call_args.kwargs
    assert kwargs["level"] == logging.WARNING


def test_traces_sample_rate_flows_to_sentry_init(mock_sentry_sdk):
    """traces_sample_rate kwarg lands on sentry_sdk.init(traces_sample_rate=...)."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
        traces_sample_rate=0.25,
    )
    kwargs = mock_sentry_sdk["init"].call_args.kwargs
    assert kwargs["traces_sample_rate"] == 0.25


def test_traces_sample_rate_defaults_to_zero(mock_sentry_sdk):
    """Default traces_sample_rate is 0.0 — tracing off, no quota surprises."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    kwargs = mock_sentry_sdk["init"].call_args.kwargs
    assert kwargs["traces_sample_rate"] == 0.0


def test_service_name_attached_as_tag(mock_sentry_sdk):
    """service_name is set as a Sentry tag so events can be filtered by service."""
    get_logger(
        "billing-api",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    mock_sentry_sdk["set_tag"].assert_called_with("service", "billing-api")


def test_service_name_tagged_even_in_dev_branch(mock_sentry_sdk):
    """service_name tag is set even when env != production (minimal init path)."""
    get_logger(
        "billing-api",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="development",
    )
    mock_sentry_sdk["set_tag"].assert_called_with("service", "billing-api")


def test_invalid_renderer_raises_value_error():
    """Bad renderer string fails fast before any side effects."""
    import pytest

    with pytest.raises(ValueError, match="renderer must be one of"):
        get_logger("svc", renderer="yaml")  # type: ignore[arg-type]
