"""Shared fixtures.

Resets structlog and the package's module-level _is_configured flag between
tests, and provides a patch-set for the Sentry SDK so tests stay offline.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
import structlog

import python_sentry_logger_wrapper.core as core_module


@pytest.fixture(autouse=True)
def reset_logger_config():
    """Reset structlog + the package's configure-once flag between tests.

    Without this, structlog config from one test leaks into the next (process-global
    state), and the _is_configured short-circuit hides side effects we want to assert.
    """
    yield
    structlog.reset_defaults()
    core_module._is_configured = False
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)


@pytest.fixture
def mock_sentry_sdk():
    """Patch sentry_sdk + LoggingIntegration at the import site (core module)."""
    with patch.object(core_module, "sentry_sdk") as mock_sdk, patch.object(
        core_module, "LoggingIntegration"
    ) as mock_logging_integration:
        mock_sdk.init = MagicMock()
        mock_sdk.set_tag = MagicMock()
        mock_sdk.capture_event = MagicMock()
        mock_logging_integration.return_value = MagicMock(
            name="LoggingIntegrationInstance"
        )
        yield {
            "sdk": mock_sdk,
            "init": mock_sdk.init,
            "set_tag": mock_sdk.set_tag,
            "LoggingIntegration": mock_logging_integration,
        }
