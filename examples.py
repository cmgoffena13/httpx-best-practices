from client import AsyncProductionHTTPClient, SyncProductionHTTPClient
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def async_examples():
    """Async examples using AsyncProductionHTTPClient."""

    # Example 1: Using context manager (automatic cleanup)
    logger.info("=== Example 1: Context Manager (auto cleanup) ===")
    async with AsyncProductionHTTPClient(
        base_url="https://jsonplaceholder.typicode.com"
    ) as client:
        response = await client.get("/posts/1")
        logger.info(f"Status: {response.status_code}, Data: {response.json()}")

    # Example 2: Explicit lifecycle management
    logger.info("\n=== Example 2: Manual lifecycle (explicit close) ===")
    client = AsyncProductionHTTPClient(base_url="https://jsonplaceholder.typicode.com")
    try:
        response = await client.get("/posts/2")
        logger.info(f"Status: {response.status_code}, Data: {response.json()}")
    finally:
        await client.close()  # Important: must call close() to cleanup connection pool

    # Example 3: Using in your own class
    logger.info("\n=== Async Example 3: Custom class with lifecycle management ===")

    class MyApiClient:
        """Example async API client."""

        def __init__(self):
            self.client = AsyncProductionHTTPClient(
                base_url="https://jsonplaceholder.typicode.com",
                request_timeout=10.0,
                max_attempts=4,
            )
            self._closed = False
            logger.info("MyApiClient initialized")

        async def get_post(self, post_id: int):
            response = await self.client.get(f"/posts/{post_id}")
            return response.json()

        async def close(self):
            if self.client and not self._closed:
                await self.client.close()
                self._closed = True
                logger.info("MyApiClient closed")

        def __del__(self):
            if hasattr(self, "_closed") and not self._closed:
                logger.warning(
                    "MyApiClient destroyed without calling close()! Resource leak possible."
                )

    api_client = MyApiClient()
    try:
        post = await api_client.get_post(1)
        logger.info(f"Fetched post: {post['title']}")
    finally:
        await api_client.close()


def sync_examples():
    """Sync examples using SyncProductionHTTPClient."""

    # Example 1: Context manager
    logger.info("\n=== Sync Example 1: Context Manager ===")
    with SyncProductionHTTPClient(
        base_url="https://jsonplaceholder.typicode.com"
    ) as client:
        response = client.get("/posts/1")
        logger.info(f"Status: {response.status_code}, Data: {response.json()}")

    # Example 2: Manual lifecycle
    logger.info("\n=== Sync Example 2: Manual lifecycle ===")
    client = SyncProductionHTTPClient(base_url="https://jsonplaceholder.typicode.com")
    try:
        response = client.get("/posts/2")
        logger.info(f"Status: {response.status_code}, Data: {response.json()}")
    finally:
        client.close()

    # Example 3: Using in your own class
    logger.info("\n=== Sync Example 3: Custom class with lifecycle management ===")

    class MySyncApiClient:
        """Example sync API client."""

        def __init__(self):
            self.client = SyncProductionHTTPClient(
                base_url="https://jsonplaceholder.typicode.com",
                request_timeout=10.0,
                max_attempts=4,
            )
            self._closed = False
            logger.info("MySyncApiClient initialized")

        def get_post(self, post_id: int):
            response = self.client.get(f"/posts/{post_id}")
            return response.json()

        def close(self):
            if self.client and not self._closed:
                self.client.close()
                self._closed = True
                logger.info("MySyncApiClient closed")

        def __del__(self):
            if hasattr(self, "_closed") and not self._closed:
                logger.warning(
                    "MySyncApiClient destroyed without calling close()! Resource leak possible."
                )

    api_client = MySyncApiClient()
    try:
        post = api_client.get_post(3)
        logger.info(f"Fetched post: {post['title']}")
    finally:
        api_client.close()


asyncio.run(async_examples())
sync_examples()
