"""Synchronous email client — /api/email/v1/{projectId}/send ."""

from __future__ import annotations

from typing import Dict, Optional

import httpx


class EmailClient:
    def __init__(
        self,
        http: httpx.Client,
        base_url: str,
        api_key: str,
        project_id: str,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._http = http
        self._url = f"{base_url}/api/email/v1/{project_id}/send"
        self._api_key = api_key
        self._extra_headers = extra_headers or {}

    def send(
        self,
        to: str,
        subject: str,
        text: Optional[str] = None,
        html: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, object]:
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                **self._extra_headers,
            }
            res = self._http.post(
                self._url,
                headers=headers,
                json={
                    "to": to,
                    "subject": subject,
                    "text": text,
                    "html": html,
                    "replyTo": reply_to,
                },
            )
            json_body = res.json()
            if res.is_error:
                return {"data": None, "error": json_body.get("error", "Failed to send email")}
            return {"data": {"ok": True}, "error": None}
        except Exception as err:  # noqa: BLE001
            return {"data": None, "error": str(err)}
