"""Structlog processor chain — shape transformations and graceful fallbacks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from python_sentry_logger_wrapper._processors import (
    add_sentry_trace_id,
    nest_custom_fields,
    remove_processors_meta_safe,
    rename_and_flatten_fields,
)


def test_rename_and_flatten_fields_maps_event_to_message():
    event_dict = {"event": "user logged in", "level": "info"}
    out = rename_and_flatten_fields(None, "info", event_dict)
    assert out["message"] == "user logged in"
    assert "event" not in out


def test_rename_and_flatten_fields_maps_level_to_log_level_uppercase():
    event_dict = {"event": "hi", "level": "warning"}
    out = rename_and_flatten_fields(None, "warning", event_dict)
    assert out["log_level"] == "WARNING"
    assert "level" not in out


def test_rename_and_flatten_fields_is_safe_without_event_or_level():
    """Missing keys must not raise — robustness over strictness."""
    out = rename_and_flatten_fields(None, "info", {"other": "value"})
    assert out == {"other": "value"}


def test_nest_custom_fields_moves_non_standard_keys_under_details():
    event_dict = {
        "message": "hi",
        "log_level": "INFO",
        "timestamp": "2024-01-01T00:00:00Z",
        "logger": "svc",
        "user_id": 42,
        "request_id": "abc",
    }
    out = nest_custom_fields(None, "info", event_dict)
    assert out["message"] == "hi"
    assert out["log_level"] == "INFO"
    assert out["timestamp"] == "2024-01-01T00:00:00Z"
    assert out["logger"] == "svc"
    assert out["details"] == {"user_id": 42, "request_id": "abc"}
    assert "user_id" not in out
    assert "request_id" not in out


def test_nest_custom_fields_skips_details_key_when_empty():
    """No custom fields → no empty details dict."""
    event_dict = {"message": "hi", "log_level": "INFO"}
    out = nest_custom_fields(None, "info", event_dict)
    assert "details" not in out


def test_nest_custom_fields_strips_underscore_prefixed_keys():
    """Internal keys (prefixed with _) are dropped, not nested."""
    event_dict = {"message": "hi", "_internal": "secret", "user_id": 1}
    out = nest_custom_fields(None, "info", event_dict)
    assert "_internal" not in out
    assert "_internal" not in out.get("details", {})
    assert out["details"] == {"user_id": 1}


def test_nest_custom_fields_preserves_exc_info_and_stack_info():
    """exc_info / stack_info stay top-level so the final renderer can format them."""
    event_dict = {
        "message": "boom",
        "exc_info": ("type", "value", "tb"),
        "stack_info": "stack-string",
    }
    out = nest_custom_fields(None, "error", event_dict)
    assert out["exc_info"] == ("type", "value", "tb")
    assert out["stack_info"] == "stack-string"
    assert "details" not in out


def test_remove_processors_meta_safe_strips_internal_fields():
    event_dict = {"message": "hi", "_record": object(), "_from_structlog": True}
    out = remove_processors_meta_safe(None, "info", event_dict)
    assert "_record" not in out
    assert "_from_structlog" not in out
    assert out["message"] == "hi"


def test_remove_processors_meta_safe_no_error_when_missing():
    """Unlike structlog's built-in, ours doesn't raise KeyError on absent fields."""
    out = remove_processors_meta_safe(None, "info", {"message": "hi"})
    assert out == {"message": "hi"}


def test_add_sentry_trace_id_silent_when_no_scope():
    """No active Sentry scope → no trace_id key, no exception."""
    with patch(
        "python_sentry_logger_wrapper._processors.sentry_sdk.get_current_scope",
        side_effect=Exception("no scope"),
    ):
        out = add_sentry_trace_id(None, "info", {"message": "hi"})
    assert "trace_id" not in out
    assert "span_id" not in out
    assert out["message"] == "hi"


def test_add_sentry_trace_id_silent_when_traceparent_empty():
    """get_traceparent() returning falsy is swallowed, no trace_id added."""
    fake_scope = MagicMock()
    fake_scope.get_traceparent.return_value = None
    with patch(
        "python_sentry_logger_wrapper._processors.sentry_sdk.get_current_scope",
        return_value=fake_scope,
    ):
        out = add_sentry_trace_id(None, "info", {"message": "hi"})
    assert "trace_id" not in out


def test_add_sentry_trace_id_populates_when_scope_active():
    """A valid traceparent string yields trace_id + span_id top-level."""
    fake_scope = MagicMock()
    fake_scope.get_traceparent.return_value = "abc123def456-789xyz"
    with patch(
        "python_sentry_logger_wrapper._processors.sentry_sdk.get_current_scope",
        return_value=fake_scope,
    ):
        out = add_sentry_trace_id(None, "info", {"message": "hi"})
    assert out["trace_id"] == "abc123def456"
    assert out["span_id"] == "789xyz"
