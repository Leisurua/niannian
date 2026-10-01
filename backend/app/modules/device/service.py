from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.device.models import DeviceBinding
from app.platform.errors import AppError


async def require_active_binding(db: AsyncSession, binding_id: UUID, owner_id: UUID) -> None:
    binding = await db.get(DeviceBinding, binding_id)
    if not binding or binding.owner_user_id != owner_id or binding.status != "ACTIVE":
        raise AppError("AUTH_SESSION_REVOKED", "设备绑定已失效，请重新登录。", 401)
