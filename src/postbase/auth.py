"""Synchronous auth client — /api/auth/v1/{projectId}/... ."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from ._internal import random_verifier_pair
from .types import (
    AuthChangeEvent,
    AuthResponse,
    AuthUser,
    Cookie,
    CookieAdapter,
    CookieToSet,
    NativeOAuthProvider,
    Session,
)

AuthListener = Callable[[AuthChangeEvent, Optional[Session]], None]


class Unsubscribe:
    def __init__(self, fn: Callable[[], None]) -> None:
        self._fn = fn

    def unsubscribe(self) -> None:
        self._fn()


def _session_cookie(cookies: List[Cookie]) -> Optional[Cookie]:
    for c in cookies:
        if (
            c.name.startswith("postbase-session")
            or c.name == "next-auth.session-token"
            or c.name == "__Secure-next-auth.session-token"
        ):
            return c
    return None


def _access_token(session: Optional[Session]) -> Optional[str]:
    return session.access_token if session else None


def _refresh_token(session: Optional[Session]) -> Optional[str]:
    return session.refresh_token if session else None


class AuthAdminClient:
    """Admin methods — require a service-role key."""

    def __init__(self, http: httpx.Client, base_url: str, api_key: str, project_id: str) -> None:
        self._http = http
        self._admin_base = f"{base_url}/api/auth/v1/{project_id}/admin/users"
        self._api_key = api_key

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"}

    def list_users(
        self, page: Optional[int] = None, per_page: Optional[int] = None
    ) -> Dict[str, Any]:
        params: Dict[str, str] = {}
        if page:
            params["page"] = str(page)
        if per_page:
            params["perPage"] = str(per_page)
        try:
            res = self._http.get(self._admin_base, headers=self._headers(), params=params)
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return {"data": None, "error": str(err)}
        if res.is_error:
            return {"data": None, "error": json_body.get("error", "Failed to list users")}
        users = [AuthUser.from_dict(u) for u in json_body.get("users", [])]
        return {"data": {"users": users, "total": json_body.get("total")}, "error": None}

    def get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        try:
            res = self._http.get(f"{self._admin_base}/{user_id}", headers=self._headers())
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return {"data": {"user": None}, "error": str(err)}
        if res.is_error:
            return {"data": {"user": None}, "error": json_body.get("error", "User not found")}
        return {"data": {"user": AuthUser.from_dict(json_body.get("user"))}, "error": None}

    def create_user(
        self,
        email: str,
        password: Optional[str] = None,
        email_confirm: Optional[bool] = None,
        user_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"email": email}
        if password is not None:
            payload["password"] = password
        if email_confirm is not None:
            payload["email_confirm"] = email_confirm
        if user_metadata is not None:
            payload["user_metadata"] = user_metadata
        try:
            res = self._http.post(self._admin_base, headers=self._headers(), json=payload)
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return {"data": {"user": None}, "error": str(err)}
        if res.is_error:
            return {
                "data": {"user": None},
                "error": json_body.get("error", "Failed to create user"),
            }
        return {"data": {"user": AuthUser.from_dict(json_body.get("user"))}, "error": None}

    def update_user_by_id(self, user_id: str, **attributes: Any) -> Dict[str, Any]:
        try:
            res = self._http.patch(
                f"{self._admin_base}/{user_id}", headers=self._headers(), json=attributes
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return {"data": {"user": None}, "error": str(err)}
        if res.is_error:
            return {
                "data": {"user": None},
                "error": json_body.get("error", "Failed to update user"),
            }
        return {"data": {"user": AuthUser.from_dict(json_body.get("user"))}, "error": None}

    def delete_user(self, user_id: str) -> Dict[str, Any]:
        try:
            res = self._http.delete(f"{self._admin_base}/{user_id}", headers=self._headers())
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return {"data": None, "error": str(err)}
        if res.is_error:
            return {"data": None, "error": json_body.get("error", "Failed to delete user")}
        return {"data": None, "error": None}


class AuthClient:
    def __init__(
        self,
        http: httpx.Client,
        base_url: str,
        api_key: str,
        project_id: str,
        extra_headers: Optional[Dict[str, str]] = None,
        cookie_adapter: Optional[CookieAdapter] = None,
    ) -> None:
        self._http = http
        self._base_url = base_url
        self._api_key = api_key
        self._auth_base = f"{base_url}/api/auth/v1/{project_id}"
        self._extra_headers = extra_headers or {}
        self._cookie_adapter = cookie_adapter
        self._listeners: List[AuthListener] = []
        self._current_session: Optional[Session] = None
        self._pkce: Dict[str, str] = {}

        self.admin = AuthAdminClient(http, base_url, api_key, project_id)

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            **self._extra_headers,
        }

    def _notify(self, event: AuthChangeEvent, session: Optional[Session]) -> None:
        self._current_session = session
        for fn in list(self._listeners):
            fn(event, session)

    # ─── Sign-up / sign-in ───────────────────────────────────────────────

    def sign_up(
        self,
        email: str,
        password: str,
        remember_me: Optional[bool] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> AuthResponse:
        try:
            res = self._http.post(
                f"{self._auth_base}/signup",
                headers=self._headers(),
                json={
                    "email": email,
                    "password": password,
                    "data": data,
                    "remember_me": remember_me,
                },
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return AuthResponse(user=None, session=None, error=str(err))
        if res.is_error:
            return AuthResponse(
                user=None, session=None, error=json_body.get("error", "Sign up failed")
            )
        session = Session.from_dict(json_body.get("session"))
        user = AuthUser.from_dict(json_body.get("user"))
        if session:
            self._notify("SIGNED_IN", session)
        return AuthResponse(user=user, session=session, error=None)

    def sign_in_with_password(
        self, email: str, password: str, remember_me: Optional[bool] = None
    ) -> AuthResponse:
        try:
            res = self._http.post(
                f"{self._auth_base}/token",
                headers=self._headers(),
                json={
                    "email": email,
                    "password": password,
                    "grant_type": "password",
                    "remember_me": remember_me,
                },
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return AuthResponse(user=None, session=None, error=str(err))
        if res.is_error:
            return AuthResponse(
                user=None, session=None, error=json_body.get("error", "Sign in failed")
            )
        session = Session.from_dict(json_body.get("session"))
        user = AuthUser.from_dict(json_body.get("user"))
        self._notify("SIGNED_IN", session)
        return AuthResponse(user=user, session=session, error=None)

    def sign_in_with_otp(
        self,
        email: str,
        type: str = "otp",
        redirect_to: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        try:
            res = self._http.post(
                f"{self._auth_base}/otp",
                headers=self._headers(),
                json={"email": email, "type": type, "redirectTo": redirect_to},
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return {"error": str(err)}
        if res.is_error:
            return {"error": json_body.get("error", "OTP send failed")}
        return {"error": None}

    def verify_otp(
        self, email: str, token: str, remember_me: Optional[bool] = None
    ) -> AuthResponse:
        try:
            res = self._http.post(
                f"{self._auth_base}/verify",
                headers=self._headers(),
                json={"email": email, "token": token, "remember_me": remember_me},
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return AuthResponse(user=None, session=None, error=str(err))
        if res.is_error:
            return AuthResponse(
                user=None, session=None, error=json_body.get("error", "Verification failed")
            )
        session = Session.from_dict(json_body.get("session"))
        user = AuthUser.from_dict(json_body.get("user"))
        self._notify("SIGNED_IN", session)
        return AuthResponse(user=user, session=session, error=None)

    def sign_in_with_id_token(
        self,
        provider: NativeOAuthProvider,
        id_token: str,
        nonce: Optional[str] = None,
        remember_me: Optional[bool] = None,
    ) -> AuthResponse:
        try:
            res = self._http.post(
                f"{self._auth_base}/oauth/id-token",
                headers=self._headers(),
                json={
                    "provider": provider,
                    "id_token": id_token,
                    "nonce": nonce,
                    "remember_me": remember_me,
                },
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return AuthResponse(user=None, session=None, error=str(err))
        if res.is_error:
            return AuthResponse(
                user=None, session=None, error=json_body.get("error", "Sign in failed")
            )
        session = Session.from_dict(json_body.get("session"))
        user = AuthUser.from_dict(json_body.get("user"))
        self._notify("SIGNED_IN", session)
        return AuthResponse(user=user, session=session, error=None)

    # ─── OAuth (PKCE, redirect-based) ────────────────────────────────────

    def get_oauth_sign_in_url(
        self,
        provider: str,
        redirect_to: Optional[str] = None,
        scopes: Optional[str] = None,
    ) -> Dict[str, str]:
        """Build the provider authorize URL for a PKCE OAuth flow.

        Unlike the browser SDK, there is no `window.location` to redirect —
        the caller (a web framework route handler) issues the HTTP redirect
        itself. Persist `code_verifier` and `state` (e.g. in a server-side
        session or short-lived cookie) and pass them to
        `handle_oauth_callback` when the provider redirects back.
        """
        code_verifier, code_challenge, state = random_verifier_pair()
        self._pkce[state] = code_verifier

        authorize_base = f"{self._auth_base}/oauth/authorize"
        params = {
            "provider": provider,
            "code_challenge": code_challenge,
            "state": state,
            "redirect_to": redirect_to or "",
        }
        if scopes:
            params["scopes"] = scopes
        authorize_url = f"{authorize_base}?{urlencode(params)}"
        return {"url": authorize_url, "code_verifier": code_verifier, "state": state}

    def handle_oauth_callback(self, callback_url: str) -> AuthResponse:
        """Parse the tokens Postbase appends as query params on the OAuth
        callback redirect and turn them into a `Session`."""
        parsed = urlparse(callback_url)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        error = params.get("error")
        if error:
            return AuthResponse(user=None, session=None, error=error)

        access_token = params.get("access_token")
        refresh_token = params.get("refresh_token")
        expires_at = params.get("expires_at")
        refresh_token_expires_at = params.get("refresh_token_expires_at")
        user_b64 = params.get("user")

        if not access_token or not refresh_token or not expires_at:
            return AuthResponse(user=None, session=None, error=None)

        user: Optional[AuthUser] = None
        if user_b64:
            import base64
            import json

            try:
                padded = user_b64 + "=" * (-len(user_b64) % 4)
                decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
                user = AuthUser.from_dict(json.loads(decoded))
            except Exception:  # noqa: BLE001
                user = None

        session = Session(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=float(expires_at),
            refresh_token_expires_at=(
                float(refresh_token_expires_at) if refresh_token_expires_at else None
            ),
            user=user or AuthUser(id="", email=""),
        )
        self._notify("SIGNED_IN", session)
        return AuthResponse(user=user, session=session, error=None)

    # ─── Session / user ──────────────────────────────────────────────────

    def sign_out(self, access_token: Optional[str] = None) -> Dict[str, Optional[str]]:
        try:
            token = access_token or _access_token(self._current_session)
            headers = self._headers()
            if token:
                headers["X-Postbase-Token"] = token
            self._http.post(f"{self._auth_base}/logout", headers=headers)
            self._notify("SIGNED_OUT", None)
            return {"error": None}
        except Exception as err:  # noqa: BLE001
            return {"error": str(err)}

    def get_session(self) -> Dict[str, Any]:
        try:
            if self._cookie_adapter:
                cookies = self._cookie_adapter.get_all()
                cookie = _session_cookie(cookies)  # type: ignore[arg-type]
                if not cookie:
                    return {"data": {"session": None}, "error": None}
                headers = self._headers()
                headers["X-Postbase-Session"] = cookie.value
                res = self._http.get(f"{self._auth_base}/session", headers=headers)
                if res.is_error:
                    return {"data": {"session": None}, "error": None}
                json_body = res.json()
                return {
                    "data": {"session": Session.from_dict(json_body.get("session"))},
                    "error": None,
                }

            if self._current_session:
                return {"data": {"session": self._current_session}, "error": None}

            res = self._http.get(f"{self._auth_base}/session", headers=self._headers())
            if res.is_error:
                return {"data": {"session": None}, "error": None}
            json_body = res.json()
            return {"data": {"session": Session.from_dict(json_body.get("session"))}, "error": None}
        except Exception as err:  # noqa: BLE001
            return {"data": {"session": None}, "error": str(err)}

    def get_user(self, jwt: Optional[str] = None) -> Dict[str, Any]:
        try:
            token = jwt
            if not token and self._cookie_adapter:
                session_result = self.get_session()
                session = session_result["data"]["session"]
                token = session.access_token if session else None
                if not token:
                    return {"data": {"user": None}, "error": None}
            else:
                token = token or _access_token(self._current_session)

            headers = self._headers()
            if token:
                headers["X-Postbase-Token"] = token
            res = self._http.get(f"{self._auth_base}/user", headers=headers)
            json_body = res.json()
            if res.is_error:
                return {
                    "data": {"user": None},
                    "error": json_body.get("error", "Failed to get user"),
                }
            return {"data": {"user": AuthUser.from_dict(json_body.get("user"))}, "error": None}
        except Exception as err:  # noqa: BLE001
            return {"data": {"user": None}, "error": str(err)}

    def update_user(
        self,
        name: Optional[str] = None,
        image: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            token = _access_token(self._current_session)
            headers = self._headers()
            if token:
                headers["X-Postbase-Token"] = token
            payload: Dict[str, Any] = {}
            if name is not None:
                payload["name"] = name
            if image is not None:
                payload["image"] = image
            if data is not None:
                payload["data"] = data
            res = self._http.patch(f"{self._auth_base}/user", headers=headers, json=payload)
            json_body = res.json()
            if res.is_error:
                return {
                    "data": {"user": None},
                    "error": json_body.get("error", "Failed to update user"),
                }
            self._notify("USER_UPDATED", self._current_session)
            return {"data": {"user": AuthUser.from_dict(json_body.get("user"))}, "error": None}
        except Exception as err:  # noqa: BLE001
            return {"data": {"user": None}, "error": str(err)}

    def sign_in_with_email_otp(self, email: str) -> Dict[str, Any]:
        try:
            res = self._http.post(
                f"{self._auth_base}/email-otp", headers=self._headers(), json={"email": email}
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return {"data": None, "error": str(err)}
        if res.is_error:
            return {"data": None, "error": json_body.get("error", "Email OTP send failed")}
        return {"data": {"message": json_body.get("message", "OTP sent")}, "error": None}

    def verify_email_otp(
        self, email: str, code: str, remember_me: Optional[bool] = None
    ) -> AuthResponse:
        try:
            res = self._http.post(
                f"{self._auth_base}/email-otp/verify",
                headers=self._headers(),
                json={"email": email, "code": code, "remember_me": remember_me},
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return AuthResponse(user=None, session=None, error=str(err))
        if res.is_error:
            return AuthResponse(
                user=None, session=None, error=json_body.get("error", "Verification failed")
            )
        session = Session.from_dict(json_body.get("session"))
        user = AuthUser.from_dict(json_body.get("user"))
        self._notify("SIGNED_IN", session)
        return AuthResponse(user=user, session=session, error=None)

    def refresh_session(self, refresh_token: Optional[str] = None) -> AuthResponse:
        try:
            token = refresh_token or _refresh_token(self._current_session)
            res = self._http.post(
                f"{self._auth_base}/token",
                headers=self._headers(),
                json={"refresh_token": token, "grant_type": "refresh_token"},
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return AuthResponse(user=None, session=None, error=str(err))
        if res.is_error:
            return AuthResponse(
                user=None, session=None, error=json_body.get("error", "Refresh failed")
            )
        session = Session.from_dict(json_body.get("session"))
        user = AuthUser.from_dict(json_body.get("user"))
        self._notify("TOKEN_REFRESHED", session)
        return AuthResponse(user=user, session=session, error=None)

    def set_remember_me(self, remember_me: bool) -> AuthResponse:
        try:
            token = _refresh_token(self._current_session)
            if not token:
                return AuthResponse(user=None, session=None, error="No active session")
            res = self._http.patch(
                f"{self._auth_base}/session",
                headers=self._headers(),
                json={"refresh_token": token, "remember_me": remember_me},
            )
            json_body = res.json()
        except Exception as err:  # noqa: BLE001
            return AuthResponse(user=None, session=None, error=str(err))
        if res.is_error:
            return AuthResponse(
                user=None, session=None, error=json_body.get("error", "Update failed")
            )
        session_dict = json_body.get("session")
        session = Session.from_dict(session_dict)
        user = session.user if session else None
        self._notify("TOKEN_REFRESHED", session)
        return AuthResponse(user=user, session=session, error=None)

    def on_auth_state_change(self, callback: AuthListener) -> Unsubscribe:
        self._listeners.append(callback)
        if self._current_session:
            callback("SIGNED_IN", self._current_session)

        def _unsubscribe() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return Unsubscribe(_unsubscribe)

    def set_session(self, session: Session) -> Dict[str, Optional[str]]:
        if not session.access_token or not session.refresh_token:
            return {"error": "Invalid session: access_token and refresh_token are required"}
        self._notify("SIGNED_IN", session)
        if self._cookie_adapter:
            max_age = (
                max(int(session.refresh_token_expires_at - time.time()), 0)
                if session.refresh_token_expires_at
                else 7 * 24 * 60 * 60
            )
            self._cookie_adapter.set_all(
                [
                    CookieToSet(
                        name="postbase-session",
                        value=session.refresh_token,
                        options={
                            "httponly": True,
                            "secure": True,
                            "samesite": "lax",
                            "max_age": max_age,
                            "path": "/",
                        },
                    )
                ]
            )
        return {"error": None}
