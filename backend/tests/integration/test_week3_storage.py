"""Real MinIO gate, separate from the labelled MockObjectStorage tests."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from botocore.exceptions import ClientError
from sqlalchemy import text

from app.main import app
from app.worker.tasks import run_one
from app.platform.config import Settings
from app.platform.storage import S3Storage
from backend.tests.integration.test_week3_postgres import system, household, grant, memory, photo, post

CONFIG = os.environ.get('WEEK3_STORAGE_CONFIG')
pytestmark = pytest.mark.skipif(not CONFIG or not os.environ.get('WEEK3_TEST_DATABASE_URL'),
    reason='Real isolated MinIO and Week 3 PostgreSQL are required')


def test_real_minio_private_upload_confirm_proxy_revoke_and_delete(system):
    client, engine, factory, _ = system
    config = json.loads(Path(CONFIG).read_text(encoding='utf-8-sig'))
    endpoint = urlsplit(config['endpoint'])
    assert endpoint.scheme == 'http' and endpoint.hostname == '127.0.0.1' and endpoint.port == 59003
    assert config['bucket'] == 'niannian-week3-test'
    settings = Settings(s3_endpoint=config['endpoint'], s3_bucket=config['bucket'],
                        s3_access_key=config['access_key'], s3_secret_key=config['secret_key'])
    storage = S3Storage(settings)
    try:
        storage.client.create_bucket(Bucket=config['bucket'])
    except ClientError as error:
        assert error.response['Error']['Code'] in ('BucketAlreadyOwnedByYou', 'BucketAlreadyExists')
    app.state.object_storage = storage
    home = household(client); consent_id = grant(client, home)
    item = memory(client, home)
    data = photo(); checksum = hashlib.sha256(data).hexdigest()
    upload = post(client, '/v1/files/upload-requests', home[2], dict(memory_id=item['id'], media_type='PHOTO',
        mime_type='image/png', size_bytes=len(data), checksum=checksum))
    assert upload.status_code == 201
    signed = upload.json()
    assert httpx.put(signed['upload_url'], content=data, headers=signed['required_headers'], timeout=15).status_code == 200
    raw_url = urlsplit(signed['upload_url'])
    anonymous = httpx.get(raw_url.scheme + '://' + raw_url.netloc + raw_url.path, timeout=15)
    assert anonymous.status_code == 403
    file_id = signed['file']['id']
    confirmed = post(client, '/v1/files/'+file_id+'/confirm', home[2], {'checksum':checksum})
    assert confirmed.status_code == 202 and confirmed.json()['status'] == 'AVAILABLE'
    url = urlsplit(client.get('/v1/files/'+file_id+'/download-url', headers=home[2]).json()['download_url'])
    path = url.path + '?' + url.query
    download = client.get(path, headers=home[2])
    assert download.status_code == 200 and b'fictional location metadata' not in download.content
    assert post(client, '/v1/consents/'+consent_id+'/revoke', home[4]).status_code == 201
    assert client.get(path, headers=home[2]).status_code == 404
    assert client.delete('/v1/memories/'+item['id'], headers={**home[4], 'Idempotency-Key':'real-photo-delete'}).status_code == 202
    with engine.begin() as connection:
        connection.execute(text("UPDATE file_asset SET created_at=now()-interval '1 hour' WHERE id=:id"), {'id': file_id})
    async def clean():
        for _ in range(60):
            if not await run_one(factory, storage):
                break
    asyncio.run(clean())
    keys = storage.client.list_objects_v2(Bucket=config['bucket'], Prefix='private/'+home[0]+'/')
    assert keys.get('KeyCount', 0) == 0
