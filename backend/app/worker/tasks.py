"""Run provider I/O between transactions; fence every database completion."""
import asyncio

from app.modules.memory import rag, files
from app.platform import tasks
from app.platform.identifiers import utcnow


async def run_one(factory, storage=None):
    async with factory() as db:
        task = await tasks.claim(db)
        await db.commit()
        if task is None:
            return False
        task_id, token = task.id, task.lease_token
    try:
        async with asyncio.timeout(20):
            if task.kind == 'MEMORY_INDEX':
                async with factory() as db:
                    prepared = await rag.prepare_index(db, task.resource_id, task.resource_version)
                    await db.commit()
                result = await rag.embed(prepared[2], str(task_id)) if prepared else None
                async with factory() as db:
                    # Family first, then task fence, matching API lock order.
                    current = await rag.prepare_index(db, task.resource_id, task.resource_version)
                    if await tasks.leased(db, task_id, token):
                        if prepared and prepared == current:
                            await rag.apply_index(db, task.resource_id, task.resource_version, prepared, result)
                        await tasks.finish(db, task_id, token)
                        await db.commit()
            elif task.kind == 'MEMORY_CLEANUP':
                async with factory() as db:
                    if await tasks.leased(db, task_id, token):
                        await rag.cleanup(db, task.resource_id)
                        await tasks.finish(db, task_id, token)
                        await db.commit()
            else:
                if storage is None:
                    raise RuntimeError('Storage unavailable')
                # Provider I/O has neither a database session nor a business row lock.
                async with factory() as db:
                    prepared = await files.prepare_cleanup(db, task.resource_id)
                if prepared:
                    for key in prepared[0]:
                        await storage.delete(key)
                async with factory() as db:
                    if await tasks.leased(db, task_id, token):
                        # A live signed PUT can recreate raw bytes after the first purge.
                        # Keep the resource invisible and schedule a final purge after expiry.
                        if prepared and prepared[1] and prepared[1] > utcnow():
                            await tasks.defer_cleanup(db, task_id, token, prepared[1])
                        else:
                            if prepared:
                                await files.complete_cleanup(db, task.resource_id, prepared[2])
                            await tasks.finish(db, task_id, token)
                        await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception:
        async with factory() as db:
            await tasks.finish(db, task_id, token, error=True)
            await db.commit()
    return True
