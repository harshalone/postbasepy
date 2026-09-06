import httpx
import respx

from postbase import create_client


@respx.mock
def test_upload_sends_multipart_and_returns_path():
    route = respx.post("https://example.com/api/storage/v1/object/avatars/user-1.png").mock(
        return_value=httpx.Response(200, json={"path": "user-1.png"})
    )
    client = create_client("https://example.com", "pb_anon_test")
    result = client.storage.from_("avatars").upload(
        "user-1.png", b"\x89PNG\r\n", content_type="image/png"
    )
    assert result.error is None
    assert result.data == {"path": "user-1.png", "fullPath": "avatars/user-1.png"}
    assert route.calls[0].request.headers["Authorization"] == "Bearer pb_anon_test"


def test_get_public_url():
    client = create_client("https://example.com", "pb_anon_test")
    result = client.storage.from_("avatars").get_public_url("user-1.png")
    assert result["data"]["publicUrl"] == (
        "https://example.com/api/storage/v1/object/public/avatars/user-1.png"
    )


@respx.mock
def test_remove_files():
    route = respx.delete("https://example.com/api/storage/v1/object/avatars").mock(
        return_value=httpx.Response(200, json={"data": [{"name": "user-1.png"}]})
    )
    client = create_client("https://example.com", "pb_anon_test")
    result = client.storage.from_("avatars").remove(["user-1.png"])
    assert result.error is None
    assert result.count == 1
    import json

    assert json.loads(route.calls[0].request.content) == {"prefixes": ["user-1.png"]}


@respx.mock
def test_create_bucket():
    respx.post("https://example.com/api/storage/v1/bucket").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": "avatars",
                    "name": "avatars",
                    "public": True,
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-01T00:00:00Z",
                }
            },
        )
    )
    client = create_client("https://example.com", "pb_anon_test")
    result = client.storage.create_bucket("avatars", public=True)
    assert result.error is None
    assert result.data.id == "avatars"
    assert result.data.public is True
