# python-sentry-logger-wrapper

Standardized structured (JSON) logging package with built-in Sentry integration for Python applications.

## Features

- **Structured JSON logging** - Outputs to stdout for log aggregation systems (ELK, Datadog, etc.)
- **Automatic Sentry integration** - Error tracking and performance monitoring with zero configuration
- **Automatic trace correlation** - Logs across your entire call stack share the same `trace_id`
- **FastAPI automatic request tracing** - Each HTTP request gets a unique trace ID
- **Clean schema** - Standard fields at top level, custom fields nested in `details`

## Requirements

- Python >= 3.8
- FastAPI (required for automatic request tracing)

## Installation

```bash
# Install from GitHub using uv
uv add git+https://github.com/HEAL-Engineering/python-sentry-logger-wrapper.git

# Or using pip
pip install git+https://github.com/HEAL-Engineering/python-sentry-logger-wrapper.git
```

## Quick Start

### Basic Usage with FastAPI

```python
from fastapi import FastAPI
from python_sentry_logger_wrapper import get_logger
import os

# Initialize logger with Sentry BEFORE creating FastAPI app
logger = get_logger(
    service_name="api-service",
    sentry_dsn=os.getenv("SENTRY_DSN"),
    sentry_environment="production"
)

app = FastAPI()

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    logger.info("Fetching user from API")
    user = await fetch_user(user_id)
    return user

async def fetch_user(user_id: int):
    logger.info("Querying database", user_id=user_id)
    return await db.query(...)
```

**What happens automatically:**
- Each HTTP request gets a unique `trace_id`
- ALL logs during that request share the same `trace_id`
- Logs appear in stdout as JSON AND in Sentry with full request context
- Errors are automatically linked to the request that caused them

### Multi-Layer Application Example

```python
# API Layer
from python_sentry_logger_wrapper import get_logger

logger = get_logger("example-api", sentry_dsn=os.getenv("SENTRY_DSN"))

@app.post("/items")
async def create_item(item: Item):
    logger.info("Creating item", item_count=len(item.data))
    result = await item_service.create(item)
    logger.info("Item created", item_id=result.id)
    return result

# Service Layer
logger = get_logger("example-api")

async def create(item: Item):
    logger.info("Validating item")
    await validate_data(item.data)

    logger.info("Processing external request")
    response = await external_service.process(item)

    if not response.success:
        logger.error("External service failed", reason=response.error_code)
        raise ServiceError(response.error_code)

    logger.info("Saving to database")
    return await db.items.create(item)
```

**Console output (all logs share the same `trace_id`):**
```json
{"timestamp": "...", "log_level": "INFO", "service_name": "example-api", "message": "Creating item", "trace_id": "abc123...", "details": {"item_count": 3}}
{"timestamp": "...", "log_level": "INFO", "service_name": "example-api", "message": "Validating item", "trace_id": "abc123...", "details": {}}
{"timestamp": "...", "log_level": "INFO", "service_name": "example-api", "message": "Processing external request", "trace_id": "abc123...", "details": {}}
{"timestamp": "...", "log_level": "INFO", "service_name": "example-api", "message": "Saving to database", "trace_id": "abc123...", "details": {}}
```

**In Sentry:**
- Click the trace to see all logs in timeline
- View request duration, endpoint, and status code
- If an error occurs, see which request caused it with full context

## Log Schema

### Standard Fields (top-level)
- `timestamp` - ISO 8601 UTC timestamp
- `log_level` - INFO, WARNING, ERROR, etc.
- `service_name` - Your service identifier
- `message` - Log message
- `trace_id` - Distributed tracing ID (automatically added by Sentry)

### Custom Fields (nested under `details`)
Any additional fields you pass are automatically nested:

```python
logger.info("User login", user_id=123, ip="10.0.1.100", method="oauth")
# Output: {..., "details": {"user_id": 123, "ip": "10.0.1.100", "method": "oauth"}}
```

## Sentry Configuration

### Get Your DSN
1. Create a project at [sentry.io](https://sentry.io)
2. Copy your DSN from Settings → Client Keys
3. Set it as an environment variable: `export SENTRY_DSN="https://..."`

### Free Tier
Sentry offers 5,000 errors/events per month free - perfect for small projects.

### Configuration Options

```python
logger = get_logger(
    service_name="my-service",
    log_level=logging.INFO,  # Minimum log level for stdout
    sentry_dsn="https://...",  # Optional: enables Sentry
    sentry_environment="production",  # Optional: environment tag
    sentry_sample_rate=0.1  # Optional: sample 10% of traces (reduces costs)
)
```

### What Gets Sent to Sentry

- **ERROR/CRITICAL logs** - Sent as searchable events
- **INFO/WARNING logs** - Sent as breadcrumbs (attached to errors for context)
- **All custom fields** - Searchable in Sentry UI (e.g., `details.user_id:123`)
- **Request context** - Automatic with FastAPI (URL, method, headers, duration)

## Advanced Usage

### Exception Handling

```python
try:
    result = await process_data(item)
except ProcessingError as e:
    logger.error(
        "Data processing failed",
        error_type=type(e).__name__,
        item_id=item.id,
        exc_info=True  # Includes full stack trace
    )
    raise
```

### Different Log Levels

```python
logger.debug("Detailed debugging info", query="SELECT * FROM users")
logger.info("Normal operation", status="healthy")
logger.warning("Degraded performance", latency_ms=2500)
logger.error("Operation failed", retry_count=3)
logger.critical("System down", reason="database_unavailable")
```

## FAQ

**Q: Do I need to pass `trace_id` manually through my functions?**
A: No! It's automatically propagated through your entire call stack via context variables.

**Q: Can I use this without Sentry?**
A: Yes! Just omit `sentry_dsn` and you'll get JSON logs to stdout only.

**Q: Does Sentry integration affect my JSON stdout logs?**
A: No, logs are sent to both Sentry AND stdout independently. Your log aggregation system still works.

**Q: How do I search logs in Sentry?**
A: Custom fields are under `details`, so search like: `details.user_id:123` or `details.transaction_id:txn_*`

**Q: Can I use this without FastAPI?**
A: Yes, but automatic request tracing requires FastAPI. Without it, you'll need to manage trace context manually.

## License

MIT
