"""Validation and schema parity with the approved Week 3 contracts."""

from pathlib import Path
from typing import get_args
import re

import yaml

from app.modules.conversation.protocol import BackendState, ClientEnvelope, ClientType, ServerType
from app.modules.memory.validation import ConsentScope, MemoryDraft, MemorySource, MemoryStatus, MemoryType, Visibility
from app.modules.reminder.schedule import RecurrenceKind, ScheduleRule
from app.platform.models import DOMAIN_MODELS

ROOT = Path(__file__).resolve().parents[3]


def test_internal_values_match_frozen_openapi():
    schemas = yaml.safe_load((ROOT / 'docs/openapi.yaml').read_text(encoding='utf-8'))['components']['schemas']
    pairs = [
        (MemoryType, schemas['MemoryType']['enum']),
        (MemoryStatus, schemas['MemoryStatus']['enum']),
        (ConsentScope, schemas['ConsentScope']['enum']),
        (MemorySource, schemas['MemoryCreate']['properties']['source']['enum']),
        (Visibility, schemas['MemoryCreate']['properties']['visibility']['enum']),
        (RecurrenceKind, schemas['ReminderCreate']['properties']['recurrence_kind']['enum']),
        (ClientType, schemas['WebSocketClientMessage']['allOf'][1]['properties']['type']['enum']),
        (ServerType, schemas['WebSocketServerMessage']['allOf'][1]['properties']['type']['enum']),
        (BackendState, schemas['ConversationResponse']['properties']['backend_state']['enum']),
    ]
    for internal, frozen in pairs:
        assert list(get_args(internal)) == frozen
    assert set(ClientEnvelope.model_fields) == set(schemas['WebSocketEnvelope']['required'])
    assert set(MemoryDraft.model_fields) == set(schemas['MemoryCreate']['properties'])
    assert set(ScheduleRule.model_fields) <= set(schemas['ReminderCreate']['properties'])


def test_all_thirteen_models_match_the_approved_dictionary():
    dictionary = (ROOT / 'docs/data-dictionary.md').read_text(encoding='utf-8')
    assert len(DOMAIN_MODELS) == 13
    for model in DOMAIN_MODELS:
        section = re.search(r'^## \d+\. ' + model.__tablename__ + r'\n(.*?)(?=^## |\Z)', dictionary, re.M | re.S)[1]
        columns = set(re.findall(r'^\| ([a-z][a-z0-9_]*) \|', section, re.M))
        assert set(model.__table__.columns.keys()) == columns
