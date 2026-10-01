from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from app.modules.audit.service import record
from app.platform.db import session_factory
from app.platform.errors import AppError


async def transaction(request: Request):
    factory = getattr(request.app.state, "session_factory", session_factory)
    async with factory() as db:
        try:
            yield db
            await db.commit()
        except AppError as error:
            await db.rollback()
            actor = getattr(request.state, "actor_id", None)
            if actor:
                try:
                    await record(db, actor, "REQUEST_DENIED", "AUTHORIZATION",
                                 request_id=request.state.request_id, result="DENIED",
                                 metadata={"error_code": error.code})
                    await db.commit()
                except SQLAlchemyError:
                    await db.rollback()
                    raise AppError("PROVIDER_TEMPORARILY_UNAVAILABLE", "服务暂不可用，请稍后重试。", 503) from None
            raise
        except SQLAlchemyError:
            await db.rollback()
            raise AppError("PROVIDER_TEMPORARILY_UNAVAILABLE", "服务暂不可用，请稍后重试。", 503) from None
        except Exception:
            await db.rollback()
            raise
