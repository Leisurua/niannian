"""Fictional, deterministic E0-T08 demo rows; no real contact details or media."""

from __future__ import annotations

from uuid import UUID

NAMESPACE = "DEMO_DATA:E0-T08"
FAMILY_NAME = "演示家庭（虚构数据）"
STAMP = "2026-09-01T09:00:00+08:00"
END = "2026-09-07T23:59:00+08:00"


def uid(number: int) -> str:
    value = f"01920000-0000-7000-8000-{number:012x}"
    assert UUID(value).version == 7
    return value


ELDER, CHILD, FAMILY = uid(1), uid(2), uid(3)
MEMORY_OK, MEMORY_PENDING, MEMORY_REVOKED = uid(4), uid(5), uid(6)
REMINDER, EXEC_DONE, EXEC_NO_RESPONSE = uid(7), uid(8), uid(9)
SIGNAL_MISS, SIGNAL_SCAM, SIGNAL_PHYSICAL = uid(10), uid(11), uid(12)
NOTIFICATION_READ, NOTIFICATION_FAILED, ATTEMPT_FAILED = uid(13), uid(14), uid(15)
REPORT_READY, REPORT_FAILED, METRIC = uid(16), uid(17), uid(18)
CONSENT_MEMORY, CONSENT_NOTIFY, CONSENT_REVOKED = uid(19), uid(20), uid(21)
MEMBER_ELDER, MEMBER_CHILD = uid(22), uid(23)
METRIC_DONE = uid(24)
MEMORY_DELETED, DEVICE_DEGRADED, ASSET_DELETE_PENDING, SIGNAL_MISS_FAILED = (uid(n) for n in range(25, 29))

# Only documented data-dictionary columns are used. Table order follows FK order.
ROWS: dict[str, list[dict[str, object]]] = {
    "user": [
        {"id": ELDER, "global_status": "ACTIVE", "display_name": "演示老人", "timezone": "Asia/Shanghai"},
        {"id": CHILD, "global_status": "ACTIVE", "display_name": "演示子女", "timezone": "Asia/Shanghai"},
    ],
    "family": [{"id": FAMILY, "name": FAMILY_NAME, "created_by_user_id": CHILD, "status": "ACTIVE"}],
    "family_member": [
        {"id": MEMBER_ELDER, "family_id": FAMILY, "user_id": ELDER, "role": "ELDER", "status": "ACTIVE", "joined_at": STAMP},
        {"id": MEMBER_CHILD, "family_id": FAMILY, "user_id": CHILD, "role": "CHILD", "status": "ACTIVE", "joined_at": STAMP},
    ],
    "consent": [
        {"id": CONSENT_MEMORY, "family_id": FAMILY, "subject_user_id": ELDER, "grantor_user_id": ELDER,
         "grantee_user_id": CHILD, "scope": "FAMILY_MEMORY", "status": "GRANTED", "version": 1,
         "source": "ONBOARDING", "granted_at": STAMP},
        {"id": CONSENT_NOTIFY, "family_id": FAMILY, "subject_user_id": ELDER, "grantor_user_id": ELDER,
         "grantee_user_id": CHILD, "scope": "NOTIFICATION_TO_FAMILY", "status": "GRANTED", "version": 1,
         "source": "ONBOARDING", "granted_at": STAMP},
        {"id": CONSENT_REVOKED, "family_id": FAMILY, "subject_user_id": ELDER, "grantor_user_id": ELDER,
         "grantee_user_id": CHILD, "scope": "HEALTH_MEDICATION", "status": "REVOKED", "version": 1,
         "source": "SETTINGS", "revoked_at": STAMP},
    ],
    "device_binding": [
        {"id": DEVICE_DEGRADED, "device_id_hash": "d" * 64, "owner_user_id": ELDER,
         "device_type": "ANDROID_TABLET", "app_version": "demo-mock", "os_version": "demo-mock",
         "kiosk_status": "DISABLED", "wakeword_status": "ERROR", "ble_status": "DISCONNECTED",
         "camera_permission": "DENIED", "phone_permission": "DENIED", "status": "ACTIVE",
         "capabilities": {"provider": "mock", "demo": True}, "last_state_change_at": STAMP},
    ],
    "memory": [
        {"id": MEMORY_OK, "family_id": FAMILY, "subject_user_id": ELDER, "source_user_id": CHILD,
         "type": "PREFERENCE", "title": "演示：喜欢的活动", "content": "演示人物喜欢在公园散步。",
         "required_consent_scope": "FAMILY_MEMORY", "verification_status": "CONFIRMED",
         "verified_by": ELDER, "verified_at": STAMP},
        {"id": MEMORY_PENDING, "family_id": FAMILY, "subject_user_id": ELDER, "source_user_id": CHILD,
         "type": "EVENT", "title": "演示：待确认的活动", "content": "演示人物可能参加过一次合唱活动。",
         "required_consent_scope": "FAMILY_MEMORY", "verification_status": "PENDING"},
        {"id": MEMORY_REVOKED, "family_id": FAMILY, "subject_user_id": ELDER, "source_user_id": CHILD,
         "type": "PLACE", "title": "演示：已撤回的地点", "content": "演示地点已撤回。",
         "required_consent_scope": "FAMILY_MEMORY", "verification_status": "REVOKED", "revoked_at": STAMP},
        {"id": MEMORY_DELETED, "family_id": FAMILY, "subject_user_id": ELDER, "source_user_id": CHILD,
         "type": "EVENT", "title": "演示：已删除记忆", "content": "演示删除占位；不保留原始内容。",
         "required_consent_scope": "FAMILY_MEMORY", "verification_status": "DELETED", "deleted_at": STAMP},
    ],
    "file_asset": [
        {"id": ASSET_DELETE_PENDING, "owner_user_id": ELDER, "family_id": FAMILY,
         "memory_id": MEMORY_DELETED, "object_key": "demo/E0-T08/fictional-cleanup-placeholder",
         "media_type": "OTHER", "mime_type": "application/octet-stream", "size_bytes": 0,
         "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
         "status": "DELETE_REQUESTED", "deleted_at": STAMP},
    ],
    "reminder": [
        {"id": REMINDER, "owner_user_id": ELDER, "created_by_user_id": CHILD, "type": "WATER",
         "title": "演示喝水提醒", "content": "现在可以喝些水。", "schedule_time_local": "09:00:00",
         "timezone": "Asia/Shanghai", "start_date": "2026-09-01", "recurrence_kind": "DAILY"},
    ],
    "reminder_execution": [
        {"id": EXEC_DONE, "reminder_id": REMINDER, "owner_user_id": ELDER,
         "occurrence_key": "demo-water-2026-09-01", "scheduled_at": STAMP,
         "local_date": "2026-09-01", "local_time": "09:00:00", "triggered_at": STAMP,
         "feedback_status": "DONE", "feedback_at": STAMP, "source": "ONLINE", "attempt_count": 1},
        {"id": EXEC_NO_RESPONSE, "reminder_id": REMINDER, "owner_user_id": ELDER,
         "occurrence_key": "demo-water-2026-09-02", "scheduled_at": "2026-09-02T09:00:00+08:00",
         "local_date": "2026-09-02", "local_time": "09:00:00", "triggered_at": "2026-09-02T09:00:00+08:00",
         "feedback_status": "NO_RESPONSE", "source": "OFFLINE", "attempt_count": 1},
    ],
    "interaction_metric": [
        {"id": METRIC_DONE, "owner_user_id": ELDER, "metric_date": "2026-09-01",
         "timezone_snapshot": "Asia/Shanghai", "interaction_count": 0, "conversation_seconds": 0,
         "reminder_done_count": 1, "source_cutoff_at": END},
        {"id": METRIC, "owner_user_id": ELDER, "metric_date": "2026-09-02",
         "timezone_snapshot": "Asia/Shanghai", "interaction_count": 0, "conversation_seconds": 0,
         "reminder_no_response_count": 1, "source_cutoff_at": END},
    ],
    "signal_event": [
        {"id": SIGNAL_MISS, "owner_user_id": ELDER, "family_id": FAMILY, "type": "MISS_FAMILY",
         "severity": "L1", "evidence_summary": "演示：表达想念家人。", "policy_version": "demo-1",
         "consent_check_result": "ALLOWED", "status": "NOTIFIED", "detected_at": STAMP, "notified_at": STAMP},
        {"id": SIGNAL_SCAM, "owner_user_id": ELDER, "family_id": FAMILY, "type": "SCAM_RISK",
         "severity": "L2", "evidence_summary": "演示：出现可疑转账请求，已阻止敏感操作。",
         "rule_id": "demo-scam-warning", "rule_version": "demo-1", "policy_version": "demo-1",
         "consent_check_result": "WITHHELD", "status": "WITHHELD", "detected_at": STAMP},
        {"id": SIGNAL_PHYSICAL, "owner_user_id": ELDER, "family_id": FAMILY, "type": "PHYSICAL_DISCOMFORT",
         "severity": "L1", "evidence_summary": "演示：表达身体不适；不作诊断。", "policy_version": "demo-1",
         "consent_check_result": "WITHHELD", "status": "WITHHELD", "detected_at": STAMP},
        {"id": SIGNAL_MISS_FAILED, "owner_user_id": ELDER, "family_id": FAMILY, "type": "MISS_FAMILY",
         "severity": "L1", "evidence_summary": "演示：另一条想念家人的动态，Mock 推送失败。",
         "policy_version": "demo-1", "consent_check_result": "ALLOWED",
         "status": "NOTIFICATION_FAILED", "detected_at": STAMP},
    ],
    "notification": [
        {"id": NOTIFICATION_READ, "signal_event_id": SIGNAL_MISS, "recipient_user_id": CHILD,
         "channel": "IN_APP", "status": "READ", "summary": "演示：有一条家人关注动态。",
         "policy_version": "demo-1", "provider": "mock", "action": "NONE", "sent_at": STAMP,
         "delivered_at": STAMP, "read_at": STAMP},
        {"id": NOTIFICATION_FAILED, "signal_event_id": SIGNAL_MISS_FAILED, "recipient_user_id": CHILD,
         "channel": "PUSH", "status": "FAILED", "summary": "演示：有一条待查看的关注动态。",
         "policy_version": "demo-1", "provider": "mock", "action": "NONE", "error_code": "MOCK_FAILURE"},
    ],
    "notification_attempt": [
        {"id": ATTEMPT_FAILED, "notification_id": NOTIFICATION_FAILED, "attempt_no": 1,
         "provider": "mock", "status": "FAILED", "started_at": STAMP, "finished_at": STAMP,
         "error_code": "MOCK_FAILURE", "error_detail_redacted": "Deterministic demo failure"},
    ],
    "weekly_report": [
        {"id": REPORT_READY, "owner_user_id": ELDER, "family_id": FAMILY,
         "period_start": "2026-09-01", "period_end": "2026-09-07", "version": 1,
         "status": "READY", "generated_at": END,
         "metrics_snapshot": {"interaction_count": 0, "reminder_done_count": 1, "reminder_no_response_count": 1},
         "narrative": "演示交流观察线索：本周没有完整交流记录；一次喝水提醒收到完成反馈，一次未收到反馈。未收到反馈不表示没有喝水。",
         "missing_data": ["交流记录不足，无法判断互动趋势。"], "source_cutoff_at": END},
        {"id": REPORT_FAILED, "owner_user_id": ELDER, "family_id": FAMILY,
         "period_start": "2026-09-08", "period_end": "2026-09-14", "version": 1,
         "status": "FAILED", "metrics_snapshot": {}, "missing_data": ["演示：报告生成失败。"],
         "source_cutoff_at": END},
    ],
}

JSON_COLUMNS = {"metrics_snapshot", "missing_data", "accessibility_settings", "permission_codes", "attributes", "capabilities"}

# Local fixture descriptions, not API DTOs or additional database columns.
# No media object is created and no hardware/provider/cleanup operation is performed.
SCENARIOS = {
    "device_degraded": {"provider": "mock", "demo": True, "device_id": DEVICE_DEGRADED},
    "provider_failure": {"provider": "mock", "demo": True, "attempt_id": ATTEMPT_FAILED},
    "deletion_partial_failure": {"provider": "mock", "demo": True,
                                 "memory_id": MEMORY_DELETED, "file_asset_id": ASSET_DELETE_PENDING,
                                 "error_code": "MOCK_FAILURE", "label": "演示：已不可见，模拟物理清理失败；尚未完成"},
}


def validate_fixture() -> None:
    """Fail closed if a future edit weakens the demo-only fixture boundary."""
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise RuntimeError(message)

    all_ids: set[str] = set()
    for table, rows in ROWS.items():
        require(bool(rows), f"empty fixture table: {table}")
        for row in rows:
            identifier = str(row["id"])
            require(UUID(identifier).version == 7, f"fixture ID must be UUIDv7: {table}")
            require(identifier not in all_ids, "duplicate fixture ID")
            all_ids.add(identifier)
    require(ROWS["family"][0]["name"] == FAMILY_NAME, "fictional family label required")
    require({row["role"] for row in ROWS["family_member"]} == {"ELDER", "CHILD"}, "demo roles missing")
    require({row["verification_status"] for row in ROWS["memory"]} ==
            {"CONFIRMED", "PENDING", "REVOKED", "DELETED"}, "demo memory states missing")
    for table, field, states in (
        ("reminder_execution", "feedback_status", {"DONE", "NO_RESPONSE"}),
        ("notification", "status", {"READ", "FAILED"}),
        ("weekly_report", "status", {"READY", "FAILED"}),
    ):
        require({row[field] for row in ROWS[table]} == states, f"demo states missing: {table}")
    require(all(row["provider"] == "mock" for table in ("notification", "notification_attempt")
                for row in ROWS[table]), "only Mock providers allowed")
    for rows in ROWS.values():
        for row in rows:
            require(not any(("phone" in key and key != "phone_permission") or "audio" in key or "photo" in key
                            for key in row), "contact or media fields forbidden")
            for key, value in row.items():
                if key == "family_id":
                    require(value == FAMILY, "cross-family fixture reference")
                if key.endswith("_user_id") or key in ("user_id", "verified_by"):
                    require(value in (ELDER, CHILD), "external user fixture reference")
                if key in ("memory_id", "reminder_id", "signal_event_id", "notification_id"):
                    target = key.removesuffix("_id")
                    require(value in {item["id"] for item in ROWS[target]}, "external resource fixture reference")
