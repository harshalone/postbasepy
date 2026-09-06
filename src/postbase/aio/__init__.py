"""postbase.aio — asynchronous Postbase client (httpx.AsyncClient based).

Use this in async web frameworks (FastAPI, Starlette, aiohttp servers) or
async scripts. See `postbase` (the top-level package) for the sync client.
"""

from .auth import AsyncAuthAdminClient, AsyncAuthClient
from .client import AsyncClient, create_async_client
from .email import AsyncEmailClient
from .query import AsyncDeleteBuilder, AsyncInsertBuilder, AsyncQueryBuilder, AsyncUpdateBuilder
from .storage import AsyncStorageBucketClient, AsyncStorageClient

__all__ = [
    "create_async_client",
    "AsyncClient",
    "AsyncQueryBuilder",
    "AsyncInsertBuilder",
    "AsyncUpdateBuilder",
    "AsyncDeleteBuilder",
    "AsyncAuthClient",
    "AsyncAuthAdminClient",
    "AsyncStorageClient",
    "AsyncStorageBucketClient",
    "AsyncEmailClient",
]
