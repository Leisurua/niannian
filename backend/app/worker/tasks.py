import asyncio

from app.modules.memory import rag, files
from app.modules.conversation import summary
from app.modules.signal import service as signals
from app.modules.notification import service as notifications
from app.platform import tasks
from app.platform.identifiers import utcnow


async def authorize_index_then_lock_lease(db, task, token):
    current = await rag.prepare_index(db, task.resource_id, task.resource_version)
    lease = await tasks.leased(db, task.id, token)
    return current, lease


async def run_one(factory, storage=None, *, push=None, kinds=None):
    async with factory() as db:
        task = await tasks.claim(db, kinds=kinds, exclude_kinds=('AVATAR_GENERATE', 'VOICE_GENERATE', 'VOICE_CLEANUP'))
        await db.commit()
        if task is None:
            return False
        task_id, token = task.id, task.lease_token
    try:
        async with asyncio.timeout(20):
            if task.kind == 'NOTIFICATION_DISPATCH':
                from app.modules.notification.service import dispatch
                await dispatch(factory, task_id, token, task.resource_id, push)
            elif task.kind in ('SIGNAL_CLEANUP', 'NOTIFICATION_CLEANUP', 'MEMORY_CLEANUP', 'CONVERSATION_SUMMARY_CLEANUP'):
                async with factory() as db:
                    if await tasks.leased(db, task_id, token):
                        if task.kind == 'CONVERSATION_SUMMARY_CLEANUP':
                            await summary.cleanup(db, task.resource_id, task.resource_version)
                        else:
                            cleanup = {
                                'SIGNAL_CLEANUP': signals.cleanup,
                                'NOTIFICATION_CLEANUP': notifications.cleanup,
                                'MEMORY_CLEANUP': rag.cleanup,
                            }[task.kind]
                            await cleanup(db, task.resource_id)
                        await tasks.finish(db, task_id, token)
                        await db.commit()
            elif task.kind == 'MEMORY_INDEX':
                async with factory() as db:
                    prepared = await rag.prepare_index(db, task.resource_id, task.resource_version)
                    await db.commit()
                result = await rag.embed(prepared.texts, str(task_id)) if prepared else None
                async with factory() as db:
                    current, lease = await authorize_index_then_lock_lease(db, task, token)
                    if lease:
                        if prepared and prepared == current:
                            await rag.apply_index(db, task.resource_id, task.resource_version, prepared, result)
                        await tasks.finish(db, task_id, token)
                        await db.commit()
            elif task.kind == 'CONVERSATION_SUMMARY':
                async with factory() as db:
                    prepared = await summary.prepare(db, task.resource_id, task.resource_version)
                    await db.commit()
                async with factory() as db:
                    current = await summary.prepare(db, task.resource_id, task.resource_version)
                    if await tasks.leased(db, task_id, token):
                        if prepared and current == prepared:
                            await summary.complete(db, task.resource_id, task.resource_version, prepared)
                        await tasks.finish(db, task_id, token)
                        await db.commit()
            else:
                if storage is None:
                    raise RuntimeError('Storage unavailable')
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
