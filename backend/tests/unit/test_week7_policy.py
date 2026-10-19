from datetime import datetime, time, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.notification.preferences import PreferenceInput, ready_at
from app.modules.signal.service import dedupe_key


@pytest.mark.parametrize(('zone','start','end','now','expected'), [
    ('Asia/Shanghai',time(22),time(8),'2026-10-19T15:00:00+00:00','2026-10-20T00:00:00+00:00'),
    ('Asia/Shanghai',time(22),time(8),'2026-10-19T00:00:00+00:00','2026-10-19T00:00:00+00:00'),
    ('America/New_York',time(1),time(3),'2026-03-08T06:30:00+00:00','2026-03-08T07:00:00+00:00'),
    ('America/New_York',time(1),time(2),'2026-11-01T05:30:00+00:00','2026-11-01T07:00:00+00:00'),
    ('Asia/Shanghai',None,None,'2026-10-19T15:00:00+00:00','2026-10-19T15:00:00+00:00'),
    ('Asia/Shanghai',time(8),time(8),'2026-10-19T15:00:00+00:00','2026-10-19T15:00:00+00:00'),
])
def test_quiet_hours_follow_utc_across_midnight_and_dst(zone,start,end,now,expected):
    p=SimpleNamespace(timezone=zone,quiet_hours_start=start,quiet_hours_end=end)
    assert ready_at(p,datetime.fromisoformat(now))==datetime.fromisoformat(expected)


@pytest.mark.parametrize('body', [
    {'channels':['SMS'],'timezone':'Asia/Shanghai'}, {'channels':['PUSH','PUSH'],'timezone':'UTC'},
    {'channels':['IN_APP'],'timezone':'Mars/Unknown'},
    {'channels':['IN_APP'],'timezone':'UTC','quiet_hours_start':'22:00'},
    {'channels':['IN_APP'],'timezone':'UTC','quiet_hours_start':'22:00:01','quiet_hours_end':'08:00'},
    {'channels':[],'timezone':'UTC','recipient_user_id':str(uuid4())},
])
def test_preference_invalid_input_does_not_become_permission(body):
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(body)


def test_dedupe_isolated_by_family_owner_type_category_severity_and_window():
    fid,owner=uuid4(),uuid4()
    now=datetime(2026,10,19,3,1,tzinfo=timezone.utc)
    base=dedupe_key(fid,owner,'SCAM_RISK','TRANSFER_AND_SECRECY','L2',now)
    assert base==dedupe_key(fid,owner,'SCAM_RISK','TRANSFER_AND_SECRECY','L2',now.replace(minute=29))
    assert base!=dedupe_key(fid,owner,'SCAM_RISK','TRANSFER_AND_SECRECY','L2',now.replace(minute=30))
    for args in ((uuid4(),owner,'SCAM_RISK','TRANSFER_AND_SECRECY','L2'),
        (fid,uuid4(),'SCAM_RISK','TRANSFER_AND_SECRECY','L2'),
        (fid,owner,'MISS_FAMILY','TRANSFER_AND_SECRECY','L2'),
        (fid,owner,'SCAM_RISK','URGENT_TRANSFER_REQUEST','L2'),
        (fid,owner,'SCAM_RISK','TRANSFER_AND_SECRECY','L3')):
        assert dedupe_key(*args,now)!=base
