import hmac
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import tuple_

from app.modules.auth.tokens import decode, encode
from app.platform.errors import AppError


async def page_rows(db, query, model, signer, scope: str, limit: int, cursor: str | None):
    if cursor:
        try:
            payload, signature = cursor.split('.')
            if not hmac.compare_digest(signature, signer.opaque("cursor:" + scope, payload)):
                raise ValueError()
            marker = json.loads(decode(payload))
            stamp = datetime.fromisoformat(marker['t'])
            if stamp.tzinfo is None:
                raise ValueError()
            query = query.where(tuple_(model.created_at, model.id) < tuple_(stamp, UUID(marker['id'])))
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
            raise AppError("INVALID_CURSOR", "分页信息已失效，请重新打开列表。", 400) from None
    rows = (await db.scalars(query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1))).all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if more:
        last = rows[-1]
        payload = encode(json.dumps({'t': last.created_at.isoformat(), 'id': str(last.id)}, separators=(',', ':')).encode())
        next_cursor = payload + '.' + signer.opaque("cursor:" + scope, payload)
    return rows, {"limit": limit, "next_cursor": next_cursor, "has_more": more}
