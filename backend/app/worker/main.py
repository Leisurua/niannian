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
    from app.platform.models import DOMAIN_MODELS
    from app.modules.memory.rag import maintenance
    from app.worker.tasks import run_one
    from app.modules.conversation import summary, proactive
    from app.modules.signal import service as signals
    from app.modules.notification import service as notifications
    settings = get_settings()
    logger = logging.getLogger('nianian.worker')
    try:
        async with session_factory() as db:
            await tick(db, settings)
            next_memory_scan = await maintenance(db, _memory_scan_after)
            await schedule_cleanup(db)
            await summary.maintenance(db)
            await proactive.tick(db, settings)
            await signals.maintenance(db)
            await notifications.maintenance(db)
            await db.commit()
            _memory_scan_after = next_memory_scan
        for _ in range(20):
            if not await run_one(session_factory, S3Storage(settings) if settings.s3_access_key and settings.s3_secret_key else None):
                break
    except Exception:
        log_event(logger, logging.ERROR, 'WORKER_CYCLE_FAILED', error_code='DEPENDENCY_UNAVAILABLE')
        raise


async def serve():
    scheduler = AsyncIOScheduler()
    async def safe_cycle():
        try:
            await run_cycle()
        except Exception:
            pass  # stable redacted error already emitted; next tick retries
    scheduler.add_job(safe_cycle, 'interval', seconds=15, max_instances=1, coalesce=True)
    scheduler.start()
    try:
        await safe_cycle()
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Run a single database cycle')
    parser.add_argument('--serve', action='store_true', help='Run the 15-second scheduler')
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    log_event(logging.getLogger("nianian.worker"), logging.INFO, "WORKER_READY")
    configure_event_loop()
    if args.once:
        asyncio.run(run_cycle())
    elif args.serve:
        asyncio.run(serve())


if __name__ == "__main__":
    main()
