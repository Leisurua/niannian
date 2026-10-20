"""Verify external upload link host without network access."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

from app.platform.storage import S3Storage


def settings(public=None):
    return SimpleNamespace(s3_access_key="fictional", s3_secret_key="fictional",
        s3_endpoint="http://minio:9000", s3_public_endpoint=public, s3_bucket="nianian-private")

def test_s3_upload_url_uses_client_reachable_endpoint():
    endpoints = []
    def make_client(_service, **kwargs):
        endpoint = kwargs["endpoint_url"]
        endpoints.append(endpoint)
        return SimpleNamespace(generate_presigned_url=lambda *_args, **_kwargs: endpoint + "/signed")
    with patch("app.platform.storage.boto3.client", side_effect=make_client):
        storage = S3Storage(settings("http://192.0.2.10:9000"))
        signed = asyncio.run(storage.upload_url("demo/fixture", "image/png", 10, 60))
    assert endpoints == ["http://minio:9000", "http://192.0.2.10:9000"]
    assert urlparse(signed).hostname == "192.0.2.10"
    assert storage.upload_client is not storage.client

def test_s3_local_setup_still_uses_existing_client():
    with patch("app.platform.storage.boto3.client") as factory:
        storage = S3Storage(settings())
    assert factory.call_count == 1
    assert storage.upload_client is storage.client
