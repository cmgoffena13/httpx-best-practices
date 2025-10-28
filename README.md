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
    max_attempts=5
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
from client import ProductionHTTPClient

with ProductionHTTPClient(base_url="https://api.example.com") as client:
    response = client.get("/users/1")
    data = response.json()
```

## Configuration

### Parameters

- `base_url` (Optional[str]): Base URL for requests (uses relative paths)
- `connect_timeout` (float): Connection establishment timeout (default: 5.0)
- `read_timeout` (float): Read timeout for response data (default: 10.0)
- `write_timeout` (float): Write timeout for request data (default: 5.0)
- `pool_timeout` (float): Connection pool timeout (default: 2.0)
- `max_connections` (int): Maximum total connections in pool (default: 50)
- `max_keepalive_connections` (int): Maximum keepalive connections (default: 20)
- `keepalive_expiry` (float): Keepalive connection expiry time in seconds (default: 30.0)
- `max_attempts` (int): Maximum total attempts including initial request (default: 5)
- `default_headers` (Optional[dict]): Headers to include on all requests

### Retry Behavior

**Retries on:**
- `429` Too Many Requests (respects `Retry-After` header)
- `500` Internal Server Error
- `502` Bad Gateway
- `503` Service Unavailable (respects `Retry-After` header)
- `504` Gateway Timeout
- `408` Request Timeout
- `104` Connection Reset
- Network errors, timeouts, connection errors

**Never retries:**
- `4xx` client errors (except 429, 408, 104)
- Success responses

### Backoff Strategy

Exponential backoff with jitter: `random(0.8, 1.0) * 2^attempt` seconds

With `max_attempts=5` (default):
- Retry 1: 0.8-1.0 seconds (after initial failure)
- Retry 2: 1.6-2.0 seconds
- Retry 3: 3.2-4.0 seconds
- Retry 4: 6.4-8.0 seconds

Example:
```python
client = AsyncProductionHTTPClient(
    max_attempts=5  # Will try up to 5 times total
)
```

## Advanced Usage

### Custom Configuration

Fine-tune client behavior for your specific needs:

```python
# High-performance configuration
client = AsyncProductionHTTPClient(
    base_url="https://api.example.com",
    connect_timeout=3.0,        # Quick connection
    read_timeout=15.0,          # Allow for large responses
    max_connections=100,        # More concurrent connections
    max_keepalive_connections=50, # More persistent connections
    keepalive_expiry=60.0,     # Keep connections longer
)
```

### Custom Headers

```python
client = AsyncProductionHTTPClient(
    base_url="https://api.example.com",
    default_headers={
        "Authorization": "Bearer your-token-here",
        "User-Agent": "MyApp/1.0"
    }
)
```

### In Your Own Class

```python
class MyApiClient:
    """Example async API client with lifecycle management."""
    
    def __init__(self):
        self.client = AsyncProductionHTTPClient(
            base_url="https://api.example.com",
            max_attempts=5
        )
        self._closed = False
    
    async def fetch_user(self, user_id: int):
        """Fetch user data from the API."""
        response = await self.client.get(f"/users/{user_id}")
        return response.json()
    
    async def close(self):
        """Clean up the HTTP client."""
        if self.client and not self._closed:
            await self.client.close()
            self._closed = True
    
    def __del__(self):
        """Warn if client wasn't properly closed."""
        if hasattr(self, '_closed') and not self._closed:
            print("Warning: MyApiClient destroyed without calling close()! Resource leak possible.")

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

The client implements comprehensive retry logic for both HTTP status codes and network exceptions:

#### HTTP Status Code Retries
Retries on transient server errors and rate limiting:
- `429` Too Many Requests (respects `Retry-After` header)
- `500` Internal Server Error
- `502` Bad Gateway  
- `503` Service Unavailable (respects `Retry-After` header)
- `504` Gateway Timeout
- `408` Request Timeout
- `104` Connection Reset

#### Exception Retries
Retries on all httpx network-related exceptions:
- **TimeoutException**: Request timed out
- **NetworkError**: General network connectivity issues  
- **ConnectError**: Failed to establish connection
- **ConnectTimeout**: Connection establishment timed out
- **ReadTimeout**: Reading response timed out
- **PoolTimeout**: Connection pool exhausted
- **LocalProtocolError**: Local protocol violations

#### What's Never Retried
- `4xx` client errors (except 429, 408, 104)
- Success responses (2xx)
- POST requests (not idempotent)

All retries use exponential backoff with jitter to prevent thundering herd problems.

#### Scalable Design
The retry logic is designed to be easily extensible. New HTTP status codes or httpx exceptions can be added to the `RETRIABLE_STATUS_CODES` and `HTTPX_EXCEPTIONS` dictionaries respectively, making the retry behavior configurable without code changes.

### Why POST Requests Are Not Retried

**POST requests are never automatically retried** to prevent duplicate side effects. Here's why:

**The Problem with Retrying POST:**
- POST is **not idempotent** - sending the same request multiple times can cause different effects
- A 500 response might mean "the server received your data but crashed before responding"
- Retrying could cause the same data to be processed **twice**

**Other methods ARE retried** because they're idempotent:
- **GET**: Safe to retry - just reading data
- **PUT**: Idempotent - same request twice = same result
- **DELETE**: Idempotent - deleting already deleted is fine

### Exponential Backoff + Jitter

Prevents all clients from retrying at the same time:

```
Client 1: retries at 0.85s, 1.7s, 3.5s
Client 2: retries at 0.92s, 1.9s, 3.8s
Client 3: retries at 0.88s, 1.6s, 3.3s
```

### Retry-After Support

For `429` (rate limiting) and `503` (service unavailable) responses, respects the server's `Retry-After` header:

```python
# Server responds: 429 Too Many Requests or 503 Service Unavailable
# Headers: Retry-After: 60
# Client waits 60 seconds before retry instead of using exponential backoff
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

**Use `ProductionHTTPClient` when:**
- Writing synchronous code (scripts, CLI tools, simple backends)
- You need simple blocking behavior

**Use `AsyncProductionHTTPClient` when:**
- Building async web applications (FastAPI, Quart, etc.)
- Handling concurrent requests efficiently
- Want better performance with multiple concurrent requests

## Connection Pool & Timeout Configuration

The clients provide comprehensive control over connection behavior and timeouts:

### Timeout Configuration

**Individual timeout controls:**
- `connect_timeout=5.0`: Max seconds to establish TCP connection
- `read_timeout=10.0`: Max seconds to receive response data  
- `write_timeout=5.0`: Max seconds to send request data
- `pool_timeout=2.0`: Max seconds to acquire connection from pool

**Timeout tuning scenarios:**
```python
# Slow APIs with large responses
client = AsyncProductionHTTPClient(
    connect_timeout=5.0,    # Quick connection
    read_timeout=30.0,      # Allow time for large responses
    write_timeout=10.0,     # Reasonable upload time
)

# Fast APIs with quick responses  
client = AsyncProductionHTTPClient(
    connect_timeout=2.0,    # Quick connection
    read_timeout=5.0,       # Fast response expected
    write_timeout=3.0,      # Quick upload
)
```

### Connection Pool Configuration

**Pool limits and behavior:**
- `max_connections=50`: Total connections in the pool
- `max_keepalive_connections=20`: Connections kept alive for reuse
- `keepalive_expiry=30.0`: Seconds to keep connections alive

**Pool tuning scenarios:**
```python
# High-concurrency applications
client = AsyncProductionHTTPClient(
    max_connections=200,           # More total connections
    max_keepalive_connections=100, # More persistent connections
    keepalive_expiry=60.0,        # Keep connections longer
)

# Memory-constrained environments
client = AsyncProductionHTTPClient(
    max_connections=10,           # Fewer total connections
    max_keepalive_connections=5,  # Minimal keepalive
    keepalive_expiry=10.0,        # Shorter keepalive time
)

# High-traffic APIs with many hosts
client = AsyncProductionHTTPClient(
    max_connections=100,           # More connections for multiple hosts
    max_keepalive_connections=50,  # Balance between reuse and memory
    keepalive_expiry=15.0,        # Shorter expiry for dynamic traffic
)
```

### Production Recommendations

**For most production applications:**
- Use default timeouts unless you have specific requirements
- Increase `max_connections` if you hit pool exhaustion
- Adjust `keepalive_expiry` based on your traffic patterns
- Monitor connection pool metrics in production

**Warning signs to watch for:**
- `PoolTimeout` exceptions → Increase `max_connections` or `pool_timeout`
- Frequent connection establishment → Increase `max_keepalive_connections`
- Memory usage growing → Decrease pool limits
- Slow response times → Check timeout values

## Requirements

- Python >= 3.12
- httpx[http2] >= 0.28.1
- pendulum >= 3.0.0 (for Retry-After date parsing)