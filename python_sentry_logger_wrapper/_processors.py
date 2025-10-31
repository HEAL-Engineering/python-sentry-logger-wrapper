"""Custom processors for heal-logger to shape logs into the standard schema."""
from typing import Any, Dict, Optional
from structlog.types import EventDict, WrappedLogger
import sentry_sdk


STANDARD_FIELDS = {"timestamp", "log_level", "service_name", "message", "trace_id", "logger"}


def remove_processors_meta_safe(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Safely remove structlog's internal metadata fields (_record, _from_structlog).
    Unlike the built-in remove_processors_meta, this doesn't raise KeyError if fields are missing.
    """
    event_dict.pop("_record", None)
    event_dict.pop("_from_structlog", None)
    return event_dict


def rename_and_flatten_fields(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor to rename 'event' to 'message', 'logger_name' to 'service_name',
    and 'level' to 'log_level' to conform to the standard log schema.
    
    Args:
        logger: The wrapped logger instance
        method_name: The name of the method called (e.g., 'info', 'error')
        event_dict: The current state of the log entry
        
    Returns:
        The modified event dictionary
    """
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")

    if "logger_name" in event_dict:
        event_dict["logger_name"] = event_dict.pop("logger_name")
        
    if "level" in event_dict:
        event_dict["log_level"] = event_dict.pop("level").upper()
        
    return event_dict


def add_sentry_trace_id(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor to add Sentry trace_id to logs for correlation with Sentry events.

    Args:
        logger: The wrapped logger instance
        method_name: The name of the method called (e.g., 'info', 'error')
        event_dict: The current state of the log entry

    Returns:
        The modified event dictionary with trace_id added
    """

    try:
        scope = sentry_sdk.get_current_scope()
        if scope:
            traceparent = scope.get_traceparent()
            if traceparent:
                # traceparent format is "trace_id-span_id"
                trace_span_list = traceparent.split("-")
                trace_id = trace_span_list[0]
                span_id = trace_span_list[1]
                event_dict["trace_id"] = trace_id
                event_dict["span_id"] = span_id
            else:
                raise Exception("Couldn't extract trace and span")
    except (AttributeError, Exception) as e:
        print(f"DEBUG: Exception in add_sentry_trace_id: {e}", flush=True)

    return event_dict

def remove_internal_fields(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor to remove non-standard fields that were added by added processors
    """

    for key in list(event_dict.keys()):
        if key.startswith("_"):
            # Remove all internal fields (those starting with _)
            event_dict.pop(key)
        
    return event_dict


def nest_custom_fields(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor to nest all non-standard, custom fields into a 'details' object.
    This keeps the root of the log clean and predictable.

    Args:
        logger: The wrapped logger instance
        method_name: The name of the method called (e.g., 'info', 'error')
        event_dict: The current state of the log entry

    Returns:
        The modified event dictionary with custom fields nested under 'details'
    """

    details: Dict[str, Any] = {}

    for key in list(event_dict.keys()):
        if key.startswith("_"):
            # Remove all internal fields (those starting with _)
            event_dict.pop(key)
        elif key not in STANDARD_FIELDS:
            details[key] = event_dict.pop(key)

    if details:
        event_dict["details"] = details

    return event_dict