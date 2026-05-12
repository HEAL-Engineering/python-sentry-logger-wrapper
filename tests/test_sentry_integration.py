"""Sentry behavior — health-check filters and renderer-independence of ingestion."""

from __future__ import annotations

import logging

import pytest

from python_sentry_logger_wrapper import get_logger


def _get_callback(mock_sentry_sdk, name: str):
    """Pull a callback kwarg out of the mocked sentry_sdk.init call."""
    init = mock_sentry_sdk["init"]
    assert init.call_count >= 1, "sentry_sdk.init was not called"
    return init.call_args.kwargs[name]


def test_before_send_drops_uvicorn_health_check_event(mock_sentry_sdk):
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    before_send = _get_callback(mock_sentry_sdk, "before_send")
    event = {
        "logger": "uvicorn.access",
        "logentry": {"formatted": '127.0.0.1:0 - "GET /health HTTP/1.1" 200 OK'},
    }
    assert before_send(event, {}) is None


def test_before_send_passes_non_health_event_unchanged(mock_sentry_sdk):
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    before_send = _get_callback(mock_sentry_sdk, "before_send")
    event = {
        "logger": "my.app",
        "logentry": {"formatted": "something bad happened"},
    }
    assert before_send(event, {}) is event


def test_before_send_transaction_drops_health_transaction(mock_sentry_sdk):
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    cb = _get_callback(mock_sentry_sdk, "before_send_transaction")
    assert cb({"transaction": "/health"}, {}) is None


def test_before_send_transaction_passes_other_transactions(mock_sentry_sdk):
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    cb = _get_callback(mock_sentry_sdk, "before_send_transaction")
    event = {"transaction": "GET /users"}
    assert cb(event, {}) is event


def test_before_send_log_drops_below_logs_threshold(mock_sentry_sdk):
    """before_send_log filters by sentry_logs_level (Logs threshold), NOT event_level."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
        sentry_logs_level=logging.WARNING,
    )
    cb = _get_callback(mock_sentry_sdk, "before_send_log")
    info_event = {"severity_text": "info", "body": "noise below threshold"}
    assert cb(info_event, {}) is None


def test_before_send_log_passes_at_or_above_logs_threshold(mock_sentry_sdk):
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
        sentry_logs_level=logging.WARNING,
    )
    cb = _get_callback(mock_sentry_sdk, "before_send_log")
    warn_event = {"severity_text": "warning", "body": "at threshold"}
    assert cb(warn_event, {}) is warn_event


def test_before_send_log_threshold_is_independent_of_event_level(mock_sentry_sdk):
    """Raising sentry_event_level must not affect Logs-product filtering."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
        sentry_event_level=logging.CRITICAL,  # high — would drop INFO if conflated
        sentry_logs_level=logging.INFO,  # but Logs threshold is INFO
    )
    cb = _get_callback(mock_sentry_sdk, "before_send_log")
    info_event = {"severity_text": "info", "body": "should reach Logs"}
    assert cb(info_event, {}) is info_event


def test_before_breadcrumb_drops_uvicorn_health_crumb(mock_sentry_sdk):
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    cb = _get_callback(mock_sentry_sdk, "before_breadcrumb")
    crumb = {
        "category": "uvicorn.access",
        "message": '127.0.0.1 - "GET /health HTTP/1.1" 200',
    }
    assert cb(crumb, {}) is None


@pytest.mark.parametrize("renderer", ["json", "console"])
def test_renderer_choice_does_not_affect_sentry_init(mock_sentry_sdk, renderer):
    """Sentry ingestion is wired the same regardless of stdout renderer choice."""
    get_logger(
        "svc",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
        renderer=renderer,
    )
    assert mock_sentry_sdk["init"].call_count == 1
    mock_sentry_sdk["LoggingIntegration"].assert_called_once()


def test_service_name_tag_set_on_init(mock_sentry_sdk):
    get_logger(
        "payments",
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        sentry_environment="production",
    )
    mock_sentry_sdk["set_tag"].assert_called_with("service", "payments")
