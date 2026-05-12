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
from .core import get_logger, reset_configuration

__version__ = "0.1.0"
__all__ = ["get_logger", "reset_configuration"]