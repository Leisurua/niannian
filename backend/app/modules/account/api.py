from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import Field, SecretStr

from app.modules.account import service
from app.modules.account.export import build_export
from app.modules.auth.api import limit_login
from app.modules.auth.schemas import Input
from app.modules.memory.files import store
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Account'])


class DeleteAccount(Input):
    confirmation: Literal['DELETE_MY_ACCOUNT']
    # Generated and saved by the client BEFORE deletion, so a lost HTTP response
    # cannot strand the user after every session has been revoked.
    receipt_token: SecretStr = Field(min_length=43, max_length=128)


@router.get('/me/export', operation_id='exportAccount')
async def export(request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    settings = get_settings()
    # Lazy storage construction permits accounts with no photos to export even
    # if object storage is temporarily unavailable/unconfigured.
    class Storage:
        async def read(self, key, maximum):
            return await store(request, settings).read(key, maximum)
    payload = await build_export(db, actor, Storage(), settings, request.state.request_id)
    return Response(payload, media_type='application/zip', headers={
        'Cache-Control': 'no-store', 'Content-Disposition': 'attachment; filename="niannian-account.zip"'})


@router.post('/me/deletion', status_code=202, operation_id='deleteAccount')
async def delete_account(body: DeleteAccount, request: Request, response: Response,
                         actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.request_deletion(db, actor, body.receipt_token.get_secret_value(), get_settings())


@router.get('/account-deletions/{deletion_id}', operation_id='getAccountDeletion')
async def deletion_status(deletion_id: UUID, request: Request, response: Response,
                          x_deletion_token: str = Header(min_length=43, max_length=128), db=Depends(transaction)):
    limit_login(request)
    response.headers['Cache-Control'] = 'no-store'
    return await service.deletion_view(db, await service.receipt(db, deletion_id, x_deletion_token))


class ReceiptLookup(Input):
    receipt_token: SecretStr = Field(min_length=43, max_length=128)


@router.post('/account-deletions/lookup', operation_id='lookupAccountDeletion')
async def lookup(body: ReceiptLookup, request: Request, response: Response, db=Depends(transaction)):
    from sqlalchemy import select
    from app.modules.account.models import AccountDeletion
    from app.modules.auth.tokens import digest
    from app.platform.errors import AppError
    limit_login(request)
    row = await db.scalar(select(AccountDeletion).where(AccountDeletion.receipt_hash == digest(body.receipt_token.get_secret_value())))
    if row is None:
        raise AppError('ACCOUNT_DELETION_NOT_FOUND', '删除回执不存在或凭证无效。', 404)
    response.headers['Cache-Control'] = 'no-store'
    return await service.deletion_view(db, row)
