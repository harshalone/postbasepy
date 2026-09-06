import httpx
import pytest
import respx

from postbase.aio import create_async_client

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_async_select_and_await():
    respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "1"}], "count": 1})
    )
    client = create_async_client("https://example.com", "pb_anon_test", project_id="proj1")
    result = await client.from_("posts").select().eq("id", "1")
    assert result.data == [{"id": "1"}]
    await client.aclose()


@respx.mock
async def test_async_single():
    respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "1"}], "count": 1})
    )
    async with create_async_client("https://example.com", "pb_anon_test") as client:
        result = await client.from_("posts").select().eq("id", "1").single()
        assert result.data == {"id": "1"}
        assert result.error is None


@respx.mock
async def test_async_sql():
    respx.post("https://example.com/api/db/sql").mock(
        return_value=httpx.Response(200, json={"data": [{"count": 5}], "count": None})
    )
    async with create_async_client("https://example.com", "pb_anon_test") as client:
        result = await client.sql(
            "SELECT COUNT(*) as count FROM posts WHERE status = $1", ["published"]
        )
        assert result.data == [{"count": 5}]


@respx.mock
async def test_async_rpc():
    respx.post("https://example.com/api/rpc/get_nearby_posts").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "1"}], "count": None})
    )
    async with create_async_client("https://example.com", "pb_anon_test") as client:
        result = await client.rpc("get_nearby_posts", {"lat": 1.0, "lng": 2.0})
        assert result.data == [{"id": "1"}]
