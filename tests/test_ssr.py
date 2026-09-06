import httpx
import pytest
import respx

from postbasepy import CookieAdapter, create_client
from postbasepy.aio import create_async_client
from postbasepy.types import Cookie


@respx.mock
def test_sync_client_forwards_session_cookie_as_header():
    route = respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [], "count": 0})
    )
    adapter = CookieAdapter(
        get_all=lambda: [Cookie(name="postbase-session", value="refresh-token-123")],
        set_all=lambda cookies: None,
    )
    client = create_client("https://example.com", "pb_anon_test", cookies=adapter)
    client.from_("posts").select().execute()

    sent = route.calls[0].request
    assert sent.headers["X-Postbase-Session"] == "refresh-token-123"


@pytest.mark.asyncio
@respx.mock
async def test_async_client_supports_async_cookie_adapter():
    route = respx.post("https://example.com/api/db/sql").mock(
        return_value=httpx.Response(200, json={"data": [], "count": 0})
    )

    async def get_all():
        return [Cookie(name="postbase-session", value="refresh-token-async")]

    async def set_all(cookies):
        return None

    adapter = CookieAdapter(get_all=get_all, set_all=set_all)
    client = create_async_client("https://example.com", "pb_anon_test", cookies=adapter)
    await client.sql("SELECT 1")

    sent = route.calls[0].request
    assert sent.headers["X-Postbase-Session"] == "refresh-token-async"
    await client.aclose()


def test_set_session_writes_cookie_with_refresh_ttl():
    written = {}

    def set_all(cookies):
        written["cookies"] = cookies

    adapter = CookieAdapter(get_all=lambda: [], set_all=set_all)
    client = create_client("https://example.com", "pb_anon_test", cookies=adapter)

    from postbasepy.types import AuthUser, Session

    session = Session(
        access_token="at",
        refresh_token="rt",
        expires_at=9999999999,
        refresh_token_expires_at=9999999999,
        user=AuthUser(id="u1", email="a@example.com"),
    )
    result = client.auth.set_session(session)
    assert result["error"] is None
    assert written["cookies"][0].name == "postbase-session"
    assert written["cookies"][0].value == "rt"
