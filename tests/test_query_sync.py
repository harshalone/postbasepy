import httpx
import respx

from postbasepy import create_client


@respx.mock
def test_select_builds_expected_body():
    route = respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "1", "title": "Hello"}], "count": 1})
    )
    client = create_client("https://example.com", "pb_anon_test", project_id="proj1")

    result = (
        client.from_("posts")
        .select("id, title")
        .eq("status", "published")
        .order("created_at", ascending=False)
        .limit(10)
        .execute()
    )

    assert result.error is None
    assert result.data == [{"id": "1", "title": "Hello"}]
    assert result.count == 1

    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer pb_anon_test"
    import json

    body = json.loads(sent.content)
    assert body["operation"] == "select"
    assert body["table"] == "posts"
    assert body["columns"] == ["id", "title"]
    assert body["filters"] == [{"column": "status", "operator": "eq", "value": "published"}]
    assert body["order"] == [{"column": "created_at", "ascending": False}]
    assert body["limit"] == 10


@respx.mock
def test_select_with_alias_renames_result_keys():
    respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "1", "name": "Foo"}], "count": None})
    )
    client = create_client("https://example.com", "pb_anon_test")

    result = client.from_("apis").select("apis.id as api_id, apis.name").execute()
    assert result.data == [{"api_id": "1", "name": "Foo"}]


@respx.mock
def test_single_errors_when_no_rows():
    respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [], "count": 0})
    )
    client = create_client("https://example.com", "pb_anon_test")
    result = client.from_("posts").select().eq("id", "missing").single()
    assert result.data is None
    assert result.error == "No rows returned"


@respx.mock
def test_maybe_single_returns_none_without_error():
    respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [], "count": 0})
    )
    client = create_client("https://example.com", "pb_anon_test")
    result = client.from_("posts").select().eq("id", "missing").maybe_single()
    assert result.data is None
    assert result.error is None


@respx.mock
def test_insert_returns_single_row():
    respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "1", "title": "New"}], "count": None}
        )
    )
    client = create_client("https://example.com", "pb_anon_test")
    result = client.from_("posts").insert({"title": "New"}).select().single()
    assert result.data == {"id": "1", "title": "New"}


@respx.mock
def test_query_error_response():
    respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(400, json={"error": "bad request"})
    )
    client = create_client("https://example.com", "pb_anon_test")
    result = client.from_("posts").select().execute()
    assert result.data is None
    assert result.error == "bad request"


@respx.mock
def test_or_filter_sent_as_or_filters():
    route = respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [], "count": 0})
    )
    client = create_client("https://example.com", "pb_anon_test")
    client.from_("users").select().or_("email.ilike.%a%,name.ilike.%a%").execute()

    import json

    body = json.loads(route.calls[0].request.content)
    assert body["orFilters"] == [
        [
            {"column": "email", "operator": "ilike", "value": "%a%"},
            {"column": "name", "operator": "ilike", "value": "%a%"},
        ]
    ]


@respx.mock
def test_join_sent_with_type():
    route = respx.post("https://example.com/api/db/query").mock(
        return_value=httpx.Response(200, json={"data": [], "count": 0})
    )
    client = create_client("https://example.com", "pb_anon_test")
    client.from_("orders").join("users", on="orders.user_id = users.id", type="left").select(
        "orders.id, users.email"
    ).execute()

    import json

    body = json.loads(route.calls[0].request.content)
    assert body["joins"] == [{"table": "users", "on": "orders.user_id = users.id", "type": "left"}]
