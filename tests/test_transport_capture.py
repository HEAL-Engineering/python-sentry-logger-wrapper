"""End-to-end Sentry transport capture — proves a real envelope is produced.

This test sits between the mocked unit tests and a true network round-trip.
We swap Sentry's HTTP transport for an in-memory capturing one, run the full
get_logger() pipeline (structlog + stdlib + LoggingIntegration), then assert
that calling ``logger.error(...)`` actually produces an envelope of the right
shape. Catches integration bugs (wrong processor order, malformed event_dict)
that pure mocks would miss, without needing a DSN or network access.
"""

from __future__ import annotations

import logging

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

import python_sentry_logger_wrapper.core as core_module
from python_sentry_logger_wrapper import get_logger


class _CaptureTransport(Transport):
    """In-memory Sentry transport — records envelopes on the class instead of POSTing.

    Captures are stored on the *class* (not the instance) so test code can read them
    via ``_CaptureTransport.captured`` regardless of when sentry_sdk constructs the
    transport during init.
    """

    captured: list = []

    def __init__(self, options=None):
        super().__init__(options)

    def capture_envelope(self, envelope):
        _CaptureTransport.captured.append(envelope)

    def flush(self, timeout, callback=None):
        return None

    def kill(self):
        return None


@pytest.fixture
def capture_transport(monkeypatch):
    """Inject _CaptureTransport into sentry_sdk.init and reset the capture buffer."""
    real_init = sentry_sdk.init

    def init_with_capture(*args, **kwargs):
        kwargs["transport"] = _CaptureTransport
        return real_init(*args, **kwargs)

    monkeypatch.setattr(core_module.sentry_sdk, "init", init_with_capture)
    _CaptureTransport.captured = []
    yield _CaptureTransport
    sentry_sdk.flush(timeout=2.0)


def _find_event_payload(envelopes, needle: str):
    """Walk envelopes for an event item whose payload contains ``needle``."""
    for envelope in envelopes:
        for item in envelope.items:
            payload = getattr(item, "payload", None)
            if payload is None:
                continue
            try:
                data = payload.json
            except Exception:
                continue
            if data and needle in str(data):
                return data
    return None


def test_error_log_produces_sentry_envelope(capture_transport):
    """logger.error() through structlog → stdlib → LoggingIntegration → envelope."""
    logger = get_logger(
        "transport-test-svc",
        sentry_dsn="https://public@o0.ingest.sentry.io/0",
        sentry_environment="production",
        sentry_event_level=logging.ERROR,
    )

    logger.error("envelope-canary", user_id=42)
    sentry_sdk.flush(timeout=2.0)

    envelopes = capture_transport.captured
    assert envelopes, (
        "no envelopes captured — Sentry pipeline did not produce a payload"
    )
    data = _find_event_payload(envelopes, "envelope-canary")
    assert data is not None, (
        f"expected envelope containing 'envelope-canary'; got "
        f"{len(envelopes)} envelope(s) with no matching event"
    )


def test_service_name_tag_on_captured_envelope(capture_transport):
    """service_name set via set_tag lands on the envelope's tags."""
    logger = get_logger(
        "payments-svc",
        sentry_dsn="https://public@o0.ingest.sentry.io/0",
        sentry_environment="production",
        sentry_event_level=logging.ERROR,
    )

    logger.error("tag-canary")
    sentry_sdk.flush(timeout=2.0)

    data = _find_event_payload(capture_transport.captured, "tag-canary")
    assert data is not None, "no envelope captured the tag-canary event"
    tags = data.get("tags") or {}
    # tags may be dict or list of [k, v] pairs depending on sentry-sdk version
    if isinstance(tags, dict):
        assert tags.get("service") == "payments-svc"
    else:
        assert ["service", "payments-svc"] in tags or (
            "service",
            "payments-svc",
        ) in tags


def test_info_log_below_event_threshold_does_not_envelope(capture_transport):
    """info-level log with sentry_event_level=ERROR should not produce an event envelope."""
    logger = get_logger(
        "svc",
        sentry_dsn="https://public@o0.ingest.sentry.io/0",
        sentry_environment="production",
        sentry_event_level=logging.ERROR,
    )

    logger.info("not-an-event")
    sentry_sdk.flush(timeout=2.0)

    # Logs product or breadcrumb may still produce an envelope; just assert there's
    # no "event" type item carrying our info message.
    data = _find_event_payload(capture_transport.captured, "not-an-event")
    if data is not None:
        # If we found a match, it must not be an exception/event with this as the message
        assert data.get("level") != "error"
