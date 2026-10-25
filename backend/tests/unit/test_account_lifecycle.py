import asyncio
from datetime import datetime, timezone

import pytest

from app.modules.account.backups import prune
from app.platform.storage import S3Storage


def test_backup_retention_uses_snapshot_time_and_only_managed_files(tmp_path):
    old = tmp_path / 'niannian-backup-20260101T000000Z.dump'
    current = tmp_path / 'niannian-backup-20261024T000000Z.tar.gz'
    unrelated = tmp_path / 'unrelated.dump'
    for file in (old, current, unrelated):
        file.write_bytes(b'fictional')
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    assert prune(tmp_path, 30, now=now) == [old.name]
    assert old.exists()
    assert prune(tmp_path, 30, now=now, apply=True) == [old.name]
    assert not old.exists() and current.exists() and unrelated.exists()
    assert prune(tmp_path, 30, now=now, apply=True) == []
    with pytest.raises(ValueError):
        prune(tmp_path, 0, apply=True)


def test_versioned_storage_deletes_every_version_and_marker_not_prefix_neighbors():
    storage = object.__new__(S3Storage)
    calls = []
    pages = iter([
        {'Versions': [{'Key': 'own', 'VersionId': 'v1'}, {'Key': 'own.safe', 'VersionId': 'other'}],
            'DeleteMarkers': [{'Key': 'own', 'VersionId': 'marker'}], 'IsTruncated': True},
        {'Versions': [{'Key': 'own', 'VersionId': 'v2'}]},
        {'Versions': [{'Key': 'own.safe', 'VersionId': 'other'}]},
    ])
    async def call(operation, **kwargs):
        calls.append((operation, kwargs))
        if operation == 'list_object_versions':
            return next(pages)
        return {}
    storage._call = call
    asyncio.run(storage.delete_all_versions('own'))
    removed = [args for operation, args in calls if operation == 'delete_object']
    assert removed == [{'Key': 'own'}, {'Key': 'own', 'VersionId': 'v1'},
        {'Key': 'own', 'VersionId': 'marker'}, {'Key': 'own', 'VersionId': 'v2'}]
