"""postbase — the official Python client for Postbase.

Postbase is a self-hosted, open-source backend-as-a-service built on
PostgreSQL: a REST query API, authentication, file storage, and row-level
security.

Quick start (sync)::

    from postbasepy import create_client

    postbase = create_client(
        "https://your-postbase-instance.com",
        "pb_anon_your_api_key",
        project_id="your-project-id",
    )
    result = postbase.from_("posts").select().eq("status", "published").execute()

Quick start (async)::

    from postbasepy.aio import create_async_client

    postbase = create_async_client(
        "https://your-postbase-instance.com",
        "pb_anon_your_api_key",
        project_id="your-project-id",
    )
    result = await postbase.from_("posts").select().eq("status", "published").execute()
"""

from .auth import AuthAdminClient, AuthClient
from .client import Client, create_client
from .email import EmailClient
from .query import DeleteBuilder, InsertBuilder, QueryBuilder, UpdateBuilder
from .storage import StorageBucketClient, StorageClient
from .types import (
    AuthChangeEvent,
    AuthResponse,
    AuthUser,
    Bucket,
    Cookie,
    CookieAdapter,
    CookieToSet,
    Filter,
    FilterOperator,
    JoinClause,
    JoinType,
    NativeOAuthProvider,
    QueryResult,
    RealtimeEvent,
    RealtimePayload,
    Session,
    SingleResult,
    StorageObject,
)

__version__ = "0.1.0"

__all__ = [
    "create_client",
    "Client",
    "QueryBuilder",
    "InsertBuilder",
    "UpdateBuilder",
    "DeleteBuilder",
    "AuthClient",
    "AuthAdminClient",
    "StorageClient",
    "StorageBucketClient",
    "EmailClient",
    "AuthUser",
    "Session",
    "AuthResponse",
    "AuthChangeEvent",
    "NativeOAuthProvider",
    "Filter",
    "FilterOperator",
    "JoinClause",
    "JoinType",
    "QueryResult",
    "SingleResult",
    "StorageObject",
    "Bucket",
    "RealtimeEvent",
    "RealtimePayload",
    "Cookie",
    "CookieToSet",
    "CookieAdapter",
    "__version__",
]
