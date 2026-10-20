from __future__ import annotations

import platform
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from niannian_desktop.api import APP_VERSION, ApiClient
from niannian_desktop.api import ApiError as ApiError
from niannian_desktop.api import ClientError as ClientError
from niannian_desktop.api import NetworkError as NetworkError
from niannian_desktop.api import normalize_base_url as normalize_base_url


class NianNianClient(ApiClient):
    def me(self) -> dict[str, Any]:
        return self._request("GET", "/v1/me")

    def create_family(self, name: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/families",
            body={"name": name.strip()},
            idempotency_key=str(uuid4()),
        )

    def create_invitation(self, family_id: str, role: str = "ELDER") -> dict[str, Any]:
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        return self._request(
            "POST",
            f"/v1/families/{quote(family_id)}/invitations",
            body={"target_role": role, "expires_at": expires.isoformat(), "max_usage": 1},
            idempotency_key=str(uuid4()),
        )

    def accept_invitation(self, token: str, display_name: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"confirm_identity": True}
        if display_name:
            body["requested_display_name"] = display_name
        return self._request("POST", f"/v1/family-invitations/{quote(token, safe='')}/accept", body=body)

    def register_family_device(self, family_id: str) -> dict[str, Any]:
        device_id = f"windows-family-{uuid4()}"
        result = self._request(
            "POST",
            "/v1/devices/register",
            body={
                "device_id": device_id,
                "device_type": "OTHER",
                "client_kind": "FAMILY_MOBILE",
                "family_id": family_id,
                "app_version": APP_VERSION,
                "os_version": platform.platform(),
                "capabilities": {"desktop": True, "rest_polling": True},
            },
            idempotency_key=str(uuid4()),
        )
        self.binding = result
        return result

    def list_devices(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v1/devices?limit=100").get("items", []))

    def send_text_to_role(self, text: str, role: str = "ELDER", priority: str = "NORMAL") -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/messages",
            body={
                "destination": {"type": "FAMILY_ROLE", "role": role},
                "message_type": "TEXT",
                "priority": priority,
                "payload": {"text": text.strip()},
            },
            idempotency_key=str(uuid4()),
        )

    def message(self, message_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/messages/{quote(message_id)}")
