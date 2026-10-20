from __future__ import annotations

import platform
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from niannian_desktop.api import APP_VERSION, ApiClient
from niannian_desktop.api import ApiError as ApiError
from niannian_desktop.api import ClientError as ClientError
from niannian_desktop.api import NetworkError as NetworkError
from niannian_desktop.api import normalize_base_url as normalize_base_url


class ElderClient(ApiClient):
    login_kind = "elder"
    default_identifier = "demo-elder"
    default_device_name = "Windows 老人演示端"

    def accept_invitation(self, token: str) -> dict[str, Any]:
        clean = token.strip()
        if not clean:
            raise ClientError("请粘贴子女端生成的邀请令牌。")
        return self._request(
            "POST",
            f"/v1/family-invitations/{quote(clean, safe='')}/accept",
            body={"confirm_identity": True, "requested_display_name": "演示老人"},
        )

    def register_device(self, family_id: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/v1/devices/register",
            body={
                "device_id": f"windows-elder-{uuid4()}",
                "device_type": "OTHER",
                "client_kind": "ELDER_MOBILE",
                "family_id": family_id,
                "app_version": APP_VERSION,
                "os_version": platform.platform(),
                "capabilities": {
                    "desktop_demo": True,
                    "large_text": True,
                    "rest_polling": True,
                },
            },
            idempotency_key=str(uuid4()),
        )
        self.binding = result
        return result

    def reply_to_children(self, text: str, *, important: bool = False) -> dict[str, Any]:
        clean = text.strip()
        if not clean:
            raise ClientError("回复内容不能为空。")
        return self._request(
            "POST",
            "/v1/messages",
            body={
                "destination": {"type": "FAMILY_ROLE", "role": "CHILD"},
                "message_type": "TEXT",
                "priority": "IMPORTANT" if important else "NORMAL",
                "payload": {"text": clean},
            },
            idempotency_key=str(uuid4()),
        )
