import logging
import argparse
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.platform.config import get_settings
from app.platform.logging import configure_logging, log_event
from app.platform.runtime import configure_event_loop

_memory_scan_after = None

async def run_cycle():
    global _memory_scan_after
    from app.platform.db import session_factory
    from app.modules.reminder.service import tick
    from app.modules.memory.files import schedule_cleanup
    from app.platform.storage import S3Storage
    from app.modules.memory.rag import maintenance
    from app.worker.tasks import run_one
    from app.modules.conversation import summary, proactive
    from app.modules.signal import service as signals
    from app.modules.notification import service as notifications
    from app.modules.report import metrics
    from app.modules.account import service as accounts
    from app.modules.avatar import service as avatars
    settings = get_settings()
    logger = logging.getLogger('nianian.worker')
    try:
        if settings.backup_directory:
            from app.modules.account.backups import prune
            try:
                await asyncio.to_thread(prune, settings.backup_directory, settings.backup_retention_days, apply=True)
            except Exception:
                log_event(logger, logging.ERROR, 'BACKUP_RETENTION_FAILED', error_code='BACKUP_DIRECTORY_UNAVAILABLE')
        storage = S3Storage(settings) if settings.s3_access_key and settings.s3_secret_key else None
        for _ in range(5):
            if not await accounts.process_one(session_factory, storage, settings):
                break
        async with session_factory() as db:
            await accounts.maintenance(db, settings)
            await avatars.maintenance(db)
            await tick(db, settings)
            next_memory_scan = await maintenance(db, _memory_scan_after)
            await schedule_cleanup(db)
            await summary.maintenance(db)
            await proactive.tick(db, settings)
            await signals.maintenance(db)
            await notifications.maintenance(db)
            await metrics.maintenance(db)
            await db.commit()
            _memory_scan_after = next_memory_scan
        for _ in range(20):
            if not await run_one(session_factory, storage):
                break
    except Exception:
        log_event(logger, logging.ERROR, 'WORKER_CYCLE_FAILED', error_code='DEPENDENCY_UNAVAILABLE')
        raise


async def dispatch_notifications(factory=None):
    from app.platform.db import session_factory
    from app.worker.tasks import run_one
    for _ in range(20):
        if not await run_one(factory or session_factory, kinds=('NOTIFICATION_DISPATCH',)):
            break


async def notification_loop():
    delay = 1
    while True:
        await asyncio.sleep(delay)
        try:
            await dispatch_notifications()
            delay = 1
        except Exception:
            log_event(logging.getLogger('nianian.worker'), logging.ERROR,
                'NOTIFICATION_CYCLE_FAILED', error_code='DEPENDENCY_UNAVAILABLE')
            delay = 15


async def serve():
    scheduler = AsyncIOScheduler()
    async def safe_cycle():
        try:
            await run_cycle()
        except Exception:
            pass  # stable redacted error already emitted; next tick retries
    scheduler.add_job(safe_cycle, 'interval', seconds=15, max_instances=1, coalesce=True)
    scheduler.start()
    notifications = asyncio.create_task(notification_loop())
    try:
        await safe_cycle()
        await asyncio.Event().wait()
    finally:
        notifications.cancel()
        await asyncio.gather(notifications, return_exceptions=True)
        scheduler.shutdown(wait=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Run a single database cycle')
    parser.add_argument('--serve', action='store_true', help='Run the 15-second scheduler')
    parser.add_argument('--avatar', action='store_true', help='Run the dedicated photo/THA3 worker')
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    log_event(logging.getLogger("nianian.worker"), logging.INFO, "WORKER_READY")
    configure_event_loop()
    if args.avatar:
        from app.modules.avatar.worker import serve as avatar_serve
        asyncio.run(avatar_serve(once=args.once))
    elif args.once:
        asyncio.run(run_cycle())
    elif args.serve:
        asyncio.run(serve())


if __name__ == "__main__":
    main()
