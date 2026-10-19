"""Private S3 adapter with explicit credentials, bounded reads and safe errors."""
import asyncio

import boto3
from botocore.config import Config

from app.platform.errors import AppError


class S3Storage:
    def __init__(self, settings):
        if not settings.s3_access_key or not settings.s3_secret_key:
            raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', '照片存储尚未配置。', 503)
        self.bucket = settings.s3_bucket
        self.client = boto3.client('s3', endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key,
            region_name='us-east-1', config=Config(signature_version='s3v4', connect_timeout=3,
                read_timeout=10, retries={'max_attempts': 1}, s3={'addressing_style': 'path'}))
        public = getattr(settings, 's3_public_endpoint', None)
        self.upload_client = boto3.client('s3', endpoint_url=public,
            aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key,
            region_name='us-east-1', config=Config(signature_version='s3v4',
                s3={'addressing_style': 'path'})) if public and public != settings.s3_endpoint else self.client

    async def _call(self, operation, **kwargs):
        try:
            return await asyncio.to_thread(getattr(self.client, operation), Bucket=self.bucket, **kwargs)
        except Exception:
            raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', '照片存储暂不可用，请稍后重试。', 503) from None

    async def upload_url(self, key, mime, size, seconds):
        try:
            return await asyncio.to_thread(self.upload_client.generate_presigned_url, 'put_object',
                Params={'Bucket': self.bucket, 'Key': key, 'ContentType': mime, 'ContentLength': size}, ExpiresIn=seconds)
        except Exception:
            raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', '暂时无法生成上传地址。', 503) from None

    async def read(self, key, maximum):
        response = await self._call('get_object', Key=key)
        body = response['Body']
        try:
            if response['ContentLength'] > maximum:
                raise AppError('FILE_TOO_LARGE', '照片超出大小限制。', 413)
            value = await asyncio.to_thread(body.read, maximum + 1)
            if len(value) > maximum:
                raise AppError('FILE_TOO_LARGE', '照片超出大小限制。', 413)
            return value
        except AppError:
            raise
        except Exception:
            raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', '照片读取失败，请重试。', 503) from None
        finally:
            body.close()

    async def write(self, key, data, mime):
        await self._call('put_object', Key=key, Body=data, ContentType=mime)

    async def delete(self, key):
        await self._call('delete_object', Key=key)
