"""Renderer parameter — json / console / auto behavior end-to-end."""

from __future__ import annotations

import json
import logging
import sys
from unittest.mock import patch

import pytest
import structlog

from python_sentry_logger_wrapper import get_logger


def _emit_and_capture(
    capsys, logger_name: str = "svc", message: str = "hello-renderer"
):
    """Emit one log line via stdlib logging (the path Sentry hooks) and capture stdout."""
    capsys.readouterr()  # drain anything from init
    logger = logging.getLogger(logger_name)
    logger.info(message)
    return capsys.readouterr().out


def test_json_renderer_produces_parseable_json(capsys):
    get_logger("svc", renderer="json")
    out = _emit_and_capture(capsys)
    assert out.strip(), "expected at least one log line on stdout"
    last_line = out.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["message"] == "hello-renderer"
    assert payload["log_level"] == "INFO"


def test_console_renderer_is_not_json(capsys):
    get_logger("svc", renderer="console")
    out = _emit_and_capture(capsys)
    assert "hello-renderer" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip().splitlines()[-1])


def test_auto_renderer_resolves_to_console_under_tty(capsys):
    with patch.object(sys.stdout, "isatty", return_value=True, create=True):
        get_logger("svc", renderer="auto")
    out = _emit_and_capture(capsys)
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip().splitlines()[-1])
    assert "hello-renderer" in out


def test_auto_renderer_resolves_to_json_when_piped(capsys):
    with patch.object(sys.stdout, "isatty", return_value=False, create=True):
        get_logger("svc", renderer="auto")
    out = _emit_and_capture(capsys)
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["message"] == "hello-renderer"


def test_console_renderer_drops_format_exc_info_from_chain():
    """ConsoleRenderer handles raw exc_info itself; format_exc_info would stringify it."""
    get_logger("svc", renderer="console")
    processors = structlog.get_config()["processors"]
    assert structlog.processors.format_exc_info not in processors


def test_json_renderer_includes_format_exc_info_in_chain():
    get_logger("svc", renderer="json")
    processors = structlog.get_config()["processors"]
    assert structlog.processors.format_exc_info in processors


def test_invalid_renderer_raises():
    with pytest.raises(ValueError, match="renderer must be one of"):
        get_logger("svc", renderer="xml")  # type: ignore[arg-type]
