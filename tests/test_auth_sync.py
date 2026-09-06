import httpx
import respx

from postbasepy import create_client


@respx.mock
def test_sign_up_returns_session_and_user():
    respx.post("https://example.com/api/auth/v1/proj1/signup").mock(
        return_value=httpx.Response(
            200,
            json={
                "user": {"id": "u1", "email": "a@example.com"},
                "session": {
                    "accessToken": "at",
                    "refreshToken": "rt",
                    "expiresAt": 9999999999,
                    "user": {"id": "u1", "email": "a@example.com"},
                },
            },
        )
    )
    client = create_client("https://example.com", "pb_anon_test", project_id="proj1")
    response = client.auth.sign_up("a@example.com", "supersecret")
    assert response.error is None
    assert response.user.id == "u1"
    assert response.session.access_token == "at"


@respx.mock
def test_sign_in_with_password_error():
    respx.post("https://example.com/api/auth/v1/proj1/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid credentials"})
    )
    client = create_client("https://example.com", "pb_anon_test", project_id="proj1")
    response = client.auth.sign_in_with_password("a@example.com", "wrong")
    assert response.error == "invalid credentials"
    assert response.user is None


@respx.mock
def test_get_oauth_sign_in_url_contains_pkce_params():
    client = create_client("https://example.com", "pb_anon_test", project_id="proj1")
    result = client.auth.get_oauth_sign_in_url("google", redirect_to="https://app.com/callback")
    assert "code_challenge=" in result["url"]
    assert "state=" in result["url"]
    assert "provider=google" in result["url"]
    assert result["code_verifier"]
    assert result["state"] in result["url"]


def test_handle_oauth_callback_parses_tokens():
    client = create_client("https://example.com", "pb_anon_test", project_id="proj1")
    callback_url = (
        "https://app.com/callback?access_token=at&refresh_token=rt"
        "&expires_at=9999999999&refresh_token_expires_at=8888888888"
    )
    response = client.auth.handle_oauth_callback(callback_url)
    assert response.error is None
    assert response.session.access_token == "at"
    assert response.session.refresh_token == "rt"
    assert response.session.refresh_token_expires_at == 8888888888.0


def test_handle_oauth_callback_with_error_param():
    client = create_client("https://example.com", "pb_anon_test", project_id="proj1")
    response = client.auth.handle_oauth_callback("https://app.com/callback?error=access_denied")
    assert response.error == "access_denied"
    assert response.session is None


@respx.mock
def test_admin_list_users_requires_service_key():
    respx.get("https://example.com/api/auth/v1/proj1/admin/users").mock(
        return_value=httpx.Response(
            200, json={"users": [{"id": "u1", "email": "a@example.com"}], "total": 1}
        )
    )
    client = create_client("https://example.com", "pb_service_test", project_id="proj1")
    result = client.auth.admin.list_users(page=1, per_page=50)
    assert result["error"] is None
    assert result["data"]["total"] == 1
    assert result["data"]["users"][0].id == "u1"
