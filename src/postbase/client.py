"""Synchronous Postbase client."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypeVar

import httpx

from ._query_state import QueryState
from .auth import AuthClient
from .email import EmailClient
from .query import QueryBuilder
from .storage import StorageClient
from .types import CookieAdapter, QueryResult

T = TypeVar("T")


def _session_cookie_value(cookie_adapter: Optional[CookieAdapter]) -> Optional[str]:
    """Read the session cookie from a sync CookieAdapter.

    The sync `Client` requires `get_all()` to return a plain list, not an
    awaitable — use `AsyncClient` if your cookie source is async.
    """
    if not cookie_adapter:
        return None
    cookies = cookie_adapter.get_all()
    if not isinstance(cookies, list):
        raise TypeError(
            "CookieAdapter.get_all() must return a list for the sync Client — "
            "use postbase.aio.create_async_client() for an async cookie source"
        )
    for c in cookies:
        if (
            c.name.startswith("postbase-session")
            or c.name == "next-auth.session-token"
            or c.name == "__Secure-next-auth.session-token"
        ):
            return c.value
    return None


class Client:
    """Synchronous Postbase client. Create via `create_client()`."""

    def __init__(
        self,
        url: str,
        key: str,
        project_id: str = "",
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[CookieAdapter] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self._project_id = project_id
        self._extra_headers = headers or {}
        self._cookie_adapter = cookies
        self._http = http_client or httpx.Client()

        self.auth = AuthClient(self._http, self.url, key, project_id, self._extra_headers, cookies)
        self.email = EmailClient(self._http, self.url, key, project_id, self._extra_headers)
        self.storage = StorageClient(self._http, self.url, key, self._extra_headers)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def from_(self, table: str) -> QueryBuilder[Dict[str, Any]]:
        state = QueryState(
            base_url=self.url,
            api_key=self.key,
            table=table,
            extra_headers=self._extra_headers,
            session_token=_session_cookie_value(self._cookie_adapter),
        )
        return QueryBuilder(self._http, state)

    def sql(self, query: str, params: Optional[List[Any]] = None) -> QueryResult[Dict[str, Any]]:
        if not self.url:
            raise ValueError(
                "[postbase] url is required — ensure POSTBASE_URL is set in your environment"
            )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.key}",
            **self._extra_headers,
        }
        session_token = _session_cookie_value(self._cookie_adapter)
        if session_token:
            headers["X-Postbase-Session"] = session_token
        try:
            res = self._http.post(
                f"{self.url}/api/db/sql",
                headers=headers,
                json={"query": query, "params": params or []},
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return QueryResult(data=None, count=None, error=str(err))
        if res.is_error:
            return QueryResult(
                data=None, count=None, error=json_body.get("error", "SQL query failed")
            )
        return QueryResult(data=json_body.get("data"), count=json_body.get("count"), error=None)

    def rpc(
        self,
        fn: str,
        args: Optional[Dict[str, Any]] = None,
        count: Optional[str] = None,
        head: bool = False,
    ) -> QueryResult[Dict[str, Any]]:
        if not self.url:
            raise ValueError(
                "[postbase] url is required — ensure POSTBASE_URL is set in your environment"
            )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.key}",
            **self._extra_headers,
        }
        session_token = _session_cookie_value(self._cookie_adapter)
        if session_token:
            headers["X-Postbase-Session"] = session_token
        try:
            method = "HEAD" if head else "POST"
            res = self._http.request(
                method,
                f"{self.url}/api/rpc/{fn}",
                headers=headers,
                json={"args": args or {}, "count": count},
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return QueryResult(data=None, count=None, error=str(err))
        if res.is_error:
            return QueryResult(data=None, count=None, error=json_body.get("error", "RPC failed"))
        return QueryResult(data=json_body.get("data"), count=json_body.get("count"), error=None)


def create_client(
    url: str,
    key: str,
    project_id: str = "",
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[CookieAdapter] = None,
    http_client: Optional[httpx.Client] = None,
) -> Client:
    """Create a synchronous Postbase client.

    Args:
        url: Your Postbase instance URL.
        key: The anon or service-role API key.
        project_id: The project ID, used to scope auth/email endpoints.
        headers: Extra headers sent with every request.
        cookies: A `CookieAdapter` for server-side session forwarding (SSR-style
            usage in a web framework request handler). Omit for scripts/services
            using the anon or service key directly.
        http_client: An existing `httpx.Client` to reuse (e.g. for connection
            pooling across multiple Postbase clients). One is created if omitted.
    """
    return Client(
        url, key, project_id=project_id, headers=headers, cookies=cookies, http_client=http_client
    )
