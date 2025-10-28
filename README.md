# httpx Best Practices for Production

Production-ready HTTP clients for Python with connection pooling, exponential backoff retries, and proper error handling.

## Features

- ✅ **Connection pooling** - Reuse connections efficiently
- ✅ **Exponential backoff with jitter** - Prevents thundering herd
- ✅ **Smart retry logic** - Only retries transient errors (5xx, 429, timeouts, network errors)
- ✅ **Retry-After support** - Respects server rate limit headers
- ✅ **HTTP/2 support** - Better multiplexing and connection reuse
- ✅ **Configurable timeouts** - Simple timeout configuration
- ✅ **Sync and async variants** - Use whichever fits your needs
- ✅ **Default headers** - Add headers to all requests

## Quick Start

### Async Example

```python
from client import AsyncProductionHTTPClient

# Using context manager (recommended)
async with AsyncProductionHTTPClient(
    base_url="https://api.example.com",
    request_timeout=10.0,
    max_retries=4
) as client:
    response = await client.get("/users/1")
    data = response.json()

# Or manual lifecycle
client = AsyncProductionHTTPClient(base_url="https://api.example.com")
try:
    response = await client.get("/users/1")
finally:
    await client.close()  # Important: cleanup connection pool
```

### Sync Example

```python
from client import SyncProductionHTTPClient

with SyncProductionHTTPClient(base_url="https://api.example.com") as client:
    response = client.get("/users/1")
    data = response.json()
```

## Configuration

### Parameters

- `base_url` (Optional[str]): Base URL for requests (uses relative paths)
- `request_timeout` (float): Total request timeout in seconds (default: 10.0)
  - Connection timeout: min(timeout/2, 5.0) seconds
  - Read timeout: request_timeout seconds
- `max_retries` (int): Maximum retry attempts (default: 4)
- `default_headers` (Optional[dict]): Headers to include on all requests

### Retry Behavior

**Retries on:**
- `429` Too Many Requests (respects `Retry-After` header)
- `500` Internal Server Error
- `502` Bad Gateway
- `503` Service Unavailable
- `504` Gateway Timeout
- `104` Connection Reset
- `408` Request Timeout
- Network errors, timeouts

**Never retries:**
- `4xx` client errors (except 429, 408, 104)
- Success responses

### Backoff Strategy

Exponential backoff with jitter: `random(0.8, 1.0) * 2^attempt` seconds

With `max_retries=4` (default):
- Retry 1: 0.8-1.0 seconds (after initial failure)
- Retry 2: 1.6-2.0 seconds
- Retry 3: 3.2-4.0 seconds
- Retry 4: 6.4-8.0 seconds

Example:
```python
client = AsyncProductionHTTPClient(
    max_retries=4  # Will retry up to 4 times
    # Total possible attempts: 5 (initial + 4 retries)
)
```

## Advanced Usage

### Custom Headers

```python
client = AsyncProductionHTTPClient(
    base_url="https://api.example.com",
    default_headers={
        "User-Agent": "MyApp/1.0",
        "X-Custom-Header": "value"
    }
)
```

### In Your Own Class

```python
class MyApiClient:
    def __init__(self):
        self.client = AsyncProductionHTTPClient(
            base_url="https://api.example.com"
        )
    
    async def fetch_user(self, user_id: int):
        response = await self.client.get(f"/users/{user_id}")
        return response.json()
    
    async def close(self):
        await self.client.close()

# Usage
client = MyApiClient()
try:
    user = await client.fetch_user(1)
finally:
    await client.close()
```

## How It Works

### Connection Pooling

httpx automatically pools connections when you reuse a client:

```python
# ❌ BAD: Creates new connections each time
async with AsyncProductionHTTPClient() as client:
    await client.get("https://api.example.com/users/1")

async with AsyncProductionHTTPClient() as client:
    await client.get("https://api.example.com/users/2")

# ✅ GOOD: Reuses connections
async with AsyncProductionHTTPClient() as client:
    await client.get("/users/1")  # Reuses connection
    await client.get("/users/2")  # Reuses connection
```

### Retry Logic

Only retries **transient errors** that might succeed on retry:

```python
# Will retry on 500, 502, 503, 504
response = await client.get("/api/data")

# Will NOT retry on 400, 401, 403, 404, etc.
# These fail immediately to avoid wasting time
```

### Exponential Backoff + Jitter

Prevents all clients from retrying at the same time:

```
Client 1: retries at 0.85s, 1.7s, 3.5s
Client 2: retries at 0.92s, 1.9s, 3.8s
Client 3: retries at 0.88s, 1.6s, 3.3s
# Tighter jitter, closer to exponential value
```

### Retry-After Support

For `429` responses, respects the server's `Retry-After` header:

```python
# Server responds: 429 Too Many Requests
# Headers: Retry-After: 60
# Client waits 60 seconds before retry
response = await client.get("/rate-limited-endpoint")
```

## Best Practices

1. **Always use context managers** for automatic cleanup:
   ```python
   async with AsyncProductionHTTPClient() as client:
       # Connections auto-closed when done
   ```

2. **Set reasonable timeouts** based on your use case:
   ```python
   # For fast APIs
   client = AsyncProductionHTTPClient(request_timeout=5.0)
   
   # For slow APIs
   client = AsyncProductionHTTPClient(request_timeout=30.0)
   ```

3. **Use base_url** for cleaner code:
   ```python
   client = AsyncProductionHTTPClient(base_url="https://api.example.com")
   await client.get("/users/1")  # vs await client.get("https://api.example.com/users/1")
   ```

4. **Reuse clients** across requests to benefit from connection pooling

5. **Monitor retry patterns** in logs to identify problematic endpoints

## When to Use Sync vs Async

**Use `SyncProductionHTTPClient` when:**
- Writing synchronous code (scripts, CLI tools, simple backends)
- You need simple blocking behavior

**Use `AsyncProductionHTTPClient` when:**
- Building async web applications (FastAPI, Quart, etc.)
- Handling concurrent requests efficiently
- Want better performance with multiple concurrent requests

## Connection Pool Tuning

The default pool limits (20 keepalive, 50 max connections) work well for most use cases. Adjust if you have:

- **High concurrency**: Increase `max_connections`
- **Long-lived processes**: Increase `keepalive_expiry`
- **Memory constraints**: Decrease `max_keepalive_connections`

## Requirements

- Python >= 3.12
- httpx >= 0.28.1
- pendulum >= 3.0.0 (for Retry-After date parsing)

## License

MIT
