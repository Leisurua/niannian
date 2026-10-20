from pathlib import Path
import yaml
from app.main import app
from app.modules.notification.preferences import PreferenceInput, view
from types import SimpleNamespace
from uuid import uuid4


def test_week7_preference_and_existing_surface_contracts():
    spec=yaml.safe_load((Path(__file__).resolve().parents[3]/'docs/openapi.yaml').read_text(encoding='utf-8'))
    schemas=spec['components']['schemas']
    assert set(PreferenceInput.model_fields)==set(schemas['NotificationPreferenceInput']['properties'])
    result=view(SimpleNamespace(version=0,channels=['IN_APP'],timezone='Asia/Shanghai',quiet_hours_start=None,
        quiet_hours_end=None),uuid4(),uuid4(),uuid4())
    assert set(result)==set(schemas['NotificationPreferenceResponse']['properties'])
    ids={r.operation_id for r in app.routes if getattr(r,'operation_id',None)}
    assert {'listSignalEvents','getSignalEvent','listNotifications','getNotification','markNotificationRead',
        'getNotificationPreference','putNotificationPreference'} <= ids
    assert not {'actOnNotification','contactForSignalEvent','markSignalFalsePositive'} & ids
    paths={(r.path,method) for r in app.routes for method in getattr(r,'methods',[])}
    assert ('/v1/signal-events','POST') not in paths
    assert ('/v1/notification-attempts','GET') not in paths
