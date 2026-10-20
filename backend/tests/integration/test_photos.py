import asyncio
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from app.modules.memory.files import cleanup
from app.platform.identifiers import utcnow
from PIL import Image
from sqlalchemy import text

from backend.tests.support import (
    URL,
    grant,
    household,
    memory,
    photo,
    post,
    upload,
)

pytestmark = pytest.mark.skipif(not URL, reason='Set TEST_DATABASE_URL to run PostgreSQL integration tests')

def test_file_decode_metadata_strip_signed_proxy_revoke_and_cleanup(system):
    client, engine, factory, storage = system
    home = household(client); cid = grant(client, home)
    item = memory(client, home)
    fid, result = upload(client, home, storage, item['id'], photo())
    assert result['status'] == 'AVAILABLE'
    signed = client.get('/v1/files/' + fid + '/download-url', headers=home[2]).json()['download_url']
    url = urlsplit(signed); path = url.path + '?' + url.query
    fetched = client.get(path, headers=home[2])
    assert fetched.status_code == 200
    assert fetched.headers['cache-control'] == 'no-store'
    with Image.open(BytesIO(fetched.content)) as image:
        assert not image.info and image.size == (4, 4)
    # Reusing a still-valid upload URL cannot overwrite the clean object.
    storage.objects[storage.keys[-1]] = b'<script>fictional hostile replacement</script>'
    assert client.get(path, headers=home[2]).content == fetched.content
    assert client.get(path).status_code == 401
    assert client.get(path, headers=home[4]).status_code == 404
    assert post(client, '/v1/consents/' + cid + '/revoke', home[4]).status_code == 201
    assert client.get(path, headers=home[2]).status_code == 404
    deletion = client.delete('/v1/memories/' + item['id'], headers={**home[4], 'Idempotency-Key': 'erase-memory'})
    assert deletion.status_code == 202
    async def clean():
        async with factory() as db:
            await cleanup(db, storage)
            await db.commit()
    storage.fail_delete = True
    asyncio.run(clean())
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM file_asset WHERE id=:id'), {'id': UUID(fid)}).scalar() == 'DELETE_REQUESTED'
    storage.fail_delete = False
    asyncio.run(clean())
    assert storage.objects == {}
    assert client.get(path, headers=home[2]).status_code == 404


def test_file_quarantine_wrong_checksum_and_no_unscoped_upload(system):
    client, _, _, storage = system
    home = household(client); grant(client, home)
    item = memory(client, home)
    data = b'\x89PNG\r\n\x1a\nnot a decoded image'
    fid, result = upload(client, home, storage, item['id'], data)
    assert result['status'] == 'QUARANTINED'
    assert client.get('/v1/files/' + fid + '/download-url', headers=home[2]).status_code == 404
    assert post(client, '/v1/files/upload-requests', home[2], dict(media_type='PHOTO', mime_type='image/png', size_bytes=5, checksum='a'*64)).status_code == 422


def test_late_signed_put_raw_object_is_reclaimed_after_upload_window(system):
    client, _, factory, storage = system
    home = household(client); grant(client, home)
    item = memory(client, home)
    upload(client, home, storage, item['id'], photo())
    key = storage.keys[-1]
    storage.objects[key] = b'fictional replay'
    async def run():
        async with factory() as db:
            await cleanup(db, storage, utcnow()+timedelta(minutes=7))
            await db.commit()
    asyncio.run(run())
    assert key not in storage.objects and key+'.safe' in storage.objects
