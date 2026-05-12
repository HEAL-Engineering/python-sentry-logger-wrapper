"""
python-sentry-logger-wrapper: Standardized structured (JSON) logging package with Sentry integration.

This package provides a simple, consistent interface for structured logging
with built-in Sentry support. It ensures all logs are output as JSON to stdout,
making them compatible with centralized logging systems like ELK, Datadog, etc.

Basic Usage:
    from python_sentry_logger_wrapper import get_logger

    logger = get_logger("my-service")
    logger.info("Service started", version="1.0.0")
"""

from importlib.metadata import PackageNotFoundError, version

from .core import get_logger, reset_configuration

try:
    __version__ = version("sentry-struct-logger")
except PackageNotFoundError:
    # Source tree without an installed distribution (e.g. running tests against an uninstalled checkout).
    __version__ = "0.0.0+unknown"

__all__ = ["get_logger", "reset_configuration"]
